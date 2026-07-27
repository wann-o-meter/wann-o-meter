#!/usr/bin/env python3
"""
Wann-Plattform Admin Dashboard
FastAPI + Jinja2 (SSR) + HTMX

Features:
- Configure and run scoped crawl sources (data/_sources/*.yaml)
- Review extracted candidates (approve/modify/reject) against their source
  document snapshot, with already-reviewed candidates auto-waved-through
- Maintain already-created pages (edit/delete/tag)
- Harvest registries (bulk entity lists from Wikidata)
"""

import asyncio
import html
import json
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import uvicorn
import yaml
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from core import approval, crawl_config, crawl_runner, review_state, staging, store, validate
from core.extraction import ExtractionError, suggest_tags
from sources import registry as harvest_registry

# Must stay in sync with lib/schema.ts's lizenzSchema (the "value" fields
# only - "label" is admin-UI-only help text, not part of the data model). The
# license is deliberately never guessed automatically: PLAN.md section 6
# requires an explicit decision per new source. Operators aren't expected to
# know copyright law, so each label states the concrete situation to match
# rather than an abstract legal term - order follows PLAN.md's decision tree,
# most-common civic-data case first.
# (mode, tooltip) for the Extraction dropdowns, built FROM EXTRACTION_MODES so
# a mode added there shows up in the UI even before it gets a description.
_EXTRACTION_MODE_HINTS = {
    "auto": "date tables read directly, everything else via the model",
    "llm": "always the model - best labels, one call per 20k chars",
    # The regex reads ISO and the "2001 Jun 21" catalog form only, so a German
    # page ("19. September bis 4. Oktober 2026") yields NOTHING under static -
    # reported as "static: 0 date(s)", which looks the same as a page with no
    # dates at all. Say so here rather than let it be discovered by a run.
    "static": "regex only, never the model - ISO dates (2026-09-19) only, NOT '19. September'",
}
EXTRACTION_MODE_OPTIONS = [
    (mode, _EXTRACTION_MODE_HINTS.get(mode, "")) for mode in crawl_config.EXTRACTION_MODES
]

LICENSE_OPTIONS = [
    {
        "value": "official_par5",
        "label": "Official work - law, regulation, official government notice (free, §5 UrhG)",
    },
    {
        "value": "dl_de_by",
        "label": "Official German open-data portal (GovData, DWD, destatis - free with attribution)",
    },
    {
        "value": "cc_by",
        "label": "Source explicitly states Creative Commons Attribution (CC-BY)",
    },
    {
        "value": "tos_checked",
        "label": "Private source - you read its Terms of Service and reuse is allowed",
    },
    {
        "value": "permission_granted",
        "label": "Private source - you emailed and got explicit permission",
    },
    {
        "value": "own_derivation",
        "label": "Your own calculation/derivation - no copied third-party data",
    },
]

LICENSE_VALUES = {option["value"] for option in LICENSE_OPTIONS}

# Matches core/crawler.py's sniff_format() labels - what a crawl source's
# `formats` field can filter on.
CRAWL_FORMAT_OPTIONS = ["html", "pdf", "ics", "image"]

# Seeds the category datalist so an operator without a house style guide has
# something to reuse instead of inventing a near-duplicate name (see
# RESERVED_CATEGORIES below for why fragmentation matters) - kept deliberately
# short; real usage (via _category_paths()) is the actual source of truth
# going forward, this just gives the very first pages somewhere to start.
SUGGESTED_CATEGORIES = ["politik"]

load_dotenv()



class PipelineState:
    """Tracks in-flight crawl_sources runs (background task + polling) -
    replaces the old CrawlerState/SeedRun bookkeeping entirely. There's no
    more in-memory discovered/scraped/accepted state to track: crawl ->
    extract -> stage -> diff -> write now runs as one background operation
    per source (core/crawl_runner.py, core/runner.py), landing directly in
    pipeline/staging/ + review-state/ + data/ rather than in memory."""
    def __init__(self):
        self.running_sources: Set[str] = set()
        self.errors: Dict[str, str] = {}
        self.last_result: Dict[str, dict] = {}
        self.progress: Dict[str, str] = {}
        # {source_id: {url: status}} for the most recent run of each source,
        # in insertion order (crawl order). Deliberately NOT cleared when a
        # run finishes - it's the per-page record the crawl-sources table
        # shows afterwards, and it's the only place the URLs that got
        # dropped (robots, fetch error, wrong format) exist at all; staging/
        # only ever holds the survivors. Lost on restart, which is fine: it
        # falls back to the staged documents then (see _source_pages).
        self.pages: Dict[str, Dict[str, str]] = {}

    def to_dict(self) -> dict:
        return {
            "is_running": bool(self.running_sources),
            "running_sources": sorted(self.running_sources),
        }


state = PipelineState()

app = FastAPI(title="Wann-Plattform Admin")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Exposed as globals rather than passed per route, so _base.html can render
# every <datalist> once and EVERY form gets them - the three copies these
# replace lived in three templates, which is why the crawl-source edit row
# had category suggestions but the page-title and page-slug fields beside it
# silently had none. Read straight from disk on each render, same philosophy
# as _list_created_pages(); this is a local admin tool, not a hot path.
templates.env.globals.update(
    all_categories=lambda: _category_suggestions(),
    all_tags=lambda: _all_tags(),
    all_page_titles=lambda: sorted({p["title"] for p in _list_created_pages()}),
    all_page_slugs=lambda: sorted({p["slug"] for p in _list_created_pages()}),
    extraction_mode_options=EXTRACTION_MODE_OPTIONS,
)

# Backs the site's dynamic /{category-path}/{slug}/ routes (lib/pages.ts
# reads the same tree via `join(process.cwd(), "data")` from the repo root,
# src/pages/[...path].astro renders it). A category can nest up to
# MAX_CATEGORY_DEPTH "/"-joined segments deep (data/sport/fussball/
# bundesliga/{slug}/ -> /sport/fussball/bundesliga/{slug}/) - each non-
# reserved top-level folder under data/ is the root of one category tree.
REPO_ROOT = Path(__file__).parent.parent
DATA_ROOT = REPO_ROOT / "data"

# Must stay in sync with lib/pages.ts's RESERVED_CATEGORIES - these top-level
# data/ folder names are already owned by the site's hardcoded categories, so
# a page can't be created under them (would collide with an existing route).
# Checked against segment 1 only.
RESERVED_CATEGORIES = {
    "kalender", "urlaubsfenster", "feiertage", "presets",
    "seiten", "themen", "api", "feeds", "impressum", "datenschutz", "schema",
}

# Must stay in sync with lib/pages.ts's RESERVED_AT_ANY_DEPTH - "tag" is
# reserved as a category segment at ANY depth (not just segment 1), since
# it's used as a route suffix (src/pages/themen/[tag].astro).
RESERVED_AT_ANY_DEPTH = {"tag"}

# Must stay in sync with lib/pages-schema.ts's MAX_CATEGORY_DEPTH.
MAX_CATEGORY_DEPTH = 4

# Allowlist for /pages/{full_path}/delete's return_to - the pages that render
# its Delete button (see _pages_table.html), matched exactly rather than
# blocklisted, so no "starts with a single /" style check has to anticipate
# every open-redirect trick (protocol-relative "//", backslash variants a
# browser treats the same way, etc).
#
# "/" is the dashboard, which includes _pages_table.html too - leaving it out
# didn't fail closed in a visible way, it silently bounced every delete from
# the dashboard to /crawl-sources. Adding a page that renders the table means
# adding it here.
_SAFE_RETURN_TO = re.compile(r"^/$|^/(?:crawl-sources|review)(?:/[^/]+)?/?$")


def _slugify(text: str) -> str:
    text = text.lower().strip()
    for umlaut, ascii_form in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}.items():
        text = text.replace(umlaut, ascii_form)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "page"


def _slugify_category_path(category: str) -> List[str]:
    """Splits an operator-typed category path ("Sport/Fußball/Bundesliga")
    on "/" and slugifies each segment independently - never slugify before
    splitting, that would turn "/" into "-" and collapse the hierarchy.
    Matches lib/pages-schema.ts's per-segment validation."""
    return [_slugify(seg) for seg in category.split("/") if seg.strip()]


def _validate_category_segments(segments: List[str]) -> Optional[str]:
    """Returns an error message if the (already-slugified) category path is
    invalid, else None. Mirrors lib/pages.ts's reserved-name handling
    (segment 1 vs. "tag" at any depth) and lib/pages-schema.ts's max-depth
    rule, so an operator gets the same rejection the site's build would
    apply anyway, just earlier and with a friendlier message."""
    if not segments:
        return "Category must not be empty."
    if len(segments) > MAX_CATEGORY_DEPTH:
        return f"Category path is too deep (max {MAX_CATEGORY_DEPTH} segments, got {len(segments)})."
    if segments[0] in RESERVED_CATEGORIES:
        return f"'{segments[0]}' is a reserved category name (already used by an existing site section)."
    for segment in segments:
        if segment in RESERVED_AT_ANY_DEPTH:
            return f"'{segment}' is a reserved segment name and can't be used at any depth."
    return None


