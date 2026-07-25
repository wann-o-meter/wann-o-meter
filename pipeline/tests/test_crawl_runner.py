import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import approval, crawl_runner, review_state, staging  # noqa: E402
from core.crawl_config import CrawlSource  # noqa: E402
from core.crawler import CrawledDocument  # noqa: E402
from core.extraction import ExtractionError  # noqa: E402

ICS_BYTES = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
    "BEGIN:VEVENT\r\nUID:1@example.org\r\nSUMMARY:Stadtfest\r\nDTSTART:20260815\r\nDTEND:20260816\r\nEND:VEVENT\r\n"
    "END:VCALENDAR\r\n"
).encode("utf-8")


def _source(**overrides):
    base = dict(
        id="test-source",
        seed_url="https://example.org/events.ics",
        category="veranstaltungen",
        allowed_domains=["example.org"],
        path_prefix=None,
        max_depth=0,
        formats=["ics"],
        event_type_hint="Stadtfeste",
        schedule="manual",
    )
    base.update(overrides)
    return CrawlSource(**base)


@pytest.fixture(autouse=True)
def _isolate_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    monkeypatch.setattr(review_state, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")


def _approve_like_the_review_ui_would(source_id: str, event: dict) -> None:
    """Mimics what main.py's POST /review/.../approve does - which is now
    exactly one thing: write the event to data/. The file IS the record of
    what is approved, so there is no second bookkeeping step. A fresh
    candidate is never waved through on its own (review_state.diff: not in
    the file -> needs_review); a human action puts it there."""
    approval.write_event("veranstaltungen", source_id, source_id, event, {
        "url": "https://example.org/events.ics", "license": "tos_checked",
        "retrieved_at": "2026-07-24", "extraction": "llm",
    })


def test_a_brand_new_candidate_is_queued_for_review_not_written_or_reconfirmed(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )

    result = crawl_runner.run(_source())

    assert result["documents"] == 1
    assert result["candidates"] == 1
    assert result["reconfirmed"] == 0
    assert result["needs_review"] == 1

    data_path = Path(approval.DATA_ROOT) / "veranstaltungen" / "test-source" / "data.yaml"
    assert not data_path.exists()


def test_a_previously_approved_candidate_auto_waves_through_on_a_later_run(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    first = crawl_runner.run(_source())
    assert first["needs_review"] == 1

    target_file = str(Path(approval.DATA_ROOT) / "veranstaltungen" / "test-source" / "data.yaml")
    event = {
        "type": "event", "year": 2026, "from": "2026-08-15", "to": "2026-08-15",
        "precision": "exact", "ics": True, "name": "Stadtfest",
    }
    _approve_like_the_review_ui_would("test-source", event)

    result = crawl_runner.run(_source())

    assert result["reconfirmed"] == 1
    assert result["needs_review"] == 0

    datei = yaml.safe_load(Path(target_file).read_text(encoding="utf-8"))
    assert len(datei["windows"]) == 1


def test_new_event_alongside_an_already_approved_one_only_queues_the_new_one(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    crawl_runner.run(_source())

    target_file = str(Path(approval.DATA_ROOT) / "veranstaltungen" / "test-source" / "data.yaml")
    event = {
        "type": "event", "year": 2026, "from": "2026-08-15", "to": "2026-08-15",
        "precision": "exact", "ics": True, "name": "Stadtfest",
    }
    _approve_like_the_review_ui_would("test-source", event)

    second_event_ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:1@example.org\r\nSUMMARY:Stadtfest\r\nDTSTART:20260815\r\nDTEND:20260816\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:2@example.org\r\nSUMMARY:Weihnachtsmarkt\r\nDTSTART:20261201\r\nDTEND:20261224\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode("utf-8")
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", second_event_ics)],
    )

    result = crawl_runner.run(_source())

    assert result["reconfirmed"] == 1  # the already-known Stadtfest, re-verified
    assert result["needs_review"] == 1  # the new Weihnachtsmarkt


def test_an_llm_extraction_failure_is_reported_not_silently_swallowed(monkeypatch):
    """A missing/misconfigured LLM_PROVIDER (or any other extraction
    failure) must not look identical to "this document genuinely has no
    dates" - see _windows_from_document's docstring. Regression test for
    the crawl_runner.run() -> [] short-circuit that used to hide this."""
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.html", "text/html", b"<html><body>some content</body></html>")],
    )
    monkeypatch.setattr(
        crawl_runner, "extract_any",
        lambda url, content, content_type: {"kind": "html_page", "clean_markdown_full": "some content"},
    )
    monkeypatch.setattr(
        crawl_runner, "extract_dated_events",
        lambda text, on_progress=None: (_ for _ in ()).throw(ExtractionError("LLM call failed: missing API key")),
    )

    result = crawl_runner.run(_source(formats=["html"]))

    assert result["documents"] == 1
    assert result["candidates"] == 0
    assert result["extraction_errors"] == ["https://example.org/events.html: LLM call failed: missing API key"]


def test_on_progress_is_called_with_crawl_and_per_document_updates(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    messages = []

    crawl_runner.run(_source(), on_progress=messages.append)

    assert any(m["phase"] == "crawling" for m in messages)
    assert any(m["phase"] == "extracting" and "Document 1/1" in m["detail"] for m in messages)
    assert any(m["phase"] == "diffing" for m in messages)


class TestSubjectName:
    """page.yaml's title used to be the source id verbatim ("eclipse-gsfc-
    nasa-gov"), which is what the site then showed as the page heading."""

    def _doc(self, title):
        return CrawledDocument(
            "https://example.org/x", "text/html",
            f"<html><head><title>{title}</title></head><body>hi</body></html>".encode(),
        )

    def test_uses_the_cleaned_up_page_title(self, monkeypatch):
        monkeypatch.setattr(crawl_runner, "suggest_title", lambda text, raw: "Sonnenfinsternis")
        assert crawl_runner._subject_name([self._doc("Solar Eclipse 2027 - NASA")], "fallback-id") == "Sonnenfinsternis"

    def test_falls_back_to_the_raw_title_when_the_model_fails(self, monkeypatch):
        def boom(text, raw):
            raise crawl_runner.ExtractionError("no api key")
        monkeypatch.setattr(crawl_runner, "suggest_title", boom)
        assert crawl_runner._subject_name([self._doc("Solar Eclipse 2027")], "fallback-id") == "Solar Eclipse 2027"

    def test_falls_back_to_the_source_id_when_no_document_has_a_title(self):
        doc = CrawledDocument("https://example.org/x", "text/html", b"<html><body>no title</body></html>")
        assert crawl_runner._subject_name([doc], "fallback-id") == "fallback-id"

    def test_unescapes_html_entities_in_the_title(self, monkeypatch):
        monkeypatch.setattr(crawl_runner, "suggest_title", lambda text, raw: raw)
        assert crawl_runner._subject_name([self._doc("Feste &amp; M&auml;rkte")], "x") == "Feste & Märkte"


CATALOG_ROWS = "\n".join(
    f"[{i:05d}](../map/20{i:02d}-06-21.gif) [20{i:02d} Jun 21](../s.php) 12:04:46 T"
    for i in range(20, 40)
)


def _html(body):
    return CrawledDocument("https://example.org/cat", "text/html", f"<html><body>{body}</body></html>".encode())


class TestStaticDates:
    def test_reads_iso_and_catalog_date_forms_and_dedupes_them(self):
        dates, negative = crawl_runner._static_dates("[2001-06-21.gif] [2001 Jun 21] and 2002 Dec 04")
        assert dates == ["2001-06-21", "2002-12-04"]
        assert negative == 0

    def test_a_negative_year_is_counted_not_read_as_its_positive_twin(self):
        """-1900-03-01 is an eclipse in 1901 BC. Reporting it as the year-1900
        CE date is wrong by 3801 years - and lib/date.ts cannot store it at
        all, so it has to be counted and skipped, not silently converted."""
        dates, negative = crawl_runner._static_dates("[-1900-03-01.gif] [-1900 Mar 01]")
        assert dates == []
        assert negative == 1

    def test_ignores_impossible_month_and_day_values(self):
        dates, _ = crawl_runner._static_dates("2001-13-01 2001-00-09 2001-02-31 2001-02-28")
        assert dates == ["2001-02-31", "2001-02-28"] or dates == ["2001-02-28", "2001-02-31"]


class TestExtractorChoice:
    def test_a_date_table_is_read_directly_without_calling_the_model(self, monkeypatch):
        def no_llm(*a, **k):
            raise AssertionError("the model must not be called for a date table")
        monkeypatch.setattr(crawl_runner, "extract_dated_events", no_llm)

        windows, note = crawl_runner._windows_from_document(_html(CATALOG_ROWS), "Sonnenfinsternis")

        assert len(windows) == 20
        assert note.startswith("static: 20 date(s)")
        assert {w["name"] for w in windows} == {"Sonnenfinsternis"}

    def test_prose_with_a_couple_of_dates_still_goes_to_the_model(self, monkeypatch):
        monkeypatch.setattr(
            crawl_runner, "extract_dated_events",
            lambda text, on_progress=None: [{"date": "2026-09-12", "label": "Stadtfest"}],
        )
        windows, note = crawl_runner._windows_from_document(_html("Das Stadtfest ist am 2026-09-12."), "x")

        assert [w["name"] for w in windows] == ["Stadtfest"]
        assert note == "llm: 1 event(s)"

    def test_mode_llm_keeps_the_model_even_for_a_date_table(self, monkeypatch):
        monkeypatch.setattr(crawl_runner, "extract_dated_events", lambda text, on_progress=None: [])
        _, note = crawl_runner._windows_from_document(_html(CATALOG_ROWS), "x", mode="llm")
        assert note == "llm: 0 event(s)"

    def test_mode_static_skips_the_model_even_on_a_page_with_few_dates(self, monkeypatch):
        def no_llm(*a, **k):
            raise AssertionError("mode=static must never call the model")
        monkeypatch.setattr(crawl_runner, "extract_dated_events", no_llm)
        windows, note = crawl_runner._windows_from_document(_html("nur am 2026-09-12"), "Termin", mode="static")
        assert [w["from"] for w in windows] == ["2026-09-12"]
        assert note == "static: 1 date(s)"

    def test_a_page_of_only_pre_year_1_dates_says_so_instead_of_looking_empty(self, monkeypatch):
        monkeypatch.setattr(crawl_runner, "extract_dated_events", lambda text, on_progress=None: [])
        bce = "\n".join(f"[-19{i:02d} Mar 01](../x) [-19{i:02d}-03-01.gif]" for i in range(20))

        windows, note = crawl_runner._windows_from_document(_html(bce), "Sonnenfinsternis")

        assert windows == []
        assert "20 before year 1 skipped (not storable)" in note


def _staged_candidates(source_id: str) -> list:
    """Every candidate file a run wrote, newest run first."""
    runs = sorted((Path(staging.STAGING_ROOT) / source_id).iterdir(), reverse=True)
    return [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted((runs[0] / "candidates").glob("*.yaml"))
    ]


class TestCandidateCarriesSubjectNameAndSourceUrl:
    """Both fields exist so an approval through the review UI produces the
    same data as an auto-waved-through one: the cleaned-up page title
    (rather than the raw source id) and a per-window citation."""

    @pytest.fixture
    def html_run(self, monkeypatch):
        monkeypatch.setattr(
            crawl_runner, "crawl",
            lambda source, on_progress=None, on_page=None: [CrawledDocument(
                "https://example.org/termine.html", "text/html",
                b"<html><head><title>Sonnenfinsternisse 2001 - 2100 | NASA</title></head>"
                b"<body><p>Am 2026-08-12.</p></body></html>",
            )],
        )
        monkeypatch.setattr(crawl_runner, "suggest_title", lambda text, raw_title: "Sonnenfinsternis")
        monkeypatch.setattr(
            crawl_runner, "extract_dated_events",
            lambda text, on_progress=None: [{"date": "2026-08-12", "label": "Sonnenfinsternis"}],
        )
        crawl_runner.run(_source(formats=["html"], event_type_hint=""))
        return _staged_candidates("test-source")

    def test_the_candidate_carries_the_cleaned_up_page_title(self, html_run):
        assert [c["subject_name"] for c in html_run] == ["Sonnenfinsternis"]

    def test_the_window_is_stamped_with_the_document_it_came_from(self, html_run):
        assert html_run[0]["event"]["source_urls"] == ["https://example.org/termine.html"]

    def test_stamping_does_not_change_the_candidates_identity(self, html_run):
        """source_urls is excluded from the content hash on purpose (see
        core/content_hash.py) - if it leaked in, adding the stamp would
        re-open every already-decided candidate for review."""
        from core.content_hash import content_hash, normalize_event
        event = html_run[0]["event"]
        assert html_run[0]["content_hash"] == content_hash(normalize_event(event, "test-source"))
        assert content_hash(normalize_event({**event, "source_urls": ["https://other.invalid"]}, "test-source")) == html_run[0]["content_hash"]


def test_a_document_without_a_title_falls_back_to_the_source_id(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None, on_page=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    crawl_runner.run(_source())

    assert _staged_candidates("test-source")[0]["subject_name"] == "test-source"


class TestSeveralSourcesAggregateIntoOnePage:
    """The reason subject_slug exists: NASA's eclipse catalog splits one
    subject across a page per century, and a reader wants one page, not one
    per century. Two sources with the same category + subject_slug have to
    land in the same data.yaml, keep a shared window once, and cite both."""

    OVERLAP = "1582-10-15"  # a line every page of that catalog carries

    def _source_for(self, source_id: str, url: str):
        return _source(
            id=source_id, seed_url=url, category="astronomie",
            subject_slug="sonnenfinsternis", subject_name="Sonnenfinsternis",
            formats=["html"], event_type_hint="Sonnenfinsternis",
        )

    def _run(self, monkeypatch, source_id: str, url: str, own_date: str):
        monkeypatch.setattr(
            crawl_runner, "crawl",
            lambda source, on_progress=None, on_page=None: [
                CrawledDocument(url, "text/html", b"<html><body>dates</body></html>")
            ],
        )
        monkeypatch.setattr(
            crawl_runner, "extract_dated_events",
            lambda text, on_progress=None: [
                {"date": own_date, "label": "Sonnenfinsternis"},
                {"date": self.OVERLAP, "label": "Sonnenfinsternis"},
            ],
        )
        source = self._source_for(source_id, url)
        crawl_runner.run(source)
        # What main.py's approve route does with each queued candidate.
        for candidate in _staged_candidates(source_id):
            approval.write_event(
                candidate["category"], candidate["subject_slug"], candidate["subject_name"],
                candidate["event"],
                {"url": url, "license": "official_par5", "retrieved_at": "2026-07-25", "extraction": "llm"},
            )

    @pytest.fixture
    def merged(self, monkeypatch):
        self._run(monkeypatch, "nasa-1901-2000", "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html", "1999-08-11")
        self._run(monkeypatch, "nasa-2001-2100", "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html", "2026-08-12")
        path = Path(approval.DATA_ROOT) / "astronomie" / "sonnenfinsternis" / "data.yaml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_both_sources_write_into_the_same_page(self, merged):
        assert merged["subject"] == {"slug": "sonnenfinsternis", "category": "astronomie"}
        assert sorted(w["from"] for w in merged["windows"]) == ["1582-10-15", "1999-08-11", "2026-08-12"]

    def test_a_window_both_sources_report_is_kept_once_and_cites_both(self, merged):
        shared = [w for w in merged["windows"] if w["from"] == self.OVERLAP]
        assert len(shared) == 1
        assert sorted(shared[0]["source_urls"]) == [
            "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html",
            "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
        ]

    def test_a_window_only_one_source_reports_cites_only_that_one(self, merged):
        own = [w for w in merged["windows"] if w["from"] == "1999-08-11"]
        assert own[0]["source_urls"] == ["https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html"]

    def test_both_sources_appear_in_the_pages_source_list(self, merged):
        assert sorted(s["url"] for s in merged["source"]) == [
            "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html",
            "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
        ]

    def test_the_shared_page_gets_the_configured_title_not_a_crawled_one(self, merged):
        page = yaml.safe_load(
            (Path(approval.DATA_ROOT) / "astronomie" / "sonnenfinsternis" / "page.yaml").read_text(encoding="utf-8")
        )
        assert page["title"] == "Sonnenfinsternis"

    def test_the_shared_window_has_one_identity_but_is_reviewed_per_source(self, merged):
        """content_hash covers subject_slug, so under a shared page the same
        real-world event hashes identically across sources - that is what lets
        merge_zeitfenster recognise it as one window. Review state stays
        per-source though (one file each), so a second source reporting an
        already-approved event is still reviewed rather than waved through on
        another source's decision."""
        def shared_hash(source_id):
            return next(
                c["content_hash"] for c in _staged_candidates(source_id)
                if c["event"]["from"] == self.OVERLAP
            )

        assert shared_hash("nasa-1901-2000") == shared_hash("nasa-2001-2100")
        assert review_state._path_for("nasa-1901-2000") != review_state._path_for("nasa-2001-2100")


class TestSuggestedCategory:
    """suggest_category existed from the start with no caller, so a source
    created without a typed category fell back to its id - which is derived
    from the domain, giving pages like "eclipse-gsfc-nasa-gov"."""

    def _docs(self):
        return [CrawledDocument(
            url="https://eclipse.invalid/SEcat5",
            content=b"<html><body>Solar eclipses 1901-2000</body></html>",
            content_type="text/html",
        )]

    def test_a_configured_category_is_never_second_guessed(self, monkeypatch):
        monkeypatch.setattr(crawl_runner, "suggest_category", lambda *a, **k: "should-not-be-called")
        source = _source(id="nasa", category="astronomie")

        assert crawl_runner._suggested_category(source, self._docs(), "Sonnenfinsternis") == "astronomie"

    def test_the_id_fallback_is_replaced_by_a_suggestion(self, monkeypatch):
        """category == id is exactly what create_crawl_source writes when the
        operator types nothing - the case worth guessing for."""
        monkeypatch.setattr(crawl_runner, "suggest_category", lambda *a, **k: "Astronomie")
        source = _source(id="eclipse-gsfc-nasa-gov", category="eclipse-gsfc-nasa-gov")

        assert crawl_runner._suggested_category(source, self._docs(), "Sonnenfinsternis") == "Astronomie"

    def test_a_failed_suggestion_falls_back_to_the_configured_value(self, monkeypatch):
        """A category guess must never be the thing that fails a whole crawl."""
        def _boom(*a, **k):
            raise ExtractionError("no API key")
        monkeypatch.setattr(crawl_runner, "suggest_category", _boom)
        source = _source(id="nasa", category="nasa")

        assert crawl_runner._suggested_category(source, self._docs(), "Sonnenfinsternis") == "nasa"

    def test_an_empty_suggestion_falls_back_too(self, monkeypatch):
        monkeypatch.setattr(crawl_runner, "suggest_category", lambda *a, **k: "")
        source = _source(id="nasa", category="nasa")

        assert crawl_runner._suggested_category(source, self._docs(), "Sonnenfinsternis") == "nasa"

    def test_existing_categories_are_offered_for_reuse(self, tmp_path):
        """Reuse over fragmentation - the suggester can only prefer an
        existing category if it is actually told about it."""
        # One page per nesting depth, plus a page with no category at all -
        # the category is everything above the slug, whatever the depth, and
        # a slug sitting directly under data/ has no category to offer.
        for page in ["astronomie/sonnenfinsternis", "sport/fussball/bundesliga", "a/b/c/seite", "no-category"]:
            folder = approval.DATA_ROOT / page
            folder.mkdir(parents=True)
            (folder / "data.yaml").write_text("{}", encoding="utf-8")

        assert crawl_runner._existing_categories() == ["a/b/c", "astronomie", "sport/fussball"]

    def test_no_data_directory_yet_is_not_an_error(self):
        assert crawl_runner._existing_categories() == []
