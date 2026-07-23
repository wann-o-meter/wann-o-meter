"""End-to-end coverage (through the actual FastAPI routes, not just the
helper functions in test_main_categories.py) for: POST /create-page with a
nested category path, and the generalized /page-data + /page-meta
path-traversal guards. Isolated from the real repo via monkeypatched
DATA_ROOT/SCRAPED_DIR (tmp_path), so this never touches real data/."""

import asyncio
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

import main  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(main, "SCRAPED_DIR", tmp_path / "scraped")
    main.SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    main.state.scraped.clear()
    return TestClient(main.app)


def _mark_scraped(url: str, raw_data: dict) -> None:
    filename = main._filename_for(url)
    (main.SCRAPED_DIR / filename).write_text(yaml.dump(raw_data, allow_unicode=True), encoding="utf-8")
    main.state.scraped[url] = {
        "url": url,
        "kind": raw_data.get("kind", "unknown"),
        "filename": filename,
        "scraped_at": "2026-07-12T00:00:00",
        "content_hash": "irrelevant",
        "changed": None,
    }


class TestParseSeedLine:
    def test_splits_a_handle_prefixed_seed_line(self):
        assert main._parse_seed_line("@am9zZWY https://example.com") == ("https://example.com", "am9zZWY")

    def test_plain_seed_line_has_no_handle(self):
        assert main._parse_seed_line("https://example.com") == ("https://example.com", None)