def _walk_pages(segments: List[str], directory: Path, out: List[tuple[str, Path]]) -> None:
    """Recursion helper for _iter_pages() - see there for the contract."""
    for entry in sorted(directory.iterdir()):
        if not entry.is_dir():
            continue
        page_yaml = entry / "page.yaml"
        data_yaml = entry / "data.yaml"
        if page_yaml.exists() and data_yaml.exists():
            out.append(("/".join(segments), entry))
            continue
        if entry.name in RESERVED_AT_ANY_DEPTH or len(segments) >= MAX_CATEGORY_DEPTH:
            continue
        _walk_pages(segments + [entry.name], entry, out)


def _iter_pages() -> List[tuple[str, Path]]:
    """Recursively walks data/, skipping reserved top-level segments and any
    "tag"-named segment at any depth, yielding (category_path, page_folder)
    for every folder that's a page leaf (page.yaml + data.yaml present).
    category_path is the "/"-joined slug path matching lib/pages.ts's
    Page.category field (e.g. "sport/fussball/bundesliga"). Cheap enough for
    the handful of pages this admin tool deals with - no index file to keep
    in sync."""
    if not DATA_ROOT.exists():
        return []
    out: List[tuple[str, Path]] = []
    for entry in sorted(DATA_ROOT.iterdir()):
        if entry.is_dir() and entry.name not in RESERVED_CATEGORIES and entry.name not in RESERVED_AT_ANY_DEPTH:
            _walk_pages([entry.name], entry, out)
    return out


def _category_paths() -> List[str]:
    """Every distinct category path that directly holds pages (leaf
    categories, not every intermediate node) - mirrors lib/pages.ts's
    getAllCategories()."""
    return sorted({category_path for category_path, _ in _iter_pages()})


def _category_name_for(category_path: str) -> str:
    """Reads the display-name chain for a "/"-joined slug path, joining each
    segment's own data/{...}/_category.yaml name (see
    categoryMetaSchema/getCategoryMeta() in lib) with "/", e.g.
    "sport/fussball/bundesliga" -> "Sport/Fußball/Bundesliga". Falls back to
    a capitalized slug for any segment that predates this file or never got
    one. For a single-segment path this is identical to the old (pre-nesting)
    behaviour."""
    accumulated = DATA_ROOT
    names = []
    for slug in category_path.split("/"):
        accumulated = accumulated / slug
        meta_path = accumulated / "_category.yaml"
        name = None
        if meta_path.exists():
            try:
                meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
                candidate = meta.get("name") if isinstance(meta, dict) else None
                if isinstance(candidate, str) and candidate.strip():
                    name = candidate.strip()
            except Exception:
                pass
        names.append(name or (slug[:1].upper() + slug[1:]))
    return "/".join(names)


def _all_tags() -> List[str]:
    """Every tag already used across all page.yaml files - shown as a
    datalist (like _category_suggestions()) so an operator can reuse one
    instead of typing a near-duplicate, and fed to the LLM tag-suggestion
    prompt so it prefers reusing these over inventing new ones."""
    tags: Set[str] = set()
    for _category_path, folder in _iter_pages():
        page_path = folder / "page.yaml"
        try:
            page = yaml.safe_load(page_path.read_text(encoding="utf-8"))
            tags.update(page.get("tags", []) if isinstance(page, dict) else [])
        except Exception:
            continue
    return sorted(tags)


def _category_suggestions() -> List[str]:
    """Existing categories' real display names (what's actually in use) plus
    the small curated seed list - shown as a datalist so an operator can
    reuse a name instead of inventing a near-duplicate one. Suggests the
    display name (not the slug/path) since that's what the operator should
    be typing - _slugify_category_path() derives a consistent folder/URL
    path from it either way, first time or on reuse."""
    existing = set(_category_paths())
    paths = existing | set(SUGGESTED_CATEGORIES)
    return sorted({_category_name_for(path) for path in paths})


def _write_category_meta_if_new(category: str) -> None:
    """Writes data/{seg1}/_category.yaml, data/{seg1}/{seg2}/_category.yaml,
    ... for every NEW segment along a (possibly multi-level) category path
    an operator typed (e.g. "Sport/Fußball/Bundesliga" writes all three
    levels' _category.yaml the first time each is seen), capturing that
    segment's OWN typed text as its display name - not the full path, so
    lib/pages.ts's getCategoryMeta() shows "Bundesliga" for that node, not
    "Sport/Fußball/Bundesliga". Never overwrites an existing _category.yaml
    (an operator editing the name later should edit the file directly, not
    have it silently reset by the next unrelated page)."""
    typed_segments = [seg.strip() for seg in category.split("/") if seg.strip()]
    accumulated = DATA_ROOT
    for typed in typed_segments:
        accumulated = accumulated / _slugify(typed)
        meta_path = accumulated / "_category.yaml"
        if meta_path.exists():
            continue
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w", encoding="utf-8") as f:
            yaml.dump({"name": typed}, f, allow_unicode=True, sort_keys=False)


def _list_created_pages() -> List[dict]:
    """For the dashboard's overview card - reads straight from disk (source
    of truth), not from in-memory state, so it survives a server restart."""
    pages = []
    for category_path, folder in _iter_pages():
        page_path = folder / "page.yaml"
        data_path = folder / "data.yaml"
        try:
            page_meta = yaml.safe_load(page_path.read_text(encoding="utf-8"))
            page_data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        source = page_data.get("source") or {}
        if isinstance(source, list):
            source = source[0] if source else {}
        pages.append({
            "category": category_path,
            "category_display": _category_name_for(category_path),
            "slug": folder.name,
            "title": page_meta.get("title", folder.name),
            "description": page_meta.get("description", ""),
            "tags": page_meta.get("tags", []),
            "url": source.get("url", ""),
            "lizenz": source.get("license", ""),
        })
    return pages

def _harvest_registry_status() -> List[dict]:
    """One row per entity_class configured in pipeline/config/registries.yaml,
    joined with whatever pipeline/data/registries/<entity_class>.json already
    holds - reads straight from disk (source of truth), not from in-memory
    state, so it survives a server restart, same as _list_created_pages()."""
    rows = []
    for entity_class, cfg in harvest_registry.load_registries_config().items():
        path = harvest_registry.OUTPUT_DIR / f"{entity_class}.json"
        count = None
        fetched_at = None
        if path.exists():
            try:
                entities = json.loads(path.read_text(encoding="utf-8"))
                count = len(entities)
                fetched_at = entities[0]["fetched_at"] if entities else None
            except Exception:
                pass
        rows.append({
            "entity_class": entity_class,
            "target_kinds": cfg.get("target_kinds", []),
            "count": count,
            "fetched_at": fetched_at,
            "running": entity_class in harvest_registry_state.running,
            "error": harvest_registry_state.errors.get(entity_class),
        })
    return rows


def _latest_run_ts(source_id: str) -> Optional[str]:
    source_dir = staging.STAGING_ROOT / source_id
    if not source_dir.exists():
        return None
    run_dirs = sorted((p.name for p in source_dir.iterdir() if p.is_dir()), reverse=True)
    return run_dirs[0] if run_dirs else None


def _source_pages(source_id: str) -> List[Dict[str, str]]:
    """[{"url", "status"}] for the crawl source's most recent run, in crawl
    order - shown inline in the crawl-sources table (expandable row) and
    refreshed live from the same /status poll while a run is in flight.

    Prefers state.pages, which is the ONLY record of URLs that never became
    documents (robots-blocked, fetch failure, filtered-out format) - a
    staging-only view showed just the survivors, so a crawl that reached 40
    pages and kept 1 was indistinguishable from one that only ever found 1.
    Falls back to the staged documents (all "crawled" by definition) when
    state.pages is empty, i.e. after a restart or for a run from a previous
    process."""
    live = state.pages.get(source_id)
    if live:
        return [{"url": url, "status": status} for url, status in live.items()]

    run_ts = _latest_run_ts(source_id)
    if run_ts is None:
        return []
    return [{"url": doc["url"], "status": "crawled"} for doc in staging.list_documents(source_id, run_ts)]


def _known_source_ids() -> List[str]:
    """Every source_id with either a data/_sources/*.yaml config or an
    existing staging/ directory - the latter covers data/_sources-based
    automated sources too (e.g. schulferien_kmk, run via `python -m
    core.runner`), since both subsystems write into the same
    pipeline/staging/ + review-state/ structure (Decision B: one unified
    review queue regardless of which subsystem produced a candidate)."""
    ids = set(crawl_config.load_all_crawl_sources().keys())
    if staging.STAGING_ROOT.exists():
        ids.update(p.name for p in staging.STAGING_ROOT.iterdir() if p.is_dir())
    return sorted(ids)


