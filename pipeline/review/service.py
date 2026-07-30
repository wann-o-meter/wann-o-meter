"""Everything the review app does that is not HTTP.

Split out of the old 82 KB main.py so the logic is reachable without a
TestClient: routes/ is glue that parses a request, calls in here, and picks a
template. The module-level DATA_ROOT lives here too, which is what lets a test
repoint the whole app at a tmp_path by patching one attribute.
"""

import html
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core import approval, crawl_config, crawl_runner, review_state, staging, store, validate

# Re-exported, not used here: routes reach these as service.suggest_tags /
# service.ExtractionError so there is ONE place to monkeypatch the model call
# (see tests/test_review_routes.py's TestSuggestTags). Importing them directly
# in routes/pages.py would bind the real function at import time and make the
# stub unreachable. F401 cannot see a use that only happens via getattr.
from core.extraction import ExtractionError, suggest_tags  # noqa: F401
from sources import registry as harvest_registry

_EXTRACTION_MODE_HINTS = {
    "auto": "date tables read directly, everything else via the model",
    "llm": "always the model - best labels, one call per 20k chars",
    # The regex reads ISO and the "2001 Jun 21" catalog form only, so a German
    # page ("19. September bis 4. Oktober 2026") yields NOTHING under static -
    # reported as "static: 0 date(s)", which looks the same as a page with no
    # dates at all. Say so here rather than let it be discovered by a run.
    "static": "regex only, never the model - ISO dates (2026-09-19) only, NOT '19. September'",
}
EXTRACTION_MODE_OPTIONS = [(mode, _EXTRACTION_MODE_HINTS.get(mode, "")) for mode in crawl_config.EXTRACTION_MODES]

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
        self.running_sources: set[str] = set()
        self.errors: dict[str, str] = {}
        self.last_result: dict[str, dict] = {}
        # {source_id: {"phase": ..., "detail": ...}} - crawl_runner.run passes
        # the phase separately so the dashboard can show "Crawling: ..." as a
        # glanceable label (_crawl_sources_table.html reads p.phase/p.detail).
        self.progress: dict[str, dict[str, str]] = {}
        # {source_id: {url: status}} for the most recent run of each source,
        # in insertion order (crawl order). Deliberately NOT cleared when a
        # run finishes - it's the per-page record the crawl-sources table
        # shows afterwards, and it's the only place the URLs that got
        # dropped (robots, fetch error, wrong format) exist at all; staging/
        # only ever holds the survivors. Lost on restart, which is fine: it
        # falls back to the staged documents then (see _source_pages).
        self.pages: dict[str, dict[str, str]] = {}

    def to_dict(self) -> dict:
        return {
            "is_running": bool(self.running_sources),
            "running_sources": sorted(self.running_sources),
        }


state = PipelineState()

templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

# Exposed as globals rather than passed per route, so _base.html can render
# every <datalist> once and EVERY form gets them - the three copies these
# replace lived in three templates, which is why the crawl-source edit row
# had category suggestions but the page-title and page-slug fields beside it
# silently had none. Read straight from disk on each render, same philosophy
# as _list_created_pages(); this is a local admin tool, not a hot path.
# jinja2 leaves env.globals' value type to be inferred from the builtins it
# ships with (range, cycler, lipsum...), so every application-supplied global
# reads as a type error. Passing a dict keeps the suppression to this one call
# instead of one per entry.
templates.env.globals.update(  # ty: ignore[no-matching-overload]
    {
        "all_categories": lambda: _category_suggestions(),
        "all_tags": lambda: _all_tags(),
        "all_page_titles": lambda: sorted({p["title"] for p in _list_created_pages()}),
        "all_page_slugs": lambda: sorted({p["slug"] for p in _list_created_pages()}),
        "extraction_mode_options": EXTRACTION_MODE_OPTIONS,
    }
)

# Backs the site's dynamic /{category-path}/{slug}/ routes (lib/pages.ts
# reads the same tree via `join(process.cwd(), "data")` from the repo root,
# src/pages/[...path].astro renders it). A category can nest up to
# MAX_CATEGORY_DEPTH "/"-joined segments deep (data/sport/fussball/
# bundesliga/{slug}/ -> /sport/fussball/bundesliga/{slug}/) - each non-
# reserved top-level folder under data/ is the root of one category tree.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"

