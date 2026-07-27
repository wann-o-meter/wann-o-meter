"""Orchestrates one scoped-crawler source end to end (Ziel 1/2/6 of the
pipeline overhaul): crawl -> for each document, sniff+extract -> stage ->
diff against review-state -> write auto-approved/modified, queue the rest.

The crawl_sources/*.yaml equivalent of core/runner.py, which does the same
fetch->stage->diff->write lifecycle for a single-fetch automated source -
shares core/staging.py, core/review_state.py, core/approval.py with it. One
crawl source produces one subject (source.subject_slug, which defaults to
source.id) with however many windows its crawl turned up, same shape as e.g.
schulferien_kmk's one subject file with several independently-sourced
windows.

SEVERAL sources may point at the same subject_slug + category on purpose -
that is how one page aggregates several overlapping sources (NASA's eclipse
catalog splits the same subject across one page per century; a reader wants
one page, not one per century). Each source keeps its own review-state and
its own citation; store.merge_zeitfenster unions them per window.

Each crawled document is extracted independently by its sniffed kind
(core/sniff.py's extract_any): an ics_feed document's windows are used
directly, no LLM (Ziel 5); an html_page/pdf_document's text goes through
core/extraction.py's extract_dated_events, guided by the source's own
event_type_hint."""

import html
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from core import approval, review_state, staging
from core.crawl_config import DEFAULT_EXTRACTION_MODE, CrawlSource
from core.crawler import CrawledDocument, crawl
from core.extraction import ExtractionError, extract_dated_events, suggest_category, suggest_title
from core.sniff import extract_any


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


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Two unambiguous machine-written date forms: ISO ("2001-06-21") and the
# catalog form ("2001 Jun 21"). Both keep an optional leading "-" so a
# negative (pre-year-1) year is RECOGNISED rather than silently read as its
# positive counterpart - it's then reported and skipped, not stored.
_STATIC_DATE_RES = (
    re.compile(r"(?<![\d-])(-?\d{4})-(\d{2})-(\d{2})(?![\d-])"),
    re.compile(
        r"(?<![\d-])(-?\d{4})\s+(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?!\d)",
        re.IGNORECASE,
    ),
)

# Below this, a page is prose that happens to mention some dates, and the
# model's labels are worth their cost. At or above it the page is a date
# TABLE, where an LLM is strictly worse: it costs one call per 20k chars,
# can drop rows silently, and invents nothing a regex couldn't read. Set
# high enough that an archive nav ("2024", "2023", ...) doesn't trip it.
STATIC_DATE_THRESHOLD = 15


def _static_dates(text: str) -> Tuple[List[str], int]:
    """Deterministic date scrape: ([storable "YYYY-MM-DD" in page order],
    count of recognised-but-unstorable pre-year-1 dates).

    The second element exists so a page of nothing but BCE dates reports
    "239 found, none storable" instead of looking identical to a page with
    no dates at all - which is exactly how eclipse.gsfc.nasa.gov's BCE
    catalogs presented (see lib/date.ts's DAY_RE: no sign, so a negative
    year cannot be represented at all)."""
    found: Dict[str, None] = {}
    negative: Dict[str, None] = {}
    for regex in _STATIC_DATE_RES:
        for match in regex.finditer(text):
            year_str, month_str, day_str = match.groups()
            month = _MONTHS.get(month_str.lower(), 0) if not month_str.isdigit() else int(month_str)
            year, day = int(year_str), int(day_str)
            if not (1 <= month <= 12 and 1 <= day <= 31):
                continue
            # Deduped like the storable ones, not counted per match: a catalog
            # writes each date twice (once in a .gif URL, once as text), so a
            # raw match count reported double what the page actually lists.
            target = negative if year < 1 else found
            target.setdefault(f"{year:05d}-{month:02d}-{day:02d}" if year < 1 else f"{year:04d}-{month:02d}-{day:02d}", None)
    return list(found), len(negative)


def _window(date: str, label: str, end: str = "") -> Dict[str, Any]:
    """`end` is the inclusive last day of a multi-day span (Oktoberfest,
    a festival week); empty for the single-day case, where from == to."""
    return {
        "type": "event",
        "year": int(date[:4]),
        "from": date,
        "to": end or date,
        "precision": "exact",
        "ics": True,
        "name": label,
    }