def _is_known_source_id(source_id: str) -> bool:
    """Allowlist check for the /review/{source_id}/... routes below -
    source_id comes straight from the URL, and every one of those routes
    uses it to build filesystem paths (staging.STAGING_ROOT / source_id /
    ..., review-state/<source_id>.yaml). Without this, a request like
    /review/../../../../etc/x could read or write outside pipeline/staging
    and pipeline/review-state entirely. Checking directory-name equality
    against _known_source_ids() (real crawl_sources configs or existing
    staging/ subdirectories) is an allowlist, not a blocklist - it rejects
    "../" the same way it rejects any other string that isn't a real,
    already-existing source_id, rather than trying to enumerate every
    traversal trick."""
    return source_id in _known_source_ids()


def _pending_candidates_for(source_id: str) -> List[dict]:
    """Candidates from source_id's most recent run whose content_hash has no
    decision yet - recomputed live from disk each call rather than cached,
    same "reads straight from disk" philosophy as _list_created_pages()."""
    run_ts = _latest_run_ts(source_id)
    if run_ts is None:
        return []
    candidates_dir = staging.STAGING_ROOT / source_id / run_ts / "candidates"
    if not candidates_dir.exists():
        return []
    state = review_state.load(source_id)
    pending = []
    for path in sorted(candidates_dir.glob("*.yaml")):
        candidate = yaml.safe_load(path.read_text(encoding="utf-8"))
        category = _target_category_for(candidate)
        slug = candidate["subject_slug"]
        # Same two lookups core/review_state.diff() makes, and in the same
        # order - the page is the record, the rejected set is the negative.
        # These have to agree: this is a SECOND implementation of "is it
        # pending", and if it drifted the UI would offer rows a run would
        # wave straight through.
        if review_state.already_approved(category, slug, candidate["event"]):
            continue
        if review_state.is_rejected(state, slug, candidate["event"]):
            continue
        candidate["run_ts"] = run_ts
        pending.append(candidate)
    return pending


def _review_queue() -> List[dict]:
    return [c for source_id in _known_source_ids() for c in _pending_candidates_for(source_id)]


def _next_review_candidate(exclude: Optional[tuple] = None) -> Optional[dict]:
    """First pending candidate in the queue, other than `exclude` - lets a
    reviewer chain straight from one decision (or an explicit Skip) to the
    next one instead of bouncing back through /review's list every time."""
    for candidate in _review_queue():
        if exclude and (candidate["source_id"], candidate["candidate_id"]) == exclude:
            continue
        return candidate
    return None


_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}
_ISO_DATE_RE = re.compile(r"^(-?\d{1,4})-(\d{2})-(\d{2})$")


def _human_date_variant(iso_date: str) -> Optional[str]:
    """"1901-01-07" -> "1901 Jan 07" - the format eclipse.gsfc.nasa.gov's
    catalog pages actually write dates in (verified against a real staged
    snapshot) - a source's own date formatting varies, so this is one
    extra guess alongside the plain ISO string, not a general parser."""
    m = _ISO_DATE_RE.match(iso_date)
    if not m:
        return None
    year, month, day = m.groups()
    abbr = _MONTH_ABBR.get(int(month))
    return f"{year} {abbr} {day}" if abbr else None


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_EMPHASIS_RE = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*", re.DOTALL)
_MD_HEADING_MARKER_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_BLANK_LINE_RUN_RE = re.compile(r"\n{2,}")


def _plaintext_from_markdown(md: str) -> str:
    """The staged .md snapshot (core/sniff.py's html_to_markdown) keeps
    markdown syntax - [label](url) links, **bold**, # headings - which is
    visual noise for a dense data table (e.g. the eclipse catalog: every
    row's image/plot/search links turn into bracket-and-paren clutter
    around the actual date/time text). The review UI wants plain,
    scannable text, not literal markdown source - strips the syntax back
    to just its human-readable text and collapses the blank-line runs left
    behind by stripped block-level tags (each one otherwise costs a whole
    scroll of vertical space for nothing).

    Trailing whitespace is stripped per line BEFORE collapsing blank runs:
    a line left with just a lone space (common once a <td>/<a> tag around
    it is gone) isn't truly empty as text, so a naive "\\n{2,}" collapse
    alone would only remove every other blank line instead of the whole
    run - verified against a real staged eclipse.gsfc.nasa.gov snapshot,
    which has exactly this shape. Collapses down to exactly ONE blank line
    (not zero) between sections - a wall of text with no paragraph breaks
    at all is just as hard to scan as ten blank lines in a row."""
    text = _MD_LINK_RE.sub(r"\1", md)
    text = _MD_EMPHASIS_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _MD_HEADING_MARKER_RE.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANK_LINE_RUN_RE.sub("\n\n", text)
    return text.strip()


def _highlight_dates(text: str, dates: List[Optional[str]]) -> str:
    """Escapes `text` for safe HTML embedding, then wraps any occurrence of
    one of the candidate's own from/to dates - in ISO form or the
    human-readable variant above - in <mark>. Best-effort: a miss just
    means no highlight, the escaped text still renders either way, since
    input is always fully escaped first regardless of whether anything
    matched."""
    escaped = html.escape(text)
    patterns = []
    seen = set()
    for date in dates:
        if not date or date in seen:
            continue
        seen.add(date)
        patterns.append(re.escape(html.escape(date)))
        variant = _human_date_variant(date)
        if variant:
            patterns.append(re.escape(html.escape(variant)))
    if not patterns:
        return escaped
    return re.sub("(" + "|".join(patterns) + ")", r"<mark>\1</mark>", escaped)


def _date_variants(date: Optional[str]) -> List[str]:
    """Every spelling of one date the review UI knows how to look for - the
    ISO string plus _human_date_variant's rendering. Shared so the
    single-candidate highlight and the whole-document one can never drift
    into finding different things on the same page."""
    if not date:
        return []
    variants = [date]
    human = _human_date_variant(date)
    if human:
        variants.append(human)
    return variants


def _highlight_candidates(text: str, candidates: List[dict], source_id: str) -> str:
    """Escapes `text`, then turns every date belonging to a still-pending
    candidate into a selectable checkbox in place.

    This is what makes a 200-row date table reviewable: the rows are already
    in front of you in their real context, so selecting the wrong ones and
    acting on them shouldn't mean finding them again in a separate list. One
    click selects a date, several clicks select several, and the bar at the
    bottom approves or rejects the whole selection - single and bulk are the
    same gesture, not two screens.

    ponytail: a <label> wrapping a hidden checkbox, so selection needs no JS
    at all - the browser does it. The only script on the page keeps the
    counter and the disabled state honest. The checkbox name and value match
    /review's table exactly, so both post to the same bulk route.

    Longest-first alternation matters: "1901 Jan 07" and a bare "1901" would
    otherwise let the shorter pattern win and swallow the row. A date shared
    by two candidates selects the first - they are duplicates of each other,
    and review is per page now, so approving one clears both."""
    escaped = html.escape(text)
    by_pattern: Dict[str, dict] = {}
    for candidate in candidates:
        event = candidate.get("event") or {}
        for date in (event.get("from"), event.get("to")):
            for variant in _date_variants(date):
                by_pattern.setdefault(html.escape(variant), candidate)
    if not by_pattern:
        return escaped

    def _hit(match: re.Match) -> str:
        candidate = by_pattern[match.group(0)]
        candidate_id = html.escape(candidate["candidate_id"])
        name = html.escape(str((candidate.get("event") or {}).get("name") or ""))
        base = f"/review/{html.escape(source_id)}/{candidate_id}"
        return (
            f'<label class="date-hit" title="{name}">'
            f'<input type="checkbox" name="selected" value="{html.escape(source_id)}/{candidate_id}">'
            f'<span>{match.group(0)}</span>'
            f'<a class="date-edit" href="{base}" title="Open this one on its own to edit it">&#9998;</a>'
            # formaction, not a nested <form> - HTML forbids nesting, and this
            # button lives inside the bulk form that wraps the whole document.
            # It re-points just this submit at the single-candidate route,
            # which picks up the form's return_to=document and comes straight
            # back here. formnovalidate so an empty license can't block it: a
            # rejection writes nothing and needs none.
            f'<button type="submit" class="date-reject" formaction="{base}/reject" '
            f'formnovalidate title="Reject this one now">&#10005;</button>'
            "</label>"
        )

    alternation = "|".join(re.escape(p) for p in sorted(by_pattern, key=len, reverse=True))
    return re.sub(alternation, _hit, escaped)