# Must stay in sync with lib/pages.ts's RESERVED_CATEGORIES - these top-level
# data/ folder names are already owned by the site's hardcoded categories, so
# a page can't be created under them (would collide with an existing route).
# Checked against segment 1 only.
RESERVED_CATEGORIES = {
    "kalender",
    "urlaubsfenster",
    "feiertage",
    "presets",
    "seiten",
    "themen",
    "api",
    "feeds",
    "impressum",
    "datenschutz",
    "schema",
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


def _slugify_category_path(category: str) -> list[str]:
    """Splits an operator-typed category path ("Sport/Fußball/Bundesliga")
    on "/" and slugifies each segment independently - never slugify before
    splitting, that would turn "/" into "-" and collapse the hierarchy.
    Matches lib/pages-schema.ts's per-segment validation."""
    return [_slugify(seg) for seg in category.split("/") if seg.strip()]


def _validate_category_segments(segments: list[str]) -> str | None:
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


def _walk_pages(segments: list[str], directory: Path, out: list[tuple[str, Path]]) -> None:
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
        _walk_pages([*segments, entry.name], entry, out)


def _iter_pages() -> list[tuple[str, Path]]:
    """Recursively walks data/, skipping reserved top-level segments and any
    "tag"-named segment at any depth, yielding (category_path, page_folder)
    for every folder that's a page leaf (page.yaml + data.yaml present).
    category_path is the "/"-joined slug path matching lib/pages.ts's
    Page.category field (e.g. "sport/fussball/bundesliga"). Cheap enough for
    the handful of pages this admin tool deals with - no index file to keep
    in sync."""
    if not DATA_ROOT.exists():
        return []
    out: list[tuple[str, Path]] = []
    for entry in sorted(DATA_ROOT.iterdir()):
        if entry.is_dir() and entry.name not in RESERVED_CATEGORIES and entry.name not in RESERVED_AT_ANY_DEPTH:
            _walk_pages([entry.name], entry, out)
    return out


def _category_paths() -> list[str]:
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


def _all_tags() -> list[str]:
    """Every tag already used across all page.yaml files - shown as a
    datalist (like _category_suggestions()) so an operator can reuse one
    instead of typing a near-duplicate, and fed to the LLM tag-suggestion
    prompt so it prefers reusing these over inventing new ones."""
    tags: set[str] = set()
    for _category_path, folder in _iter_pages():
        page_path = folder / "page.yaml"
        try:
            page = yaml.safe_load(page_path.read_text(encoding="utf-8"))
            tags.update(page.get("tags", []) if isinstance(page, dict) else [])
        except Exception:
            continue
    return sorted(tags)


def _category_suggestions() -> list[str]:
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


def _list_created_pages() -> list[dict]:
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
        pages.append(
            {
                "category": category_path,
                "category_display": _category_name_for(category_path),
                "slug": folder.name,
                "title": page_meta.get("title", folder.name),
                "description": page_meta.get("description", ""),
                "tags": page_meta.get("tags", []),
                "url": source.get("url", ""),
                "license": source.get("license", ""),
            }
        )
    return pages


def _harvest_registry_status() -> list[dict]:
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
        rows.append(
            {
                "entity_class": entity_class,
                "target_kinds": cfg.get("target_kinds", []),
                "count": count,
                "fetched_at": fetched_at,
                "running": entity_class in harvest_registry_state.running,
                "error": harvest_registry_state.errors.get(entity_class),
            }
        )
    return rows


def _latest_run_ts(source_id: str) -> str | None:
    source_dir = staging.STAGING_ROOT / source_id
    if not source_dir.exists():
        return None
    run_dirs = sorted((p.name for p in source_dir.iterdir() if p.is_dir()), reverse=True)
    return run_dirs[0] if run_dirs else None


def _source_pages(source_id: str) -> list[dict[str, str]]:
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


def _known_source_ids() -> list[str]:
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


def _pending_candidates_for(source_id: str) -> list[dict]:
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


def _review_queue() -> list[dict]:
    return [c for source_id in _known_source_ids() for c in _pending_candidates_for(source_id)]


def _next_review_candidate(exclude: tuple | None = None) -> dict | None:
    """First pending candidate in the queue, other than `exclude` - lets a
    reviewer chain straight from one decision (or an explicit Skip) to the
    next one instead of bouncing back through /review's list every time."""
    for candidate in _review_queue():
        if exclude and (candidate["source_id"], candidate["candidate_id"]) == exclude:
            continue
        return candidate
    return None


_MONTH_ABBR = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}
_ISO_DATE_RE = re.compile(r"^(-?\d{1,4})-(\d{2})-(\d{2})$")