class TestCreatePageContributedBy:
    def test_stamps_contributed_by_onto_the_source_when_given(self, client):
        url = "https://example.invalid/contributed"
        _mark_scraped(url, {"kind": "html_page", "dates": []})

        response = client.post(
            "/create-page",
            data={
                "url": url,
                "title": "Contributed Page",
                "category": "sport",
                "tags": "",
                "license": "own_derivation",
                "contributed_by": "am9zZWY",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        data = yaml.safe_load((main.DATA_ROOT / "sport" / "contributed-page" / "data.yaml").read_text(encoding="utf-8"))
        assert data["source"]["contributed_by"] == "am9zZWY"

    def test_omits_contributed_by_entirely_when_blank(self, client):
        url = "https://example.invalid/uncontributed"
        _mark_scraped(url, {"kind": "html_page", "dates": []})

        response = client.post(
            "/create-page",
            data={"url": url, "title": "Plain Page", "category": "sport", "tags": "", "license": "own_derivation"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        data = yaml.safe_load((main.DATA_ROOT / "sport" / "plain-page" / "data.yaml").read_text(encoding="utf-8"))
        assert "contributed_by" not in data["source"]


class TestCreatePageNested:
    def test_creates_a_page_under_a_deep_nested_path_and_writes_every_new_category_yaml(self, client):
        url = "https://example.invalid/bundesliga-spielplan"
        _mark_scraped(url, {"kind": "html_page", "dates": []})

        response = client.post(
            "/create-page",
            data={
                "url": url,
                "title": "Spielplan 2026/27",
                "category": "Sport/Fußball/Bundesliga",
                "tags": "fussball, liga",
                "license": "own_derivation",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        folder = main.DATA_ROOT / "sport" / "fussball" / "bundesliga" / "spielplan-2026-27"
        assert (folder / "data.yaml").exists()
        assert (folder / "page.yaml").exists()

        data = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
        assert data["subject"]["category"] == "sport/fussball/bundesliga"

        assert yaml.safe_load((main.DATA_ROOT / "sport" / "_category.yaml").read_text(encoding="utf-8")) == {
            "name": "Sport"
        }
        assert yaml.safe_load(
            (main.DATA_ROOT / "sport" / "fussball" / "_category.yaml").read_text(encoding="utf-8")
        ) == {"name": "Fußball"}
        assert yaml.safe_load(
            (main.DATA_ROOT / "sport" / "fussball" / "bundesliga" / "_category.yaml").read_text(encoding="utf-8")
        ) == {"name": "Bundesliga"}

    def test_rejects_a_reserved_top_level_segment_with_400(self, client):
        url = "https://example.invalid/reserved"
        _mark_scraped(url, {"kind": "html_page", "dates": []})

        response = client.post(
            "/create-page",
            data={"url": url, "title": "X", "category": "kalender/sub", "tags": "", "license": "own_derivation"},
        )
        assert response.status_code == 400
        assert "reserved" in response.text.lower()

    def test_rejects_tag_as_a_segment_at_any_depth_with_400(self, client):
        url = "https://example.invalid/tag-segment"
        _mark_scraped(url, {"kind": "html_page", "dates": []})

        response = client.post(
            "/create-page",
            data={"url": url, "title": "X", "category": "sport/tag", "tags": "", "license": "own_derivation"},
        )
        assert response.status_code == 400

    def test_rejects_a_path_deeper_than_max_depth_with_400(self, client):
        url = "https://example.invalid/too-deep"
        _mark_scraped(url, {"kind": "html_page", "dates": []})

        response = client.post(
            "/create-page",
            data={"url": url, "title": "X", "category": "a/b/c/d/e", "tags": "", "license": "own_derivation"},
        )
        assert response.status_code == 400
        assert "too deep" in response.text.lower()


class TestPageDataAndMetaGuards:
    def _seed_nested_page(self):
        folder = main.DATA_ROOT / "sport" / "fussball" / "bundesliga" / "spieltag-1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "data.yaml").write_text(yaml.dump({"subject": {"slug": "spieltag-1"}}), encoding="utf-8")
        (folder / "page.yaml").write_text(yaml.dump({"title": "Spieltag 1"}), encoding="utf-8")
        return folder

    def test_serves_data_yaml_for_a_deeply_nested_page(self, client):
        self._seed_nested_page()
        response = client.get("/page-data/sport/fussball/bundesliga/spieltag-1")
        assert response.status_code == 200
        assert "spieltag-1" in response.text

    def test_serves_page_yaml_for_a_deeply_nested_page(self, client):
        self._seed_nested_page()
        response = client.get("/page-meta/sport/fussball/bundesliga/spieltag-1")
        assert response.status_code == 200
        assert "Spieltag 1" in response.text

    def test_404s_for_a_category_folder_that_is_not_a_page(self, client):
        # "sport/fussball" exists as an intermediate category node (holds
        # spieltag-1), but has no page.yaml/data.yaml of its own - the guard
        # must reject it, not just check that it resolves under DATA_ROOT.
        self._seed_nested_page()
        response = client.get("/page-data/sport/fussball")
        assert response.status_code == 404

    def test_404s_on_a_path_traversal_attempt(self, client):
        self._seed_nested_page()
        response = client.get("/page-data/../../../../../../etc/passwd")
        assert response.status_code == 404

    def test_404s_for_a_nonexistent_page(self, client):
        response = client.get("/page-data/sport/fussball/bundesliga/does-not-exist")
        assert response.status_code == 404


class TestExtractLlmImagePage:
    """Regression test: _text_for_llm_extraction originally only recognized
    kind == "html_page", so a scrape produced by the vision-extraction path
    (kind == "image_page", see scraper.py's extract_image) silently fed an
    empty string to extract_dated_events and always returned 0 events."""

    def test_reads_clean_markdown_full_from_an_image_page_scrape(self, client, monkeypatch):
        import core.extraction as extraction

        url = "https://example.invalid/eclipse-map.gif"
        _mark_scraped(url, {
            "kind": "image_page",
            "clean_markdown_full": "Sonnenfinsternis am 12. August 2026",
        })
        monkeypatch.setattr(
            extraction, "extract_dated_events",
            lambda text: [{"date": "2026-08-12", "label": "Sonnenfinsternis"}] if "12. August 2026" in text else [],
        )

        response = client.post("/extract-llm", data={"url": url})

        assert response.status_code == 200
        assert response.json()["count"] == 1


class TestExtractLlmUnsupportedBinary:
    """Regression test: a scrape that failed upstream (e.g. vision
    extraction erroring on a PDF page because ANTHROPIC_API_KEY isn't set)
    saves kind == "unsupported_binary" with no clean_markdown_full. Previously
    /extract-llm and the /suggest-* routes ran on the resulting empty string
    and returned "Found 0 event(s)" / no tags / etc. indistinguishable from a
    page that was genuinely read and genuinely has no dates - now they surface
    the scrape's own failure reason instead."""

    def test_extract_llm_surfaces_the_scrape_failure_reason_instead_of_0_events(self, client, monkeypatch):
        import core.extraction as extraction

        url = "https://example.invalid/saisonkalender.pdf"
        _mark_scraped(url, {
            "kind": "unsupported_binary",
            "reason": "vision extraction failed: ANTHROPIC_API_KEY is not set - export it before using LLM extraction",
        })
        called = False

        def _fail_if_called(text):
            nonlocal called
            called = True
            return []

        monkeypatch.setattr(extraction, "extract_dated_events", _fail_if_called)

        response = client.post("/extract-llm", data={"url": url})

        assert response.status_code == 400
        assert "ANTHROPIC_API_KEY" in response.json()["error"]
        assert not called

    def test_suggest_tags_surfaces_the_scrape_failure_reason(self, client):
        url = "https://example.invalid/saisonkalender.pdf"
        _mark_scraped(url, {"kind": "unsupported_binary", "reason": "PDF has no extractable text"})

        response = client.post("/suggest-tags", data={"url": url})

        assert response.status_code == 400
        assert "PDF has no extractable text" in response.json()["error"]


class TestAcceptAndScrape:
    """Discovered -> Scrape in one click (POST /accept-and-scrape) replaces
    the old Discovered -> Accept -> switch tables -> Run Scraper flow (both
    now removed, along with the Accepted-Pages table). Only asserts the
    synchronous side effects (accept bookkeeping + background thread kicked
    off) - _scrape_and_record itself is mocked out here to avoid a real
    network call from the background thread."""

    @pytest.fixture(autouse=True)
    def _isolate_run_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "CRAWLER_STATE_DIR", tmp_path / "crawler_state")
        main.CRAWLER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        main.state.runs.clear()
        main.state.scraping.clear()
        yield
        main.state.runs.clear()
        main.state.scraping.clear()

    def _make_run(self, url: str) -> main.SeedRun:
        run = main.SeedRun("test-run", ["example.invalid"], None)
        run.discovered[url] = {"url": url, "status": "pending"}
        main.state.runs[run.run_id] = run
        return run

    def test_accepts_and_starts_a_background_scrape(self, client, monkeypatch):
        monkeypatch.setattr(main, "_scrape_and_record", lambda url: None)  # don't hit the network
        url = "https://example.invalid/eclipse-map.gif"
        run = self._make_run(url)

        response = client.post("/accept-and-scrape", data={"run_id": run.run_id, "url": url})

        assert response.status_code == 200
        assert response.json() == {"status": "started", "url": url}
        assert url in run.accepted
        assert run.discovered[url]["status"] == "accepted"

    def test_unknown_run_id_returns_404(self, client):
        response = client.post("/accept-and-scrape", data={"run_id": "does-not-exist", "url": "https://example.invalid/x"})
        assert response.status_code == 404

    def test_is_idempotent_for_an_already_accepted_url(self, client, monkeypatch):
        monkeypatch.setattr(main, "_scrape_and_record", lambda url: None)
        url = "https://example.invalid/eclipse-map.gif"
        run = self._make_run(url)
        run.accepted.append(url)

        response = client.post("/accept-and-scrape", data={"run_id": run.run_id, "url": url})

        assert response.status_code == 200
        assert run.accepted == [url]  # not appended twice


class TestCrawlOneSeedAutoScrape:
    """Regression test for auto-scraping a dated page during a live crawl
    (main.py's _crawl_one_seed, "Auto-scrape dated pages" toggle). This used
    to call _accept_and_start_scrape (which acquires state.lock itself)
    from inside a `with state.lock:` block already held by the caller -
    state.lock is a plain, non-reentrant threading.Lock, so that would
    deadlock the moment a dated page was found. Runs the crawl coroutine on
    a background thread with a bounded join() instead of asyncio.wait_for():
    a real deadlock blocks the OS thread synchronously (not just the
    coroutine), so a timeout on the coroutine itself would never fire - only
    a thread join with a timeout can detect it without hanging the suite."""

    @pytest.fixture(autouse=True)
    def _isolate_run_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "CRAWLER_STATE_DIR", tmp_path / "crawler_state")
        main.CRAWLER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        main.state.runs.clear()
        main.state.scraping.clear()
        yield
        main.state.runs.clear()
        main.state.scraping.clear()

    def test_auto_scrape_dated_page_does_not_deadlock(self, monkeypatch):
        monkeypatch.setattr(main, "_scrape_and_record", lambda url: None)  # don't hit the network
        monkeypatch.setattr(main, "BLACKLISTED_DOMAINS", [])

        seed_url = "https://example.invalid"
        dated_url = "https://example.invalid/eclipse-map.gif"
        home_html = f'<html><body><a href="{dated_url}">link</a></body></html>'

        async def fake_crawl_page(client, target_url):
            if target_url == dated_url:
                return (
                    {"url": dated_url, "title": "Eclipse map", "preview": "12. August 2026",
                     "status": "pending", "has_dates": True, "date_count": 1},
                    dated_url, "",
                )
            return (
                {"url": seed_url, "title": "Home", "preview": "", "status": "pending",
                 "has_dates": False, "date_count": 0},
                seed_url, home_html,
            )

        monkeypatch.setattr(main, "crawl_page", fake_crawl_page)

        run = main.SeedRun("auto-scrape-run", ["example.invalid"], 2, auto_accept_dated=True)
        main.state.runs[run.run_id] = run

        def runner():
            async def go():
                async with httpx.AsyncClient() as client:
                    await main._crawl_one_seed(client, run, "example.invalid")
            asyncio.run(go())

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=5)

        assert not thread.is_alive(), (
            "_crawl_one_seed deadlocked - _accept_and_start_scrape must be called "
            "outside any block already holding state.lock"
        )
        assert dated_url in run.accepted
        assert run.discovered[dated_url]["status"] == "accepted"


class TestScrapeAllDiscovered:
    """POST /crawler/runs/{run_id}/scrape-all - the "Scrape All" button next
    to Discovered Pages' Refresh. Scrapes every discovered URL not yet
    scraped or rejected, single-flight guarded by the same rescrape_state
    /rescrape-all already uses for its own batch."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setattr(main, "CRAWLER_STATE_DIR", tmp_path / "crawler_state")
        main.CRAWLER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        main.state.runs.clear()
        main.state.scraped.clear()
        main.state.scraping.clear()
        main.rescrape_state.running = False
        main.rescrape_state.total = 0
        main.rescrape_state.done = 0
        main.rescrape_state.changed_urls = []
        yield
        # Wait for any background batch this test started to actually finish
        # (rescrape_state is a module-level singleton) so a slow test can't
        # leave running=True bleeding into the next test.
        for _ in range(50):
            if not main.rescrape_state.running:
                break
            time.sleep(0.05)
        main.state.runs.clear()
        main.state.scraped.clear()
        main.state.scraping.clear()

    def _make_run(self) -> main.SeedRun:
        run = main.SeedRun("scrape-all-run", ["example.invalid"], None)
        run.discovered = {
            "https://example.invalid/a": {"url": "https://example.invalid/a", "status": "pending"},
            "https://example.invalid/b": {"url": "https://example.invalid/b", "status": "pending"},
            "https://example.invalid/already-scraped": {"url": "https://example.invalid/already-scraped", "status": "scraped"},
            "https://example.invalid/rejected": {"url": "https://example.invalid/rejected", "status": "rejected"},
        }
        run.rejected.add("https://example.invalid/rejected")
        main.state.scraped["https://example.invalid/already-scraped"] = {"kind": "html_page"}
        main.state.runs[run.run_id] = run
        return run

    def test_scrapes_only_unscraped_unrejected_urls(self, client, monkeypatch):
        monkeypatch.setattr(main, "_scrape_and_record", lambda url: None)
        run = self._make_run()

        response = client.post(f"/crawler/runs/{run.run_id}/scrape-all")

        assert response.status_code == 200
        assert response.json()["total"] == 2

    def test_unknown_run_id_returns_404(self, client):
        response = client.post("/crawler/runs/does-not-exist/scrape-all")
        assert response.status_code == 404

    def test_rejects_concurrent_batch_with_409(self, client, monkeypatch):
        started = threading.Event()
        released = threading.Event()

        def slow_scrape(url):
            started.set()
            released.wait(timeout=5)

        monkeypatch.setattr(main, "_scrape_and_record", slow_scrape)
        run = self._make_run()

        first = client.post(f"/crawler/runs/{run.run_id}/scrape-all")
        assert first.status_code == 200
        started.wait(timeout=5)

        second = client.post(f"/crawler/runs/{run.run_id}/scrape-all")
        assert second.status_code == 409

        released.set()