def _load_candidate(source_id: str, run_ts: str, candidate_id: str) -> Optional[dict]:
    """source_id must already be validated by the caller (see
    _is_known_source_id) - this only additionally guards candidate_id
    (also straight from the URL): resolve()+parent-check the same way
    /staging-document does, so a "../../../etc/passwd"-shaped candidate_id
    can't escape the run's candidates/ directory."""
    candidates_dir = (staging.STAGING_ROOT / source_id / run_ts / "candidates").resolve()
    path = (candidates_dir / f"{candidate_id.replace(':', '_')}.yaml").resolve()
    if candidates_dir not in path.parents or not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run_crawl_source_and_record(source_id: str) -> None:
    def report(msg: str) -> None:
        state.progress[source_id] = msg

    def report_page(url: str, status: str) -> None:
        state.pages.setdefault(source_id, {})[url] = status

    try:
        source = crawl_config.load_all_crawl_sources().get(source_id)
        if source is None:
            raise ValueError(f"Unknown crawl source '{source_id}'")
        state.pages[source_id] = {}
        result = crawl_runner.run(source, on_progress=report, on_page=report_page)
        state.last_result[source_id] = result
        state.errors.pop(source_id, None)
    except Exception as e:
        state.errors[source_id] = str(e)[:300]
    finally:
        state.running_sources.discard(source_id)
        state.progress.pop(source_id, None)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """The published pages - the end of the Sources -> Review -> Pages
    pipeline, and the thing an operator actually comes back to look at. The
    harvest registry used to share this page, which made the landing screen
    a mix of two unrelated concerns; it has /harvest to itself now."""
    return templates.TemplateResponse(request, "dashboard.html", {
        "active_nav": "pages",
        "state": state.to_dict(),
        "pages": _list_created_pages(),
        "license_options": LICENSE_OPTIONS,
        "category_suggestions": _category_suggestions(),
        "tag_suggestions": _all_tags(),
        "review_queue_count": len(_review_queue()),
    })


@app.get("/harvest", response_class=HTMLResponse)
async def harvest_view(request: Request):
    """Stage 1 of the entity-first harvest pipeline (see sources/registry.py) -
    fetches a known entity class's registry into pipeline/data/registries/.
    Stages 2-7 don't exist yet, so nothing downstream consumes it: its one
    designed bridge into the crawler (registry.load_registry_domains) has no
    caller. Kept and given its own page rather than mixed into the pages
    dashboard, so the pipeline nav reads as the pipeline."""
    return templates.TemplateResponse(request, "harvest.html", {
        "active_nav": "harvest",
        "state": state.to_dict(),
        "harvest_registries": _harvest_registry_status(),
    })


@app.get("/crawl-sources", response_class=HTMLResponse)
async def crawl_sources_list(request: Request):
    return templates.TemplateResponse(request, "crawl_sources.html", {
        "active_nav": "crawl-sources",
        "state": state.to_dict(),
        "sources": crawl_config.load_all_crawl_sources(),
        "running_sources": state.running_sources,
        "errors": state.errors,
        "last_result": state.last_result,
        "progress": state.progress,
        "category_suggestions": _category_suggestions(),
        "format_options": CRAWL_FORMAT_OPTIONS,
    })


@app.get("/crawl-sources-table", response_class=HTMLResponse)
async def crawl_sources_table(request: Request):
    """htmx refresh target after a Run click (see crawl_sources.html's JS
    poll) - same "re-render the whole table from the server" approach as
    the old harvest registry table, so count/error/button state all come
    from one source of truth."""
    return templates.TemplateResponse(request, "_crawl_sources_table.html", {
        "sources": crawl_config.load_all_crawl_sources(),
        "running_sources": state.running_sources,
        "errors": state.errors,
        "last_result": state.last_result,
        "progress": state.progress,
    })


@app.post("/crawl-sources/{source_id}/run")
async def run_crawl_source(source_id: str):
    sources = crawl_config.load_all_crawl_sources()
    if source_id not in sources:
        return JSONResponse({"error": f"Unknown crawl source '{source_id}'"}, status_code=404)
    if source_id in state.running_sources:
        return JSONResponse({"error": "This source is already running."}, status_code=409)
    state.running_sources.add(source_id)
    threading.Thread(target=_run_crawl_source_and_record, args=(source_id,), daemon=True).start()
    return JSONResponse({"status": "started", "source_id": source_id})


@app.get("/crawl-sources/{source_id}/status")
async def crawl_source_status(source_id: str):
    """Polled by crawl_sources.html's Run button while a crawl is in
    flight - same reasoning as the harvest registry status poll: the POST
    above returns almost instantly, the real crawl runs in the background
    thread."""
    return JSONResponse({
        "running": source_id in state.running_sources,
        "error": state.errors.get(source_id),
        "result": state.last_result.get(source_id),
        "progress": state.progress.get(source_id),
        # Carried on this same poll rather than a second endpoint/timer -
        # two polls against one source would just double the request rate
        # to show two halves of the same run.
        "pages": _source_pages(source_id),
    })


@app.post("/crawl-sources/{source_id}/delete")
async def delete_crawl_source(source_id: str):
    """Removes data/_sources/{source_id}.yaml only - review-state
    history and anything already written to data/ are kept, same reasoning
    as /pages/{path}/delete never touching review-state. A source can be
    re-added later (see create_crawl_source) and picks its history back up
    from review-state, since that's keyed by content_hash, not by whether
    the config file exists."""
    sources = crawl_config.load_all_crawl_sources()
    source = sources.get(source_id)
    if source is None:
        return HTMLResponse("Not found", status_code=404)
    if source_id in state.running_sources:
        return HTMLResponse("This source is currently running - wait for it to finish first.", status_code=409)

    source.config_path.unlink()
    state.errors.pop(source_id, None)
    state.last_result.pop(source_id, None)
    return RedirectResponse("/crawl-sources", status_code=303)


def _derive_path_prefix(seed_path: str) -> str:
    """A seed URL that points at one specific page (e.g. .../catalog/
    page.html - last segment looks like a filename) would scope the crawl
    to just that exact path if used as-is (path_prefix is a startswith
    check - see core/crawler.py's in_scope()), defeating discovery of any
    sibling page entirely. Scope to the parent directory instead in that
    case; a seed URL that already looks like a section root (no "." in the
    last segment, e.g. .../veranstaltungen) is used as-is."""
    if seed_path in ("", "/"):
        return ""
    last_segment = seed_path.rsplit("/", 1)[-1]
    if "." in last_segment:
        parent = seed_path.rsplit("/", 1)[0]
        return parent if parent not in ("", "/") else ""
    return seed_path


@app.post("/crawl-sources/new")
async def create_crawl_source(
    seed_url: str = Form(...),
    id: str = Form(""),
    category: str = Form(""),
    allowed_domains: str = Form(""),
    path_prefix: str = Form(""),
    max_depth: int = Form(crawl_config.DEFAULT_MAX_DEPTH),
    formats: List[str] = Form(["html"]),
    subject_slug: str = Form(""),
    subject_name: str = Form(""),
    event_type_hint: str = Form(""),
    schedule: str = Form("manual"),
    extraction_mode: str = Form(crawl_config.DEFAULT_EXTRACTION_MODE),
    auto_approve_ics: bool = Form(False),
):
    """Writes a new data/_sources/{id}.yaml from the
    dashboard - the file stays the actual source of truth (git-diffable,
    same as a data/_sources/ file), this just saves hand-editing it. Only seed_url
    is required: id/category/allowed_domains/path_prefix are all derived
    from it when left blank, so pasting a URL and clicking Add is enough -
    the template's Advanced section lets an operator override any of them.
    Reuses crawl_config's own _parse() as the validator so a source
    accepted here is guaranteed to also load cleanly for a real crawl run."""
    seed_url = seed_url.strip()
    parsed = urlparse(seed_url)
    if not parsed.scheme or not parsed.netloc:
        return HTMLResponse("Seed URL must be a full URL, e.g. https://example.org/veranstaltungen.", status_code=400)
    domain = parsed.netloc.removeprefix("www.")

    # _slugify() itself falls back to "page" for a blank string (see its own
    # docstring-free `or "page"`), which would mask "left blank" here - check
    # blank-ness before slugifying, not after.
    if id.strip():
        id = _slugify(id)
    else:
        # Two seed URLs on the same domain (e.g. /solar and /lunar sections)
        # would otherwise both derive the same domain-only id - fall back to
        # domain+first-path-segment before giving up and asking for a
        # custom id.
        id = _slugify(domain)
        if (crawl_config.CRAWL_SOURCES_DIR / f"{id}.yaml").exists():
            path_segments = [s for s in parsed.path.split("/") if s]
            if path_segments:
                id = f"{id}-{_slugify(path_segments[0])}"
    path = crawl_config.CRAWL_SOURCES_DIR / f"{id}.yaml"
    if path.exists():
        return HTMLResponse(
            f"A crawl source '{id}' already exists - set a custom ID under Advanced options "
            "(this domain already has a source at that same path).",
            status_code=409,
        )

    category_path = "/".join(_slugify_category_path(category or id))
    validation_error = _validate_category_segments(category_path.split("/") if category_path else [])
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)

    domains = [d.strip() for d in allowed_domains.split(",") if d.strip()] or [domain]
    scope = {"allowed_domains": domains}
    derived_path_prefix = path_prefix.strip() or _derive_path_prefix(parsed.path)
    if derived_path_prefix:
        scope["path_prefix"] = derived_path_prefix

    raw = {
        "id": id,
        "seed_url": seed_url,
        "category": category_path,
        # Blank means "its own page", i.e. the id - the same default
        # crawl_config._parse applies. A shared value is what aggregates
        # several sources into one page.
        "subject_slug": _slugify(subject_slug) if subject_slug.strip() else id,
        "subject_name": subject_name.strip(),
        "scope": scope,
        "max_depth": max_depth,
        "formats": formats,
        "event_type_hint": event_type_hint.strip(),
        "schedule": schedule.strip() or "manual",
        "extraction_mode": extraction_mode,
        "auto_approve_ics": auto_approve_ics,
    }
    try:
        crawl_config._parse(raw, path)
    except crawl_config.CrawlConfigError as e:
        return HTMLResponse(str(e), status_code=400)

    crawl_config.CRAWL_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return RedirectResponse("/crawl-sources", status_code=303)