def _human_date_variant(iso_date: str) -> str | None:
    """ "1901-01-07" -> "1901 Jan 07" - the format eclipse.gsfc.nasa.gov's
    catalog pages actually write dates in (verified against a real staged
    snapshot) - a source's own date formatting varies, so this is one
    extra guess alongside the plain ISO string, not a general parser."""
    m = _ISO_DATE_RE.match(iso_date)
    if not m:
        return None
    year, month, day = m.groups()
    abbr = _MONTH_ABBR.get(int(month))
    return f"{year} {abbr} {day}" if abbr else None


# Keyed by format so a range can be assembled from two dates written the same
# way - no page mixes "2026-10-26" with "30.10.".
def _date_renderings(iso_date: str) -> dict[str, str]:
    m = _ISO_DATE_RE.match(iso_date)
    renderings = {"iso": iso_date}
    if not m:
        return renderings
    year, month, day = m.groups()
    abbr = _MONTH_ABBR.get(int(month))
    if abbr:
        renderings["catalog"] = f"{year} {abbr} {day}"
    # kmk.org writes "26.10. - 30.10.": day.month, trailing dot, no year.
    renderings["de_full"] = f"{day}.{month}.{year}"
    renderings["de"] = f"{day}.{month}."
    return renderings


# EN DASH is deliberate: German date ranges are written with it as often
# as with a hyphen.
_RANGE_SEPARATORS = (" - ", " – ", " bis ", "-", "–")  # noqa: RUF001


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


def _highlight_dates(text: str, dates: list[str | None]) -> str:
    """Escapes `text` for safe HTML embedding, then wraps any occurrence of
    one of the candidate's own from/to dates - in ISO form or the
    human-readable variant above - in <mark>. Best-effort: a miss just
    means no highlight, the escaped text still renders either way, since
    input is always fully escaped first regardless of whether anything
    matched."""
    escaped = html.escape(text)
    spellings: list[str] = []
    if len(dates) == 2:
        spellings.extend(_date_range_variants(dates[0], dates[1]))
    for date in dates:
        spellings.extend(_date_variants(date))
    if not spellings:
        return escaped
    # Longest first, so a range wins over each of its own ends.
    alternation = "|".join(re.escape(html.escape(s)) for s in sorted(set(spellings), key=len, reverse=True))
    return re.sub("(" + alternation + ")", r"<mark>\1</mark>", escaped)


def _date_variants(date: str | None) -> list[str]:
    """Every spelling of one date the review UI knows how to look for. Shared
    so the single-candidate highlight and the whole-document one can never
    drift into finding different things on the same page."""
    if not date:
        return []
    return list(_date_renderings(date).values())


def _date_range_variants(start: str | None, end: str | None) -> list[str]:
    """Spellings of a whole range. A source that writes "26.10. - 30.10."
    must highlight as ONE hit: matching the two ends separately would put two
    checkboxes on a single window, which reads as two things to decide."""
    if not start or not end or start == end:
        return []
    starts, ends = _date_renderings(start), _date_renderings(end)
    return [
        f"{starts[fmt]}{separator}{ends[fmt]}" for fmt in starts.keys() & ends.keys() for separator in _RANGE_SEPARATORS
    ]


def _highlight_candidates(text: str, candidates: list[dict], source_id: str) -> str:
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
    by_pattern: dict[str, dict] = {}
    for candidate in candidates:
        event = candidate.get("event") or {}
        variants = _date_range_variants(event.get("from"), event.get("to"))
        for date in (event.get("from"), event.get("to")):
            variants.extend(_date_variants(date))
        for variant in variants:
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
            f"<span>{match.group(0)}</span>"
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


def _load_candidate(source_id: str, run_ts: str, candidate_id: str) -> dict | None:
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
    def report(update: dict[str, str]) -> None:
        state.progress[source_id] = update

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


