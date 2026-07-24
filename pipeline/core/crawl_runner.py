"""Orchestrates one scoped-crawler source end to end (Ziel 1/2/6 of the
pipeline overhaul): crawl -> for each document, sniff+extract -> stage ->
diff against review-state -> write auto-approved/modified, queue the rest.

The crawl_sources/*.yaml equivalent of core/runner.py, which does the same
fetch->stage->diff->write lifecycle for a single-fetch automated source -
shares core/staging.py, core/review_state.py, core/approval.py with it. One
crawl source produces one subject (subject_slug = source.id) with however
many windows its crawl turned up, same shape as e.g. schulferien_kmk's one
subject file with several independently-sourced windows.

Each crawled document is extracted independently by its sniffed kind
(scraper.py's extract_any): an ics_feed document's windows are used
directly, no LLM (Ziel 5); an html_page/pdf_document's text goes through
core/extraction.py's extract_dated_events, guided by the source's own
event_type_hint."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from core import approval, review_state, staging
from core.crawl_config import CrawlSource
from core.crawler import CrawledDocument, crawl
from core.extraction import ExtractionError, extract_dated_events
from scraper import extract_any


def _default_quelle(url: str) -> Dict[str, Any]:
    """A scoped-crawler source's license is a per-source, human decision
    (see pipeline/config/crawl_sources/*.yaml) - "tos_checked" here is only
    the placeholder default for a source config that hasn't set one yet,
    same spirit as this project's license enum never being auto-guessed
    (see main.py's LICENSE_OPTIONS docstring)."""
    return {
        "url": url,
        "license": "tos_checked",
        "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
        "extraction": "llm",
    }


def _windows_from_document(doc: CrawledDocument) -> List[Dict[str, Any]]:
    result = extract_any(doc.url, doc.content, doc.content_type)
    kind = result.get("kind")

    if kind == "ics_feed":
        return result.get("windows", [])

    if kind in ("html_page", "pdf_document", "image_page"):
        text = result.get("clean_markdown_full") or result.get("clean_markdown_preview", "")
        if not text.strip():
            return []
        try:
            events = extract_dated_events(text)
        except ExtractionError:
            return []
        return [
            {
                "type": "event",
                "year": int(e["date"][:4]),
                "from": e["date"],
                "to": e["date"],
                "precision": "exact",
                "ics": True,
                "name": e["label"],
            }
            for e in events
        ]

    return []


def run(source: CrawlSource) -> Dict[str, Any]:
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    documents = crawl(source)

    all_candidates: List[Dict[str, Any]] = []
    for doc in documents:
        doc_hash = staging.write_document(source.id, run_ts, doc.url, doc.content_type, doc.content)
        for window in _windows_from_document(doc):
            candidate = staging.build_candidate(source.id, source.id, window, doc_hash)
            staging.write_candidate(source.id, run_ts, candidate)
            all_candidates.append(candidate)

    state = review_state.load(source.id)
    auto_waved_through, needs_review, disappeared = review_state.diff(all_candidates, state)

    quelle = _default_quelle(source.seed_url)
    written = 0
    for candidate in auto_waved_through:
        # Stamp BEFORE writing - stamping after would only update
        # review-state's own copy, never reaching the data.yaml already
        # written a moment earlier.
        stamped_event = review_state.stamp_last_verified(state, candidate["content_hash"])
        try:
            approval.write_event(
                category=source.category,
                subject_slug=source.id,
                subject_name=source.id,
                event=stamped_event,
                quelle=quelle,
            )
            written += 1
        except approval.ApprovalError:
            continue

    for entry in disappeared:
        review_state.mark_disappeared(state, entry["content_hash"], entry["target_file"])
    review_state.save(source.id, state)

    return {
        "documents": len(documents),
        "candidates": len(all_candidates),
        "auto_approved": written,
        "needs_review": len(needs_review),
        "disappeared": len(disappeared),
    }