def _as_quelle_list(datei: Dict[str, Any]) -> List[Dict[str, Any]]:
    """lib/pages-schema.ts accepts `source` as either a bare object or a
    list; store.append_quelle only handles the list. Every page written
    before that list form existed still has the object on disk, so
    normalizing here is what makes merging a real page work rather than
    raising AttributeError halfway through."""
    quellen = datei.get("source") or []
    return [quellen] if isinstance(quellen, dict) else list(quellen)


def _migrate_page_folder(old_folder: Path, new_folder: Path, slug: str, category: str) -> Optional[str]:
    """Folds data/{old_category}/{old_slug}/ into data/{category}/{slug}/,
    returning why it couldn't be (nothing written) or None on success.

    One code path, no move-vs-merge branch: store.lade_oder_erstelle yields
    an empty skeleton when the target doesn't exist yet, so a plain move is
    just a merge into an empty file. merge_zeitfenster then does the real
    work - the same window from both sources keeps one entry and unions its
    citations, a different date range replaces - which is precisely the
    aggregation CrawlSource.subject_slug exists to enable.

    A missing old folder is success, not an error: a source's configured
    target can name a page it never actually wrote (nothing approved yet, or
    a config that drifted away from where its approvals really landed)."""
    old_data = old_folder / "data.yaml"
    if not old_data.exists():
        return None

    old_datei = yaml.safe_load(old_data.read_text(encoding="utf-8")) or {}
    datei = store.lade_oder_erstelle(new_folder / "data.yaml", slug, category)
    datei["source"] = _as_quelle_list(datei)

    store.merge_zeitfenster(datei, old_datei.get("windows") or [])
    for quelle in _as_quelle_list(old_datei):
        store.append_quelle(datei, quelle)
    # The moved windows keep their source_urls, and pageDataSchema's
    # superRefine fails the site build if one of those isn't in source[] -
    # so carrying the citations over is required, not politeness. Rewriting
    # subject also repairs a file whose slug no longer matches its folder.
    datei["subject"] = {"slug": slug, "category": category}

    try:
        validate.pruefe_subjekt_datei(datei)
    except validate.ValidationError as e:
        return f"The merged page would be invalid, nothing written:\n{e}"

    store.speichere(new_folder / "data.yaml", datei)
    # Copied rather than store.schreibe_page_yaml_falls_neu'd: that would
    # write a bare title and drop the description/tags a human set here. An
    # existing target page.yaml wins - it's the one already on the site.
    if not (new_folder / "page.yaml").exists() and (old_folder / "page.yaml").exists():
        shutil.copy(old_folder / "page.yaml", new_folder / "page.yaml")
    shutil.rmtree(old_folder)
    return None


@app.post("/crawl-sources/{source_id}/edit")
async def edit_crawl_source(
    source_id: str,
    category: str = Form(...),
    subject_slug: str = Form(...),
    subject_name: str = Form(""),
    event_type_hint: str = Form(""),
    extraction_mode: str = Form(""),
):
    """Changes where a crawl source writes - data/{category}/{subject_slug}/ -
    and migrates everything that already points at the old location, so
    aggregating two sources into one page costs no re-review.

    Editing these after creation is the whole point: subject_slug is how
    several sources aggregate (see CrawlSource.subject_slug), but it could
    only ever be set at create time, and getting it wrong meant living with
    a split page or re-approving every candidate by hand.

    Three things move together:
      - the config file, rewritten in place so untouched fields survive;
      - the data folder, moved or merged into the target page - this is the
        migration, because data.yaml IS the record of what is approved;
      - the rejected set, re-pointed at the new slug (review_state.repoint).

    Moving the folder used to be the easy half: the approved set also lived
    in review-state under a hash that included the slug, so a slug change
    orphaned every decision and had to re-hash them all, with a guard for
    when that failed. None of that exists now - the windows travel with the
    folder, and the rejections are a field rewrite that cannot fail.

    ponytail: no transaction log. Everything that can fail is checked before
    the first write, and only THIS source is locked out while running -
    another source writing into the same folder concurrently isn't."""
    sources = crawl_config.load_all_crawl_sources()
    source = sources.get(source_id)
    if source is None:
        return HTMLResponse("Not found", status_code=404)
    if source_id in state.running_sources:
        return HTMLResponse("This source is currently running - wait for it to finish first.", status_code=409)

    category_path = "/".join(_slugify_category_path(category))
    validation_error = _validate_category_segments(category_path.split("/") if category_path else [])
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)

    raw = yaml.safe_load(source.config_path.read_text(encoding="utf-8")) or {}
    raw.update({
        "category": category_path,
        # Deliberately NOT _slugify'd, unlike the create route: on an edit
        # the operator is matching another source's slug character for
        # character, and silently rewriting a typo into a valid-but-different
        # slug would quietly create a third page instead of saying so.
        # _parse's _SLUG_RE is the validator.
        "subject_slug": subject_slug.strip(),
        "subject_name": subject_name.strip(),
        "event_type_hint": event_type_hint.strip(),
    })
    # Whether this source reads dates with the regex or the model was settable
    # only at create time, so switching meant hand-editing the YAML. Omitted
    # rather than defaulted, so a form POST without the field (the other fields
    # here are edited by partial posts in the same way) leaves the mode alone
    # instead of silently resetting it to auto. _parse rejects an unknown mode.
    if extraction_mode:
        raw["extraction_mode"] = extraction_mode
    try:
        parsed = crawl_config._parse(raw, source.config_path)
    except crawl_config.CrawlConfigError as e:
        return HTMLResponse(str(e), status_code=400)

    if (category_path, parsed.subject_slug) != (source.category, source.subject_slug):
        old_folder = DATA_ROOT / source.category / source.subject_slug
        new_folder = DATA_ROOT / category_path / parsed.subject_slug
        error = _migrate_page_folder(old_folder, new_folder, parsed.subject_slug, category_path)
        if error:
            return HTMLResponse(error, status_code=400)

        review_state.save(source_id, review_state.repoint(review_state.load(source_id), parsed.subject_slug))
        # Staged candidates carry the OLD category+slug, so the queue would
        # look them up against a page that no longer holds them and offer
        # every one again. staging/ is gitignored working state the next run
        # rebuilds, so dropping it is cheaper than rewriting each candidate.
        shutil.rmtree(staging.STAGING_ROOT / source_id, ignore_errors=True)

    # ponytail: yaml.dump drops the file's comments - the same way the create
    # form once flattened a hand-written config. Preserving them needs ruamel;
    # re-add comments by hand after a UI edit until that's worth a dependency.
    source.config_path.write_text(yaml.dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return RedirectResponse("/crawl-sources", status_code=303)


@app.get("/review", response_class=HTMLResponse)
async def review_queue_view(request: Request):
    return templates.TemplateResponse(request, "review.html", {
        "active_nav": "review",
        "state": state.to_dict(),
        "queue": _review_queue(),
        "license_options": LICENSE_OPTIONS,
    })


@app.get("/review/{source_id}/document/{doc_hash}", response_class=HTMLResponse)
async def review_document(request: Request, source_id: str, doc_hash: str):
    """The whole staged document with every pending date highlighted and
    rejectable in place - the counterpart to the one-candidate-at-a-time
    view, for a source that is one big date table. Reviewing 200 rows by
    stepping through 200 separate pages loses the thing that makes a table
    readable: its neighbours."""
    if not _is_known_source_id(source_id) or not _DOC_HASH_RE.match(doc_hash):
        return HTMLResponse("Not found", status_code=404)
    run_ts = _latest_run_ts(source_id)
    documents_dir = staging.STAGING_ROOT / source_id / run_ts / "documents" if run_ts else None
    doc_path = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None) if documents_dir and documents_dir.exists() else None
    if doc_path is None or doc_path.suffix not in (".md", ".ics"):
        return HTMLResponse("Not found - only text snapshots can be reviewed inline.", status_code=404)

    candidates = [c for c in _pending_candidates_for(source_id) if c["document"] == doc_hash]
    raw_text = doc_path.read_text(encoding="utf-8")
    plain_text = _plaintext_from_markdown(raw_text) if doc_path.suffix == ".md" else raw_text

    return templates.TemplateResponse(request, "review_document.html", {
        "active_nav": "review",
        "state": state.to_dict(),
        "source_id": source_id,
        "doc_hash": doc_hash,
        "document_meta": staging.read_document_meta(source_id, run_ts, doc_hash),
        "document_html": _highlight_candidates(plain_text, candidates, source_id),
        "pending_count": len(candidates),
        "license_options": LICENSE_OPTIONS,
        # Shown so it's obvious which page a click here publishes to - the
        # whole selection lands in one data.yaml.
        "category": _target_category_for(candidates[0]) if candidates else "",
        "subject_slug": candidates[0]["subject_slug"] if candidates else "",
    })