def _as_source_list(file: dict[str, Any]) -> list[dict[str, Any]]:
    """lib/pages-schema.ts accepts `source` as either a bare object or a
    list; store.append_source only handles the list. Every page written
    before that list form existed still has the object on disk, so
    normalizing here is what makes merging a real page work rather than
    raising AttributeError halfway through."""
    sources = file.get("source") or []
    return [sources] if isinstance(sources, dict) else list(sources)


def _migrate_page_folder(old_folder: Path, new_folder: Path, slug: str, category: str) -> str | None:
    """Folds data/{old_category}/{old_slug}/ into data/{category}/{slug}/,
    returning why it couldn't be (nothing written) or None on success.

    One code path, no move-vs-merge branch: store.load_or_create yields
    an empty skeleton when the target doesn't exist yet, so a plain move is
    just a merge into an empty file. merge_windows then does the real
    work - the same window from both sources keeps one entry and unions its
    citations, a different date range replaces - which is precisely the
    aggregation CrawlSource.subject_slug exists to enable.

    A missing old folder is success, not an error: a source's configured
    target can name a page it never actually wrote (nothing approved yet, or
    a config that drifted away from where its approvals really landed)."""
    old_data = old_folder / "data.yaml"
    if not old_data.exists():
        return None

    old_file = yaml.safe_load(old_data.read_text(encoding="utf-8")) or {}
    file = store.load_or_create(new_folder / "data.yaml", slug, category)
    file["source"] = _as_source_list(file)

    store.merge_windows(file, old_file.get("windows") or [])
    for source in _as_source_list(old_file):
        store.append_source(file, source)
    # The moved windows keep their source_urls, and pageDataSchema's
    # superRefine fails the site build if one of those isn't in source[] -
    # so carrying the citations over is required, not politeness. Rewriting
    # subject also repairs a file whose slug no longer matches its folder.
    file["subject"] = {"slug": slug, "category": category}

    try:
        validate.pruefe_subject_file(file)
    except validate.ValidationError as e:
        return f"The merged page would be invalid, nothing written:\n{e}"

    store.speichere(new_folder / "data.yaml", file)
    # Copied rather than store.schreibe_page_yaml_falls_neu'd: that would
    # write a bare title and drop the description/tags a human set here. An
    # existing target page.yaml wins - it's the one already on the site.
    if not (new_folder / "page.yaml").exists() and (old_folder / "page.yaml").exists():
        shutil.copy(old_folder / "page.yaml", new_folder / "page.yaml")
    shutil.rmtree(old_folder)
    return None


_STAGING_DOCUMENT_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".ics": "text/calendar",
    ".md": "text/markdown; charset=utf-8",
}


_DOC_HASH_RE = re.compile(r"^[0-9a-f]+$")


def _redirect_to_next_review(source_id: str, candidate_id: str) -> RedirectResponse:
    """Chains straight from an approve/modify/reject decision to whatever's
    next in the queue (see _next_review_candidate) instead of bouncing
    through /review's list every time - falls back to the list once the
    queue is empty."""
    next_candidate = _next_review_candidate(exclude=(source_id, candidate_id))
    if next_candidate:
        return RedirectResponse(
            f"/review/{next_candidate['source_id']}/{next_candidate['candidate_id']}", status_code=302
        )
    return RedirectResponse("/review", status_code=302)


def _source_for_candidate(source_id: str, candidate: dict, license: str) -> dict:
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


def _approve_one(source_id: str, candidate_id: str, category: str, license: str) -> str | None:
    """Approves one candidate, or returns why it couldn't be. Shared by the
    single-candidate route (which turns the message into a 4xx page) and
    /review/bulk-edit (which collects the messages and reports them as a
    per-row failure list) - so a bulk run applies exactly the same
    validation, source and review-state bookkeeping as approving each row by
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

    source = _source_for_candidate(source_id, candidate, license)
    try:
        approval.write_event(
            category_path, candidate["subject_slug"], _page_title_for(candidate), candidate["event"], source
        )
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


def _reject_one(source_id: str, candidate_id: str) -> str | None:
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


class HarvestRegistryState:
    """Tracks in-flight harvest registry fetches per entity_class - a
    registry fetch is one blocking network call (Wikidata SPARQL), too slow
    to run inline in an async route."""

    def __init__(self):
        self.running: set[str] = set()
        self.errors: dict[str, str] = {}


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


def _resolve_page_folder(full_path: str) -> Path | None:
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
