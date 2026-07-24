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
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")


def _approve_like_the_review_ui_would(source_id: str, content_hash: str, event: dict, target_file: str) -> None:
    """Mimics what main.py's POST /review/.../approve does: write the event
    to data/ via core/approval.py, then record the decision - a fresh
    candidate is NEVER auto-approved by review_state.diff() on its own (see
    review_state.py's contract: unknown hash -> needs_review), a human
    action is what creates the "approved" decision in the first place."""
    approval.write_event("veranstaltungen", source_id, source_id, event, {
        "url": "https://example.org/events.ics", "license": "tos_checked",
        "retrieved_at": "2026-07-24", "extraction": "llm",
    })
    state = review_state.load(source_id)
    review_state.record_decision(state, content_hash, "approved", target_file, event)
    review_state.save(source_id, state)


def test_a_brand_new_candidate_is_queued_for_review_not_written_or_auto_approved(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )

    result = crawl_runner.run(_source())

    assert result["documents"] == 1
    assert result["candidates"] == 1
    assert result["auto_approved"] == 0
    assert result["needs_review"] == 1

    data_path = Path(approval.DATA_ROOT) / "veranstaltungen" / "test-source" / "data.yaml"
    assert not data_path.exists()


def test_a_previously_approved_candidate_auto_waves_through_on_a_later_run(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    first = crawl_runner.run(_source())
    assert first["needs_review"] == 1

    target_file = str(Path(approval.DATA_ROOT) / "veranstaltungen" / "test-source" / "data.yaml")
    event = {
        "type": "event", "year": 2026, "from": "2026-08-15", "to": "2026-08-15",
        "precision": "exact", "ics": True, "name": "Stadtfest",
    }
    from core.content_hash import content_hash, normalize_event
    hash_ = content_hash(normalize_event(event, "test-source"))
    _approve_like_the_review_ui_would("test-source", hash_, event, target_file)

    result = crawl_runner.run(_source())

    assert result["auto_approved"] == 1
    assert result["needs_review"] == 0

    datei = yaml.safe_load(Path(target_file).read_text(encoding="utf-8"))
    assert len(datei["windows"]) == 1
    assert datei["windows"][0].get("last_verified") is not None


def test_new_event_alongside_an_already_approved_one_only_queues_the_new_one(monkeypatch):
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    crawl_runner.run(_source())

    target_file = str(Path(approval.DATA_ROOT) / "veranstaltungen" / "test-source" / "data.yaml")
    event = {
        "type": "event", "year": 2026, "from": "2026-08-15", "to": "2026-08-15",
        "precision": "exact", "ics": True, "name": "Stadtfest",
    }
    from core.content_hash import content_hash, normalize_event
    hash_ = content_hash(normalize_event(event, "test-source"))
    _approve_like_the_review_ui_would("test-source", hash_, event, target_file)

    second_event_ics = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:1@example.org\r\nSUMMARY:Stadtfest\r\nDTSTART:20260815\r\nDTEND:20260816\r\nEND:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:2@example.org\r\nSUMMARY:Weihnachtsmarkt\r\nDTSTART:20261201\r\nDTEND:20261224\r\nEND:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    ).encode("utf-8")
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", second_event_ics)],
    )

    result = crawl_runner.run(_source())

    assert result["auto_approved"] == 1  # the already-known Stadtfest, re-verified
    assert result["needs_review"] == 1  # the new Weihnachtsmarkt


def test_an_llm_extraction_failure_is_reported_not_silently_swallowed(monkeypatch):
    """A missing/misconfigured LLM_PROVIDER (or any other extraction
    failure) must not look identical to "this document genuinely has no
    dates" - see _windows_from_document's docstring. Regression test for
    the crawl_runner.run() -> [] short-circuit that used to hide this."""
    monkeypatch.setattr(
        crawl_runner, "crawl",
        lambda source, on_progress=None: [CrawledDocument("https://example.org/events.html", "text/html", b"<html><body>some content</body></html>")],
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
        lambda source, on_progress=None: [CrawledDocument("https://example.org/events.ics", "text/calendar", ICS_BYTES)],
    )
    messages = []

    crawl_runner.run(_source(), on_progress=messages.append)

    assert any(m["phase"] == "crawling" for m in messages)
    assert any(m["phase"] == "extracting" and "Document 1/1" in m["detail"] for m in messages)
    assert any(m["phase"] == "diffing" for m in messages)