@app.get("/review/{source_id}/{candidate_id}", response_class=HTMLResponse)
async def review_candidate_detail(request: Request, source_id: str, candidate_id: str):
    if not _is_known_source_id(source_id):
        return HTMLResponse("Not found", status_code=404)
    run_ts = _latest_run_ts(source_id)
    candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)

    doc_hash = candidate["document"]
    doc_meta = staging.read_document_meta(source_id, run_ts, doc_hash)
    documents_dir = staging.STAGING_ROOT / source_id / run_ts / "documents"
    doc_path = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None)
    is_text = doc_path is not None and doc_path.suffix in (".md", ".ics")
    document_html = None
    if is_text:
        event = candidate["event"]
        raw_text = doc_path.read_text(encoding="utf-8")
        plain_text = _plaintext_from_markdown(raw_text) if doc_path.suffix == ".md" else raw_text
        document_html = _highlight_dates(plain_text, [event.get("from"), event.get("to")])

    return templates.TemplateResponse(request, "_candidate_review.html", {
        "state": state.to_dict(),
        "source_id": source_id,
        "candidate": candidate,
        "document_meta": doc_meta,
        "document_html": document_html,
        "document_url": f"/staging-document/{source_id}/{run_ts}/{doc_hash}" if doc_path and not is_text else None,
        "license_options": LICENSE_OPTIONS,
        "category_suggestions": _category_suggestions(),
        "next_candidate": _next_review_candidate(exclude=(source_id, candidate_id)),
    })


_STAGING_DOCUMENT_MEDIA_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".gif": "image/gif", ".ics": "text/calendar", ".md": "text/markdown; charset=utf-8",
}


_DOC_HASH_RE = re.compile(r"^[0-9a-f]+$")


@app.get("/staging-document/{source_id}/{run_ts}/{doc_hash}")
async def get_staging_document(source_id: str, run_ts: str, doc_hash: str):
    """Serves one staged document snapshot for the review UI. All three
    path segments come straight from the URL: source_id is checked against
    the same allowlist as /review/{source_id}/... (_is_known_source_id),
    doc_hash is checked against the hex-only shape staging.write_document
    actually generates it in (rejects a glob/traversal payload before it
    ever reaches documents_dir.glob()), and the resolve()+parent-check
    catches anything else (e.g. a "../"-laden run_ts)."""
    if not _is_known_source_id(source_id) or not _DOC_HASH_RE.match(doc_hash):
        return HTMLResponse("Not found", status_code=404)
    documents_dir = (staging.STAGING_ROOT / source_id / run_ts / "documents").resolve()
    if staging.STAGING_ROOT.resolve() not in documents_dir.parents:
        return HTMLResponse("Not found", status_code=404)
    match = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None) if documents_dir.exists() else None
    if match is None:
        return HTMLResponse("Not found", status_code=404)
    media_type = _STAGING_DOCUMENT_MEDIA_TYPES.get(match.suffix, "application/octet-stream")
    return Response(content=match.read_bytes(), media_type=media_type)


def _redirect_to_next_review(source_id: str, candidate_id: str) -> RedirectResponse:
    """Chains straight from an approve/modify/reject decision to whatever's
    next in the queue (see _next_review_candidate) instead of bouncing
    through /review's list every time - falls back to the list once the
    queue is empty."""
    next_candidate = _next_review_candidate(exclude=(source_id, candidate_id))
    if next_candidate:
        return RedirectResponse(f"/review/{next_candidate['source_id']}/{next_candidate['candidate_id']}", status_code=302)
    return RedirectResponse("/review", status_code=302)


def _quelle_for_candidate(source_id: str, candidate: dict, license: str) -> dict:
    run_ts = candidate.get("run_ts") or _latest_run_ts(source_id)
    url = ""
    if run_ts:
        try:
            url = staging.read_document_meta(source_id, run_ts, candidate["document"]).get("url", "")
        except FileNotFoundError:
            pass
    return {
        "url": url,
        "license": license,
        "retrieved_at": datetime.now(timezone.utc).date().isoformat(),
        "extraction": "llm",
    }


def _target_category_for(candidate: dict) -> str:
    """The category an approval should file this candidate under: the one its
    source configured, not the subject slug. Both halves of
    data/{category}/{subject_slug}/ have to match for two sources to
    aggregate into one page (see CrawlSource.subject_slug), so defaulting
    the form to the slug quietly sent a hand-approved candidate to a
    different page than the same source's auto-approved ones.

    Falls back to the slug for candidates staged before `category` was
    carried on them - that IS the old default."""
    return candidate.get("category") or candidate["subject_slug"]


def _page_title_for(candidate: dict) -> str:
    """The title page.yaml gets when approving this candidate creates it.
    Prefers the suggested subject_name a crawl/adapter run stamped on the
    candidate (see staging.build_candidate) over the raw slug - approving
    through the review UI used to pass subject_slug as the page title, so a
    crawl source's page was headed "eclipse-gsfc-nasa-gov" while the SAME
    source's auto-waved-through candidates got the cleaned-up
    "Sonnenfinsternis" via crawl_runner. page.yaml is written once and never
    rewritten, so whichever path approved first pinned the title for good.

    Falls back to the slug for candidates staged before subject_name
    existed."""
    return candidate.get("subject_name") or candidate["subject_slug"]


def _approve_one(source_id: str, candidate_id: str, category: str, license: str) -> Optional[str]:
    """Approves one candidate, or returns why it couldn't be. Shared by the
    single-candidate route (which turns the message into a 4xx page) and
    /review/bulk-edit (which collects the messages and reports them as a
    per-row failure list) - so a bulk run applies exactly the same
    validation, quelle and review-state bookkeeping as approving each row by
    hand, rather than a second, looser copy of it."""
    if not _is_known_source_id(source_id):
        return "unknown source"
    run_ts = _latest_run_ts(source_id)
    candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return "not found - may already have been reviewed"
    if license not in LICENSE_VALUES:
        return f"invalid license: {license}"

    category_path = "/".join(_slugify_category_path(category))
    validation_error = _validate_category_segments(category_path.split("/") if category_path else [])
    if validation_error:
        return validation_error

    quelle = _quelle_for_candidate(source_id, candidate, license)
    try:
        approval.write_event(category_path, candidate["subject_slug"], _page_title_for(candidate), candidate["event"], quelle)
    except approval.ApprovalError as e:
        return f"validation failed, nothing written: {e}"
    _write_category_meta_if_new(category)

    # Normally no review-state write at all: the window is now in data.yaml,
    # which IS the record of what is approved. The exception is an approval
    # filed somewhere OTHER than the page this source writes to - the source's
    # own page then doesn't contain it, so every later run would re-offer it
    # and the operator would have to re-override the category forever. The
    # negative set means "don't queue this again", which is exactly true here.
    if category_path != _target_category_for(candidate):
        st = review_state.load(source_id)
        review_state.reject(st, candidate["subject_slug"], candidate["event"])
        review_state.save(source_id, st)
    return None


def _reject_one(source_id: str, candidate_id: str) -> Optional[str]:
    """Rejects one candidate, or returns why it couldn't be - the reject-side
    twin of _approve_one, shared by the single-candidate route and the bulk
    one for the same reason."""
    if not _is_known_source_id(source_id):
        return "unknown source"
    run_ts = _latest_run_ts(source_id)
    candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return "not found - may already have been reviewed"

    st = review_state.load(source_id)
    review_state.reject(st, candidate["subject_slug"], candidate["event"])
    review_state.save(source_id, st)
    return None


@app.post("/review/{source_id}/{candidate_id}/approve")
async def approve_candidate(
    source_id: str,
    candidate_id: str,
    category: str = Form(...),
    license: str = Form(...),
):
    error = _approve_one(source_id, candidate_id, category, license)
    if error == "unknown source":
        return HTMLResponse("Not found", status_code=404)
    if error and error.startswith("not found"):
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    if error:
        return HTMLResponse(error, status_code=400)
    return _redirect_to_next_review(source_id, candidate_id)