def _windows_from_document(
    doc: CrawledDocument,
    label: str,
    mode: str = DEFAULT_EXTRACTION_MODE,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """Returns (windows, note) where note names which extractor ran and what
    it produced - reported per page so "why did this give me one event" is
    answerable from the UI instead of by reading the source.

    `label` names the windows the deterministic path produces (a table of
    dates carries no per-row title an LLM could paraphrase) - the source's
    event_type_hint, else the page title.

    `mode` is the source's extraction_mode (see core/crawl_config.py). The
    deterministic path does NOT replace the model in general - it wins on
    machine-generated date tables and loses everywhere a date needs its own
    real label, which is why this is a per-source setting and not a global
    switch.

    Raises ExtractionError (rather than swallowing it) if the LLM call
    itself fails, e.g. a missing API key for the configured LLM_PROVIDER -
    see run()'s per-document try/except, which turns that into a reported
    extraction_errors entry instead of a silent "0 candidates" that looks
    identical to "this document genuinely has no dates"."""
    result = extract_any(doc.url, doc.content, doc.content_type)
    kind = result.get("kind")

    if kind == "ics_feed":
        windows = result.get("windows", [])
        return windows, f"ics feed: {len(windows)} window(s)"

    if kind in ("html_page", "pdf_document", "image_page"):
        text = result.get("clean_markdown_full") or result.get("clean_markdown_preview", "")
        if not text.strip():
            return [], "empty document"

        if mode != "llm":
            static_dates, negative = _static_dates(text)
            # In auto, only an HTML page that is plainly a date TABLE takes the
            # deterministic path - there an LLM earns nothing (it reads the same
            # rows, one paid call per 20k chars, and silently drops some). A PDF
            # or image never does: its text came from OCR/vision, so what a date
            # MEANS is exactly the part only the model can supply.
            table_like = kind == "html_page" and len(static_dates) + negative >= STATIC_DATE_THRESHOLD
            if mode == "static" or table_like:
                note = f"static: {len(static_dates)} date(s)"
                if negative:
                    note += f", {negative} before year 1 skipped (not storable)"
                return [_window(date, label) for date in static_dates], note

        events = extract_dated_events(text, on_progress=on_progress)
        return (
            [_window(e["date"], e["label"], e.get("end", "")) for e in events],
            f"llm: {len(events)} event(s)",
        )

    return [], f"no extractor for kind '{kind}'"


def _existing_categories() -> List[str]:
    """Category paths that already hold pages, so a suggestion can reuse one
    instead of fragmenting the tree. Derived from disk rather than imported
    from main.py's _category_paths - main imports this module, so the
    dependency only goes one way."""
    root = approval.DATA_ROOT
    if not root.exists():
        return []
    # data.yaml lives at {category...}/{slug}/data.yaml, so dropping the slug
    # gives the category path at any nesting depth. A page sitting directly
    # under data/ has no category and relative_to() yields "." - not a name
    # anything should be offered for reuse.
    return sorted({
        path for path in (
            str(data_file.parent.parent.relative_to(root))
            for data_file in root.glob("*/**/data.yaml")
        )
        if path != "."
    })


def _suggested_category(source: CrawlSource, documents: List[CrawledDocument], title: str) -> str:
    """The category this source's candidates should be filed under.

    An explicitly configured category always wins. It's the create form's
    DEFAULT that this exists for: with no category typed, the route falls
    back to the source id, which is derived from the domain - so NASA's
    eclipse catalog filed itself under "eclipse-gsfc-nasa-gov" instead of
    anything a reader would look for. suggest_category has existed the whole
    time and simply had no caller.

    Only a suggestion: it lands on the candidate, which prefills the review
    form (see main.py's _target_category_for), so a human still confirms it
    before anything is written. Falls back to the configured value on any
    failure - a category guess must never be what fails a whole crawl.

    ponytail: deliberately NOT used for the auto-waved-through write below,
    which stays on source.category. This is an LLM call, so it re-rolls per
    run - re-verifying already-approved windows against a freshly guessed
    category could move a page out from under itself on any run. A human
    confirming the suggestion once, then setting it on the source (Edit in
    the crawl-sources table), is what makes it stick."""
    if source.category != source.id:
        return source.category
    text = next((doc.content[:2000].decode("utf-8", "replace") for doc in documents), "")
    try:
        return suggest_category(text, title, _existing_categories()) or source.category
    except ExtractionError:
        return source.category


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

    # Before the document loop: the deterministic extractor names its windows
    # after the page, so this has to exist by the time the first document is
    # extracted, not just when page.yaml is written.
    # An explicit subject_name in the config wins: with several sources
    # feeding one page, page.yaml is written by whichever approves first
    # (schreibe_page_yaml_falls_neu), so relying on the <title> makes a
    # shared page's heading depend on crawl order.
    subject_name = source.subject_name or _subject_name(documents, source.subject_slug)
    label = source.event_type_hint or subject_name
    category = _suggested_category(source, documents, subject_name)

    all_candidates: List[Dict[str, Any]] = []
    extraction_errors: List[str] = []
    for i, doc in enumerate(documents, start=1):
        doc_hash = staging.write_document(source.id, run_ts, doc.url, doc.content_type, doc.content)
        report("extracting", f"Document {i}/{len(documents)}: {doc.url}")
        report_page(doc.url, "extracting")
        try:
            windows, note = _windows_from_document(
                doc, label, source.extraction_mode, on_progress=lambda detail: report("extracting", detail)
            )
        except ExtractionError as e:
            extraction_errors.append(f"{doc.url}: {e}")
            report_page(doc.url, f"extraction failed: {str(e)[:80]}")
            continue
        report_page(doc.url, note)
        for window in windows:
            # Same job core/types.py's SourceResult.__post_init__ does for
            # adapter sources ("this is core's job, not each source
            # adapter's"), which the crawl path bypassed entirely - without
            # it store.merge_zeitfenster has no citations to union when a
            # second source reports the same window, so the per-window
            # citation merge silently no-ops for everything crawled.
            # source_urls is excluded from the content hash on purpose (see
            # core/content_hash.py), so this changes no candidate's identity.
            window.setdefault("source_urls", [doc.url])
            candidate = staging.build_candidate(
                source.id, source.subject_slug, window, doc_hash,
                subject_name=subject_name, category=category,
            )
            staging.write_candidate(source.id, run_ts, candidate)
            all_candidates.append(candidate)

    report("diffing", "Comparing against the page and the rejected set...")
    state = review_state.load(source.id)
    auto_waved_through, needs_review = review_state.diff(
        all_candidates, state, source.category, source.subject_slug
    )

    quelle = _default_quelle(source.seed_url)
    written = 0
    for candidate in auto_waved_through:
        try:
            approval.write_event(
                category=source.category,
                subject_slug=source.subject_slug,
                subject_name=subject_name,
                event=candidate["event"],
                quelle=quelle,
            )
            written += 1
        except approval.ApprovalError:
            continue

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
        "extraction_errors": extraction_errors,
    }
