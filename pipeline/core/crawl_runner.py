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

import html
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core import approval, review_state, staging
from core.crawl_config import CrawlSource
from core.crawler import CrawledDocument, crawl
from core.extraction import ExtractionError, extract_dated_events, suggest_title
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


def _windows_from_document(doc: CrawledDocument, on_progress: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
    """Raises ExtractionError (rather than swallowing it) if the LLM call
    itself fails, e.g. a missing API key for the configured LLM_PROVIDER -
    see run()'s per-document try/except, which turns that into a reported
    extraction_errors entry instead of a silent "0 candidates" that looks
    identical to "this document genuinely has no dates"."""
    result = extract_any(doc.url, doc.content, doc.content_type)
    kind = result.get("kind")

    if kind == "ics_feed":
        return result.get("windows", [])

    if kind in ("html_page", "pdf_document", "image_page"):
        text = result.get("clean_markdown_full") or result.get("clean_markdown_preview", "")
        if not text.strip():
            return []
        events = extract_dated_events(text, on_progress=on_progress)
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


_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _subject_name(documents: List[CrawledDocument], fallback: str) -> str:
    """A readable page title for the subject this source writes, taken from
    the first crawled document's <title> and cleaned up by the model (see
    extraction.suggest_title - the raw tag is usually full of year ranges and
    the site name). Without this a crawl source's page.yaml got the source id
    verbatim as its title, so the site showed "eclipse-gsfc-nasa-gov" as a
    page heading.

    Falls back to the source id on anything going wrong - a title is
    cosmetic, and page.yaml is written once (store.schreibe_page_yaml_falls_neu),
    so this must never be the thing that fails a whole crawl.
    """
    for doc in documents:
        match = _TITLE_RE.search(doc.content[:100_000])
        if not match:
            continue
        raw_title = html.unescape(match.group(1).decode("utf-8", "replace")).strip()
        if not raw_title:
            continue
        try:
            return suggest_title(doc.content[:2000].decode("utf-8", "replace"), raw_title) or raw_title
        except ExtractionError:
            return raw_title
    return fallback


def run(
    source: CrawlSource,
    on_progress: Optional[Callable[[Dict[str, str]], None]] = None,
    on_page: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """on_progress, if given, is called with {"phase": "crawling"|
    "extracting"|"diffing", "detail": str} at each meaningful step - the
    phase is what lets main.py's dashboard show "Crawling" vs "Extracting"
    as a distinct, glanceable label instead of a caller having to parse it
    back out of a free-text message. detail carries the specifics (current
    URL, chunk N/M, chars sent) - a slow run (many in-scope pages, or
    several LLM calls for one large chunked page) shows something better
    than a static "Running..." for however long that takes."""
    def report(phase: str, detail: str) -> None:
        if on_progress:
            on_progress({"phase": phase, "detail": detail})

    def report_page(url: str, status: str) -> None:
        if on_page:
            on_page(url, status)

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report("crawling", f"Starting at {source.seed_url}")
    documents = crawl(source, on_progress=lambda detail: report("crawling", detail), on_page=report_page)
    report("crawling", f"Done - {len(documents)} document(s) found")

    all_candidates: List[Dict[str, Any]] = []
    extraction_errors: List[str] = []
    for i, doc in enumerate(documents, start=1):
        doc_hash = staging.write_document(source.id, run_ts, doc.url, doc.content_type, doc.content)
        report("extracting", f"Document {i}/{len(documents)}: {doc.url}")
        report_page(doc.url, "extracting")
        try:
            windows = _windows_from_document(doc, on_progress=lambda detail: report("extracting", detail))
        except ExtractionError as e:
            extraction_errors.append(f"{doc.url}: {e}")
            report_page(doc.url, f"extraction failed: {str(e)[:80]}")
            continue
        report_page(doc.url, f"{len(windows)} event(s) found" if windows else "no dates found")
        for window in windows:
            candidate = staging.build_candidate(source.id, source.id, window, doc_hash)
            staging.write_candidate(source.id, run_ts, candidate)
            all_candidates.append(candidate)

    report("diffing", "Comparing against review-state...")
    state = review_state.load(source.id)
    auto_waved_through, needs_review, disappeared = review_state.diff(all_candidates, state)

    quelle = _default_quelle(source.seed_url)
    subject_name = _subject_name(documents, source.id)
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
                subject_name=subject_name,
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
        # NOT the source's auto_approve_ics setting - these are candidates a
        # human approved in an EARLIER run, which review_state.diff() waves
        # through unchanged. Named "auto_approved" originally, which read as
        # "the pipeline approved this on its own" and made a re-confirmed
        # write look like it had bypassed review.
        "reconfirmed": written,
        "needs_review": len(needs_review),
        "disappeared": len(disappeared),
        "extraction_errors": extraction_errors,
    }