@app.post("/review/bulk-edit")
async def bulk_approve_candidates(
    request: Request,
    selected: List[str] = Form(default=[]),
    # Not required: a rejection writes no data.yaml, so it has no Quelle to
    # stamp a license on. The approve branch below still demands a real one.
    license: str = Form(""),
    action: str = Form("approve"),
    return_to: str = Form(""),
):
    """Approves or rejects every checked row of /review's queue in one POST -
    `action` carries the value of whichever submit button was clicked. Each
    `selected` value is "<source_id>/<candidate_id>", and each row is
    approved under its own subject_slug as category - the same default the
    single-candidate form prefills, so bulk and one-by-one put a given
    candidate in the same place. Rows that fail are reported by id rather
    than aborting the batch: a run of 200+ rows where row 3 fails validation
    should still land the other 199, and an all-or-nothing rollback would
    need transactional writes across many data.yaml files that
    approval.write_event does not have.

    Note the queue is re-read per row (via _approve_one -> _load_candidate),
    so this stays correct if an earlier row's write changes what a later one
    resolves to."""
    if action not in ("approve", "reject"):
        return HTMLResponse(f"Invalid action: {action}", status_code=400)
    # A reject writes no data.yaml, so the license select is irrelevant to it.
    if action == "approve" and license not in LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    editted, failures = 0, []
    for value in selected:
        source_id, _, candidate_id = value.rpartition("/")
        if not source_id or not candidate_id:
            failures.append(f"{value}: malformed selection")
            continue
        if action == "reject":
            error = _reject_one(source_id, candidate_id)
        else:
            candidate = _load_candidate(source_id, _latest_run_ts(source_id), candidate_id) if _is_known_source_id(source_id) else None
            # Category default matches _candidate_review.html's prefilled field.
            category = _target_category_for(candidate) if candidate else ""
            error = _approve_one(source_id, candidate_id, category, license)
        if error:
            failures.append(f"{value}: {error}")
        else:
            editted += 1

    # return_to="document" comes from the in-document review page, whose
    # point is staying in one place - it re-renders with the decided dates
    # gone. Not a URL: the destination is rebuilt from the first selection,
    # so nothing user-supplied reaches the redirect.
    if return_to == "document" and selected:
        source_id, _, candidate_id = selected[0].rpartition("/")
        run_ts = _latest_run_ts(source_id) if _is_known_source_id(source_id) else None
        candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
        if candidate:
            return RedirectResponse(f"/review/{source_id}/document/{candidate['document']}", status_code=302)

    # Renders the queue directly instead of redirecting to it, so the
    # per-row reasons survive - a redirect could only carry the counts, and
    # "12 approved, 3 failed" without the three reasons is exactly the kind
    # of silent partial success this route has to avoid. Re-POSTing on a
    # refresh is harmless: those rows are no longer pending, so every one
    # comes back "may already have been reviewed" and nothing is written twice.
    return templates.TemplateResponse(request, "review.html", {
        "active_nav": "review",
        "state": state.to_dict(),
        "queue": _review_queue(),
        "license_options": LICENSE_OPTIONS,
        "bulk_action": "approved" if action == "approve" else "rejected",
        "bulk_done": editted,
        "bulk_failures": failures,
    })


@app.post("/review/{source_id}/{candidate_id}/modify")
async def modify_candidate(
    source_id: str,
    candidate_id: str,
    category: str = Form(...),
    license: str = Form(...),
    type: str = Form(...),
    name: str = Form(""),
    year: str = Form(""),
    from_: str = Form(..., alias="from"),
    to: str = Form(...),
    precision: str = Form("exact"),
):
    if not _is_known_source_id(source_id):
        return HTMLResponse("Not found", status_code=404)
    run_ts = _latest_run_ts(source_id)
    candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    if license not in LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    category_path = "/".join(_slugify_category_path(category))
    validation_error = _validate_category_segments(category_path.split("/") if category_path else [])
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)

    corrected_event = {
        **candidate["event"],
        "type": type,
        "name": name or None,
        "year": int(year) if year.strip() else None,
        "from": from_,
        "to": to,
        "precision": precision,
    }
    corrected_event = {k: v for k, v in corrected_event.items() if v is not None}

    quelle = _quelle_for_candidate(source_id, candidate, license)
    try:
        approval.write_event(category_path, candidate["subject_slug"], _page_title_for(candidate), corrected_event, quelle)
    except approval.ApprovalError as e:
        return HTMLResponse(f"Validation failed, nothing written:\n{e}", status_code=400)
    _write_category_meta_if_new(category)

    # The correction is already in data.yaml, so it needs no second record.
    # The ORIGINAL identity does: the source keeps re-extracting it, and
    # without retiring it the same wrong window would re-queue every run.
    st = review_state.load(source_id)
    review_state.reject(st, candidate["subject_slug"], candidate["event"])
    review_state.save(source_id, st)
    return _redirect_to_next_review(source_id, candidate_id)


@app.post("/review/{source_id}/{candidate_id}/reject")
async def reject_candidate(source_id: str, candidate_id: str, return_to: str = Form("")):
    """return_to="document" comes from the in-document Reject buttons and
    sends you back to the document you were reading instead of jumping to
    the next queue item - the whole point of that view is staying in one
    place. Not a URL, just a flag: the destination is rebuilt from the
    candidate's own document, so nothing user-supplied reaches the redirect."""
    candidate = None
    if return_to == "document":
        run_ts = _latest_run_ts(source_id)
        candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None

    error = _reject_one(source_id, candidate_id)
    if error:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    if candidate:
        return RedirectResponse(f"/review/{source_id}/document/{candidate['document']}", status_code=302)
    return _redirect_to_next_review(source_id, candidate_id)


@app.get("/status")
async def get_status():
    """JSON endpoint for external polling/tooling."""
    return JSONResponse(state.to_dict())


@app.get("/status-fragment", response_class=HTMLResponse)
async def get_status_fragment(request: Request):
    """Polled by the shared header (every 3s, see _base.html's
    #status-indicator) - just the global running/idle badge for in-flight
    crawl_sources runs (see PipelineState)."""
    return templates.TemplateResponse(request, "_status_fragment.html", {"state": state.to_dict()})


class HarvestRegistryState:
    """Tracks in-flight harvest registry fetches per entity_class - a
    registry fetch is one blocking network call (Wikidata SPARQL), too slow
    to run inline in an async route."""
    def __init__(self):
        self.running: Set[str] = set()
        self.errors: Dict[str, str] = {}


harvest_registry_state = HarvestRegistryState()


def _fetch_harvest_registry_and_record(entity_class: str) -> None:
    try:
        entities = harvest_registry.fetch_registry(entity_class)
        harvest_registry.write_registry(entity_class, entities)
        harvest_registry_state.errors.pop(entity_class, None)
    except Exception as e:
        harvest_registry_state.errors[entity_class] = str(e)[:300]
    finally:
        harvest_registry_state.running.discard(entity_class)


@app.get("/harvest/wikidata-search")
async def harvest_wikidata_search(q: str):
    """Backs the Add Registry form's class search box - proxied through the
    backend (rather than called from the browser directly) so it goes
    through the same identifying User-Agent as every other Wikidata call
    (see sources/registry.py's USER_AGENT)."""
    term = q.strip()
    if not term:
        return JSONResponse([])
    try:
        results = await asyncio.to_thread(harvest_registry.search_wikidata_classes, term)
    except Exception as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=502)
    return JSONResponse(results)


@app.post("/harvest/registries/config")
async def add_harvest_registry(
    entity_class: str = Form(...),
    sparql: str = Form(...),
    target_kinds: str = Form(...),
):
    """Adds a new entity_class to config/registries.yaml from the dashboard's
    Add Registry form - always method: wikidata_sparql, the only method
    fetch_registry() implements so far (see sources/registry.py)."""
    entity_class = entity_class.strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", entity_class):
        return HTMLResponse(
            "entity_class must start with a lowercase letter and contain only lowercase letters, digits, and underscores.",
            status_code=400,
        )
    kinds = [k.strip() for k in target_kinds.split(",") if k.strip()]
    if not kinds:
        return HTMLResponse("At least one target_kind is required.", status_code=400)
    if not sparql.strip():
        return HTMLResponse("SPARQL query must not be empty.", status_code=400)

    try:
        harvest_registry.add_registry_config(entity_class, sparql.strip(), kinds)
    except ValueError as e:
        return HTMLResponse(str(e), status_code=400)

    return RedirectResponse("/", status_code=302)


@app.post("/harvest/registry")
async def start_harvest_registry(entity_class: str = Form(...)):
    if entity_class not in harvest_registry.load_registries_config():
        return JSONResponse({"error": f"Unknown entity_class '{entity_class}'"}, status_code=400)
    if entity_class in harvest_registry_state.running:
        return JSONResponse({"error": "A fetch for this entity_class is already running."}, status_code=409)

    harvest_registry_state.running.add(entity_class)
    threading.Thread(target=_fetch_harvest_registry_and_record, args=(entity_class,), daemon=True).start()
    return JSONResponse({"status": "started", "entity_class": entity_class})


@app.get("/harvest/registry-status")
async def harvest_registry_status_route(entity_class: str):
    """Polled by the dashboard's Fetch Registry button - same reasoning as
    /scrape-status: the POST above returns almost instantly, the real fetch
    happens in the background thread."""
    return JSONResponse({
        "running": entity_class in harvest_registry_state.running,
        "error": harvest_registry_state.errors.get(entity_class),
    })


@app.get("/harvest/registry-table", response_class=HTMLResponse)
async def harvest_registry_table(request: Request):
    return templates.TemplateResponse(request, "_harvest_registry_table.html", {
        "harvest_registries": _harvest_registry_status(),
    })


@app.post("/harvest/registries/{entity_class}/delete", response_class=HTMLResponse)
async def delete_harvest_registry(request: Request, entity_class: str):
    """Removes entity_class from config/registries.yaml and deletes its
    fetched data/registries/<entity_class>.json, if any - the Admin UI's
    Delete Registry button. Refuses while a fetch is in-flight for it."""
    if entity_class in harvest_registry_state.running:
        return HTMLResponse("A fetch for this entity_class is running - wait for it to finish.", status_code=409)
    try:
        harvest_registry.delete_registry_config(entity_class)
    except ValueError as e:
        return HTMLResponse(str(e), status_code=400)
    harvest_registry_state.errors.pop(entity_class, None)
    return templates.TemplateResponse(request, "_harvest_registry_table.html", {
        "harvest_registries": _harvest_registry_status(),
    })


@app.get("/harvest/registries/{entity_class}", response_class=HTMLResponse)
async def get_harvest_registry_json(entity_class: str):
    """Raw registry JSON for one entity_class, same guard pattern as
    /scraped/{filename}."""
    path = (harvest_registry.OUTPUT_DIR / f"{entity_class}.json").resolve()
    if path.parent != harvest_registry.OUTPUT_DIR.resolve() or not path.exists():
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")


def _resolve_page_folder(full_path: str) -> Optional[Path]:
    """Shared guard for every /pages/{full_path}/... and /page-data|/page-meta
    route below. full_path is "{category-path}/{slug}", where category-path
    may itself be several "/"-joined segments now that categories can nest -
    so a naive `path.parent.parent.parent != DATA_ROOT` check (hardcoded to
    exactly one category segment before the slug) wouldn't fit. The actual
    invariant that matters is unchanged though: the resolved path must still
    be inside DATA_ROOT, AND it must be a real page folder (both page.yaml
    and data.yaml present) - checking that directly, at whatever depth,
    generalizes the guard without loosening it. Returns None if either check
    fails, so callers 404 rather than operate on an unresolved/invalid path."""
    folder = (DATA_ROOT / full_path).resolve()
    data_root = DATA_ROOT.resolve()
    if data_root != folder and data_root not in folder.parents:
        return None
    if not (folder / "page.yaml").exists() or not (folder / "data.yaml").exists():
        return None
    return folder


def _serve_page_file(full_path: str, filename: str) -> HTMLResponse:
    folder = _resolve_page_folder(full_path)
    if folder is None:
        return HTMLResponse("Not found", status_code=404)
    target = folder / filename
    if not target.exists():
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(target.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")


@app.get("/page-data/{full_path:path}", response_class=HTMLResponse)
async def get_page_data_yaml(full_path: str):
    """Raw data.yaml for a created page, same guard pattern as /scraped/{filename}."""
    return _serve_page_file(full_path, "data.yaml")


@app.get("/page-meta/{full_path:path}", response_class=HTMLResponse)
async def get_page_meta_yaml(full_path: str):
    """Raw page.yaml for a created page, same guard pattern as /scraped/{filename}."""
    return _serve_page_file(full_path, "page.yaml")


@app.post("/pages/{full_path:path}/delete")
async def delete_page(full_path: str, return_to: str = Form("/crawl-sources")):
    """Deletes a created page's whole folder (data.yaml + page.yaml) from
    data/ - the Admin UI's Delete button (and bulk "Delete Selected") on the
    created-pages table. return_to is allowlisted (not just blocklisted)
    against the only two pages that render this button - a blocklist like
    "must start with '/' and not '//'" still lets through backslash tricks
    browsers treat as protocol-relative ("/\\evil.com")."""
    folder = _resolve_page_folder(full_path)
    if folder is None:
        return HTMLResponse("Not found", status_code=404)
    shutil.rmtree(folder)
    if not _SAFE_RETURN_TO.match(return_to):
        return_to = "/crawl-sources"
    return RedirectResponse(return_to, status_code=302)


@app.post("/pages/{full_path:path}/edit")
async def edit_page(
    full_path: str,
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    category: str = Form(...),
    license: str = Form(...),
    return_to: str = Form("/crawl-sources"),
):
    """Edits an already-created page's title/description/tags/license in
    place, and MOVES its folder if the category changed - the Admin UI's
    inline Edit form on the created-pages table, for fixing a typo or
    reclassifying a page without hand-editing YAML. A category change is a
    real folder move (this page's URL changes too), refused if something
    already exists at the target path rather than silently overwriting it."""
    folder = _resolve_page_folder(full_path)
    if folder is None:
        return HTMLResponse("Not found", status_code=404)
    if license not in LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    new_segments = _slugify_category_path(category)
    validation_error = _validate_category_segments(new_segments)
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)
    new_category_path = "/".join(new_segments)

    parts = full_path.strip("/").split("/")
    slug = parts[-1]
    current_category_path = "/".join(parts[:-1])

    if new_category_path != current_category_path:
        target = DATA_ROOT / new_category_path / slug
        if target.exists():
            return HTMLResponse(f"A page already exists at /{new_category_path}/{slug}/.", status_code=409)
        target.parent.mkdir(parents=True, exist_ok=True)
        folder = folder.rename(target)
        _write_category_meta_if_new(category)

    data = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
    # The license applies to EVERY citation, and the list is kept. Collapsing
    # it to source[0] destroyed the others - and an aggregated page is the
    # normal case (several sources, one page, see CrawlSource.subject_slug),
    # so changing the license on data/astronomie/sonnenfinsternis/ dropped a
    # citation that its own windows still referenced, which pageDataSchema's
    # superRefine then failed the whole site build on.
    data["source"] = [{**q, "license": license} for q in _as_quelle_list(data)]
    subject = data.get("subject") or {}
    subject["category"] = new_category_path
    subject["slug"] = slug
    data["subject"] = subject
    with (folder / "data.yaml").open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    page = {"title": title, "description": description, "tags": tag_list}
    with (folder / "page.yaml").open("w", encoding="utf-8") as f:
        yaml.dump(page, f, allow_unicode=True, sort_keys=False)

    if not _SAFE_RETURN_TO.match(return_to):
        return_to = "/crawl-sources"
    return RedirectResponse(return_to, status_code=302)


@app.get("/pages/{full_path:path}/suggest-tags")
async def suggest_page_tags(full_path: str):
    """Tags for an existing page, preferring the vocabulary already in use.

    Operator-triggered rather than stamped at approval time: page.yaml is
    written once (store.schreibe_page_yaml_falls_neu), so an automatic call
    would only ever matter for the first candidate of a page while costing
    an LLM round trip on every other one. suggest_tags has existed since the
    beginning with no caller at all - _all_tags()'s own docstring already
    claimed to feed it.

    Returns JSON rather than re-rendering: the pages table fills the tags
    field in place, so a suggestion can be edited before it is saved. Nothing
    here writes."""
    folder = _resolve_page_folder(full_path)
    if folder is None:
        return JSONResponse({"error": "Not found"}, status_code=404)

    page = yaml.safe_load((folder / "page.yaml").read_text(encoding="utf-8")) or {}
    datei = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8")) or {}
    # The windows ARE the page's text - there is no prose to summarise, so
    # the tag prompt gets what the page actually says.
    text = "\n".join(str(w.get("name") or "") for w in (datei.get("windows") or [])[:50])
    try:
        tags = suggest_tags(text or page.get("title", ""), page.get("title", ""), _all_tags())
    except ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return JSONResponse({"tags": tags})


@app.post("/pages/{full_path:path}/add-tag")
async def add_tag_to_page(full_path: str, tag: str = Form(...)):
    """Adds one tag to an already-created page's page.yaml, deduped - backs
    the created-pages table's bulk "Add Tag" action (JSON, not a redirect,
    since the bulk action fires one fetch() per selected page and reloads
    once every request settles)."""
    folder = _resolve_page_folder(full_path)
    if folder is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    tag = tag.strip()
    if not tag:
        return JSONResponse({"error": "Empty tag."}, status_code=400)

    page_path = folder / "page.yaml"
    page = yaml.safe_load(page_path.read_text(encoding="utf-8")) or {}
    existing_tags = page.get("tags") or []
    if tag not in existing_tags:
        existing_tags.append(tag)
    page["tags"] = existing_tags
    with page_path.open("w", encoding="utf-8") as f:
        yaml.dump(page, f, allow_unicode=True, sort_keys=False)
    return JSONResponse({"status": "ok", "tags": existing_tags})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
