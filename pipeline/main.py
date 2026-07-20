#!/usr/bin/env python3
"""
Wann-Plattform Admin Dashboard
FastAPI + Jinja2 (SSR) + HTMX

Features:
- Start focused crawler from seed domains
- See discovered pages in real time
- Manually Accept / Reject pages
- Accepted pages go to scraper queue
- Avoids big generic sites (Wikipedia, Google, Facebook, etc.)
"""

import asyncio
import hashlib
import json
import re
import shutil
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import trafilatura
import uvicorn
import yaml
from bs4 import BeautifulSoup
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv

from harvest import registry as harvest_registry

# Must stay in sync with lib/schema.ts's lizenzSchema (the "value" fields
# only - "label" is admin-UI-only help text, not part of the data model). The
# license is deliberately never guessed automatically: PLAN.md section 6
# requires an explicit decision per new source. Operators aren't expected to
# know copyright law, so each label states the concrete situation to match
# rather than an abstract legal term - order follows PLAN.md's decision tree,
# most-common civic-data case first.
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

# Seeds the category datalist so an operator without a house style guide has
# something to reuse instead of inventing a near-duplicate name (see
# RESERVED_CATEGORIES below for why fragmentation matters) - kept deliberately
# short; real usage (via _category_paths()) is the actual source of truth
# going forward, this just gives the very first pages somewhere to start.
SUGGESTED_CATEGORIES = ["politik"]

BLACKLISTED_DOMAINS = {
    "wikipedia.org", "wikimedia.org",
    "google.com", "google.de", "google.at", "google.ch",
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com",
    "amazon.de", "ebay.de",
    "reddit.com", "pinterest.com",
    "tripadvisor.com", "booking.com",
}

load_dotenv()


class SeedRun:
    """One crawl "task": the seeds it was started with, plus everything it
    found. Stays in state.runs after the crawl finishes - unlike the old
    single flat CrawlerState.discovered (wiped on every /start), a run stays
    visible and browsable once it's done, and every discovered/accepted/
    rejected page lives inside its own run instead of one global bucket,
    which is what makes a discovered->accepted->scraped->created hierarchy
    per seed run possible (see /crawler/runs/{run_id})."""
    def __init__(self, run_id: str, seeds: List[str], pages_per_seed: Optional[int], source_entity_class: Optional[str] = None, auto_accept_dated: bool = False):
        self.run_id = run_id
        self.seeds = seeds
        # When true, a newly discovered page with has_dates=True (see
        # crawl_page) skips the manual Accept click and goes straight into
        # `accepted` - toggle on the Start a Crawl form, or live from the
        # run's own page while it's still crawling.
        self.auto_accept_dated = auto_accept_dated
        # Budget PER SEED, not a global cap - each seed gets its own
        # visited-set and frontier (see focused_crawler), so N seeds always
        # yield up to N * pages_per_seed pages instead of the first few
        # seeds' homepages alone exhausting one shared counter before any
        # seed's actual subpages get a turn. None/0 = unlimited (crawl each
        # seed to exhaustion, or until manually stopped via /stop).
        self.pages_per_seed = pages_per_seed
        # entity_class this run's seeds were pulled from (harvest/registry.py's
        # load_registry_domains), if any - None for a plain hand-typed seed
        # list. Purely informational (shown on the run's page) - traceability
        # from "these domains" back to "this harvest registry".
        self.source_entity_class = source_entity_class
        self.started_at = datetime.now().isoformat()
        self.finished_at: Optional[str] = None
        self.status = "running"  # running | done | stopped
        self.pages_crawled = 0
        self.current_seed = ""
        self.seeds_done = 0
        self.discovered: Dict[str, dict] = {}   # url -> metadata (includes "seed": which seed found it)
        self.accepted: List[str] = []
        self.rejected: Set[str] = set()
        # Per-seed frontier snapshot: seed -> {"queue": [...], "visited": [...],
        # "crawled": int}, written after every page (see _crawl_one_seed) and
        # restored on resume - this plus `discovered` is everything needed to
        # continue a seed exactly where it left off instead of re-crawling
        # from its start URL.
        self.seed_state: Dict[str, dict] = {}
        # seed -> GitHub handle that suggested it (see _parse_seed_line and
        # the community-sources.txt "@handle url" format) - deliberately
        # in-memory only, NOT part of to_persist_dict/from_persist_dict: it's
        # a convenience prefill for the create-page form (contributed_by),
        # not data of record, so losing it on a server restart just means
        # re-typing the handle rather than a real data loss.
        self.seed_contributors: Dict[str, str] = {}

    def to_persist_dict(self) -> dict:
        """Full snapshot written to disk after every discovered page (see
        _save_run) - unlike to_dict() below (a small summary for templates/
        the /status JSON endpoint), this includes discovered/accepted/
        rejected/seed_state, i.e. everything needed to reconstruct the run
        and resume it after a server restart."""
        return {
            "run_id": self.run_id,
            "seeds": self.seeds,
            "pages_per_seed": self.pages_per_seed,
            "source_entity_class": self.source_entity_class,
            "auto_accept_dated": self.auto_accept_dated,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "pages_crawled": self.pages_crawled,
            "current_seed": self.current_seed,
            "seeds_done": self.seeds_done,
            "discovered": self.discovered,
            "accepted": self.accepted,
            "rejected": list(self.rejected),
            "seed_state": self.seed_state,
        }

    @classmethod
    def from_persist_dict(cls, d: dict) -> "SeedRun":
        run = cls(d["run_id"], d["seeds"], d["pages_per_seed"], d.get("source_entity_class"), d.get("auto_accept_dated", False))
        run.started_at = d["started_at"]
        run.finished_at = d.get("finished_at")
        # A run that was still "running" when the process died wasn't
        # actually stopped - surface it as "stopped" so it shows up as
        # resumable instead of stuck "running" forever with nothing crawling.
        run.status = "stopped" if d["status"] == "running" else d["status"]
        run.pages_crawled = d.get("pages_crawled", 0)
        run.current_seed = d.get("current_seed", "")
        run.seeds_done = d.get("seeds_done", 0)
        run.discovered = d.get("discovered", {})
        run.accepted = d.get("accepted", [])
        run.rejected = set(d.get("rejected", []))
        run.seed_state = d.get("seed_state", {})
        return run

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "seeds": self.seeds,
            "pages_per_seed": self.pages_per_seed,
            "source_entity_class": self.source_entity_class,
            "auto_accept_dated": self.auto_accept_dated,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "pages_crawled": self.pages_crawled,
            "current_seed": self.current_seed,
            "seeds_done": self.seeds_done,
            "discovered_count": len(self.discovered),
            "accepted_count": len(self.accepted),
            "rejected_count": len(self.rejected),
        }


class CrawlerState:
    """Global, cross-run state: which run (if any) is currently crawling,
    every run started this process lifetime, and the scraper's output.
    scraped/scraping/scrape_errors stay flat/global (keyed by URL) - a URL is
    scraped once regardless of which run discovered it; run detail pages
    filter this global dict down to their own URLs (_scraped_entries_for_run)
    instead of each run keeping its own copy."""
    def __init__(self):
        self.is_running: bool = False
        self.should_stop: bool = False
        self.current_run_id: Optional[str] = None
        self.runs: Dict[str, SeedRun] = {}
        self.scraped: Dict[str, dict] = {}              # url -> {kind, filename, scraped_at}
        self.scraping: Set[str] = set()                # urls a background scrape thread is currently working on
        self.scrape_errors: Dict[str, str] = {}         # url -> last error message (cleared on next success)
        self.lock = threading.Lock()

    def to_dict(self):
        return {
            "is_running": self.is_running,
            "current_run_id": self.current_run_id,
            "runs_count": len(self.runs),
            "scraped_count": len(self.scraped),
        }


state = CrawlerState()


# "@handle https://example.com" (see data/community-sources.txt) - a
# contributor-attributed seed line. Plain "https://example.com" (no leading
# @token) is still just a seed with no known contributor, same as today.
_SEED_LINE = re.compile(r"^(?:@(?P<handle>\S+)\s+)?(?P<seed>\S+)$")


def _parse_seed_line(line: str) -> tuple[str, Optional[str]]:
    """Splits an optional "@handle " prefix off one seed line. Returns
    (seed, handle) - handle is None for a plain seed line."""
    m = _SEED_LINE.match(line)
    if not m:
        return line, None
    return m.group("seed"), m.group("handle")


def _new_run_id() -> str:
    """Timestamp-based, human-legible, sorts chronologically by default dict
    order - a numeric suffix handles the (unlikely but possible) same-second
    double /start."""
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = base
    n = 2
    while run_id in state.runs:
        run_id = f"{base}-{n}"
        n += 1
    return run_id


def _find_run_for_url(url: str) -> Optional[SeedRun]:
    """Which run's `discovered` dict contains this URL, if any - discovered
    pages are scoped per-run now (not one global dict), so anything that
    used to read/write state.discovered[url] (scrape status, title lookups)
    needs to find the owning run first."""
    for run in state.runs.values():
        if url in run.discovered:
            return run
    return None


CRAWLER_STATE_DIR = Path(__file__).parent / "crawler_state"
CRAWLER_STATE_DIR.mkdir(exist_ok=True)


def _run_state_path(run_id: str) -> Path:
    return CRAWLER_STATE_DIR / f"{run_id}.json"


def _save_run(run: SeedRun) -> None:
    """Snapshots `run` to disk - called after every discovered page (see
    _crawl_one_seed) so a killed or restarted server (not just a graceful
    /stop) can resume from the last page it saw instead of losing the whole
    run, same idea as _list_created_pages() reading pages from disk rather
    than memory."""
    _run_state_path(run.run_id).write_text(
        json.dumps(run.to_persist_dict(), ensure_ascii=False), encoding="utf-8"
    )


def _load_runs() -> None:
    """Restores state.runs from CRAWLER_STATE_DIR at process startup - runs
    a server restart (including uvicorn's reload=True, which re-executes
    this module) would otherwise wipe."""
    for path in sorted(CRAWLER_STATE_DIR.glob("*.json")):
        try:
            run = SeedRun.from_persist_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        state.runs[run.run_id] = run


_load_runs()


def is_blacklisted(url: str) -> bool:
    domain = urlparse(url).netloc.lower()
    return any(bad in domain for bad in BLACKLISTED_DOMAINS)

async def crawl_page(client: httpx.AsyncClient, url: str) -> Optional[tuple[dict, str, str]]:
    """Fetch and analyze one page. Returns (result, resolved_url, html) so callers
    don't have to fetch the same page again to extract links."""
    from scraper import extract_dates  # same regex the scraper itself uses later

    try:
        resp = await client.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return None

        html = resp.text
        resolved_url = str(resp.url)
        soup = BeautifulSoup(html, "html.parser")

        title = (soup.title.string or "").strip() if soup.title else ""
        if not title:
            title = _fallback_title_from_url(resolved_url)
        full_text = trafilatura.extract(html, include_comments=False) or ""
        text_preview = full_text[:600].replace("\n", " ")

        # Run against the full extracted text, not just the 600-char preview -
        # a page's dates are often further down than what fits in a preview.
        date_count = len(extract_dates(full_text))

        result = {
            "url": resolved_url,
            "title": title[:120],
            "preview": text_preview[:400],
            "discovered_at": datetime.now().isoformat(),
            "status": "pending",
            "has_dates": date_count > 0,
            "date_count": date_count,
        }
        return result, resolved_url, html
    except Exception:
        return None

async def _crawl_one_seed(client: httpx.AsyncClient, run: SeedRun, seed: str) -> None:
    """Crawls a single seed to its own exhaustion point (run.pages_per_seed
    pages, or unbounded if None/0) with its own visited-set and frontier -
    each seed is independent of every other seed's budget, unlike the old
    single shared queue+counter where N seeds' homepages alone could exhaust
    a small global page cap before any seed's actual subpages got a turn.
    Every discovered page is stamped with "seed" so the UI can group
    Discovered Pages by which seed found them.

    Resumes from run.seed_state[seed] if present (a prior run of this same
    seed was interrupted - by /stop or by the server dying) instead of
    always starting fresh from the seed's start URL."""
    start_url = seed if seed.startswith("http") else f"https://{seed}"
    saved = run.seed_state.get(seed)
    queue = list(saved["queue"]) if saved else [start_url]
    visited: Set[str] = set(saved["visited"]) if saved else set()
    crawled_for_this_seed = saved["crawled"] if saved else 0
    budget = run.pages_per_seed or None  # None = unlimited

    while queue and not state.should_stop and (budget is None or crawled_for_this_seed < budget):
        url = queue.pop(0)
        parsed = urlparse(url)
        domain = parsed.netloc

        if url in visited or is_blacklisted(url):
            continue
        visited.add(url)

        with state.lock:
            run.current_seed = seed

        crawled = await crawl_page(client, url)
        if not crawled:
            continue
        result, resolved_url, html = crawled
        visited.add(resolved_url)  # redirect target counts as visited too
        result["seed"] = seed

        crawled_for_this_seed += 1
        with state.lock:
            run.pages_crawled += 1
            run.discovered[resolved_url] = result
        # Outside the lock above - _accept_and_start_scrape acquires
        # state.lock itself (it's a plain, non-reentrant Lock).
        # ponytail: one background thread per matching page, unbounded - fine
        # at crawl speeds (0.4s/page, one seed at a time), revisit with a
        # worker pool/queue if auto-scrape ever needs to fan out faster than
        # that (e.g. multiple seeds crawled concurrently).
        if run.auto_accept_dated and result.get("has_dates") and resolved_url not in run.rejected:
            _accept_and_start_scrape(run, resolved_url)

        # Find new links (simple, same domain only for focus) - reuse the
        # HTML we already fetched instead of requesting the page again.
        try:
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                # Strip the fragment - "#1"/"#2" anchors on the same page are
                # not distinct pages, and left in they make the crawler queue
                # and re-crawl identical content under N different URLs.
                new_url, _ = urldefrag(urljoin(resolved_url, a["href"]))
                new_parsed = urlparse(new_url)
                if (new_parsed.netloc == domain and
                    new_url not in visited and
                    new_url not in queue and
                    not is_blacklisted(new_url) and
                    len(queue) < 500):
                    queue.append(new_url)
        except Exception:
            pass

        with state.lock:
            run.seed_state[seed] = {"queue": queue, "visited": list(visited), "crawled": crawled_for_this_seed}
        _save_run(run)

        await asyncio.sleep(0.4)  # politeness


async def focused_crawler(run: SeedRun):
    """Crawls every not-yet-completed seed in run.seeds, one seed fully at a
    time (see _crawl_one_seed), writing everything it finds into `run`
    instead of a global bucket - this is what lets a finished run stay
    browsable afterward (state.runs[run.run_id]) instead of being
    overwritten by the next /start. Only one run crawls at a time
    (state.is_running/should_stop stay global and single-flight, same
    restriction as before).

    Doubles as the resume entrypoint (see /crawler/runs/{run_id}/resume):
    run.seeds_done marks how many seeds are FULLY done, so slicing from
    there skips completed seeds and re-enters the in-progress one exactly
    where _crawl_one_seed's saved seed_state left it."""
    global state

    with state.lock:
        state.is_running = True
        state.should_stop = False
        state.current_run_id = run.run_id
        run.status = "running"

    try:
        headers = {"User-Agent": "Wann-Plattform-Crawler/1.0 (+https://github.com/am9zZWY/wann)"}
        async with httpx.AsyncClient(headers=headers) as client:
            for seed in run.seeds[run.seeds_done:]:
                if state.should_stop:
                    break
                await _crawl_one_seed(client, run, seed)
                if state.should_stop:
                    # Seed was interrupted mid-crawl, not completed - leave
                    # seeds_done pointing at it so resume re-enters it
                    # instead of skipping straight to the next seed.
                    break
                with state.lock:
                    run.seeds_done += 1
    finally:
        # Must always reset, even if the crawl loop raised (e.g. bad seed URL,
        # network setup error) - otherwise is_running stays stuck True and
        # /start refuses to ever restart the crawler.
        with state.lock:
            run.status = "stopped" if state.should_stop else "done"
            run.finished_at = datetime.now().isoformat()
            state.is_running = False
            state.should_stop = False
        _save_run(run)

app = FastAPI(title="Wann-Plattform Admin")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

SCRAPED_DIR = Path(__file__).parent / "scraped"
SCRAPED_DIR.mkdir(exist_ok=True)

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

# Allowlist for /pages/{full_path}/delete's return_to - the only two pages
# that render its Delete button (see _pages_table.html), matched exactly
# rather than blocklisted, so no "starts with a single /" style check has to
# anticipate every open-redirect trick (protocol-relative "//", backslash
# variants a browser treats the same way, etc).
_SAFE_RETURN_TO = re.compile(r"^/crawler(?:/runs/[^/]+)?/?$")


def _filename_for(url: str) -> str:
    """Human-readable, collision-safe filename: domain + short hash of the
    full URL (two URLs on the same domain must not get the same filename)."""
    domain = re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(url).netloc).strip("_")
    short_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{domain}_{short_hash}.yaml"


def _fallback_title_from_url(url: str) -> str:
    """Used only when a page has no <title> tag. The full URL by itself is a
    bad fallback for the create-page form's title field: left un-edited by
    an operator, _slugify() turns it into a scheme+domain+path slug for the
    page's folder/URL (e.g. "https-www-example-de-some-page"). The last
    path segment word-for-word is still imperfect but reads as an actual
    title and produces a sane slug if left un-edited."""
    path = urlparse(url).path.strip("/")
    last_segment = path.rsplit("/", 1)[-1] if path else ""
    if not last_segment:
        return urlparse(url).netloc
    words = re.sub(r"[-_]+", " ", last_segment).strip()
    return words.title() if words else urlparse(url).netloc


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


def _find_page_by_url(url: str) -> Optional[tuple[str, str]]:
    """Scans every page folder in data/ (skipping reserved category
    segments at any depth) for a matching source URL, so re-accepting the
    same scrape updates the existing page instead of creating a duplicate -
    possibly under a different category path than the one re-submitted this
    time, which is why the existing (category_path, slug) always wins over
    the form's category input."""
    for category_path, folder in _iter_pages():
        data_path = folder / "data.yaml"
        try:
            existing = yaml.safe_load(data_path.read_text(encoding="utf-8"))
            if existing.get("source", {}).get("url") == url:
                return category_path, folder.name
        except Exception:
            continue
    return None


def _category_and_slug_for_page(url: str, category: str, title: str) -> tuple[str, str]:
    existing = _find_page_by_url(url)
    if existing:
        return existing

    category_path = "/".join(_slugify_category_path(category))
    base = _slugify(title)
    slug = base
    n = 2
    while (DATA_ROOT / category_path / slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return category_path, slug


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


def _discovered_grouped_by_seed(run: SeedRun, limit: int = 200) -> List[dict]:
    """Groups the most recently discovered pages (up to `limit`, same
    recency-cap idea as the old flat list's [-50:]) by which seed found each
    one (see _crawl_one_seed's "seed" stamp), so the Discovered Pages view
    can show "this seed -> these pages" instead of one flat list with no
    indication of provenance. Bounded rather than grouping the entire run:
    an unlimited-budget crawl can discover thousands of pages, and this is
    re-rendered on every 5s poll. Groups follow run.seeds' order (the order
    they were crawled in), not alphabetical - a still-running crawl's
    in-progress seed naturally appears near the bottom instead of jumping
    around as new groups get sorted in."""
    recent = list(run.discovered.values())[-limit:]
    by_seed: Dict[str, List[dict]] = {}
    for page in recent:
        by_seed.setdefault(page.get("seed", ""), []).append(page)
    return [
        {"seed": seed, "pages": by_seed[seed]}
        for seed in run.seeds
        if seed in by_seed
    ]


def _scraped_entries_for_run(run: SeedRun) -> List[dict]:
    """Scraped entries whose URL this run actually discovered - state.scraped
    itself stays global/flat (keyed by URL, shared machinery), this is the
    per-run filter that makes the discovered->accepted->scraped hierarchy
    show up on a run's own page instead of every run seeing every scrape."""
    entries = []
    for entry in sorted(state.scraped.values(), key=lambda s: s["scraped_at"], reverse=True):
        if entry["url"] not in run.discovered:
            continue
        enriched = dict(entry)
        discovered_meta = run.discovered.get(entry["url"], {})
        enriched["title"] = discovered_meta.get("title", entry["url"])
        # Prefills the create-page form's contributed_by field when this
        # entry's seed came from a "@handle seed" line - just a default, the
        # form field stays a plain text input the operator can edit or clear.
        enriched["contributed_by"] = run.seed_contributors.get(discovered_meta.get("seed", ""), "")
        existing_page = _find_page_by_url(entry["url"])
        enriched["page_category"], enriched["page_slug"] = existing_page or (None, None)
        entries.append(enriched)
    return entries


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # This starlette version wants (request, name, context) - the old
    # (name, {"request": request, ...}) call crashes with a confusing
    # "unhashable type: dict" deep inside Jinja2's template cache.
    return templates.TemplateResponse(request, "dashboard.html", {
        "active_nav": "harvest",
        "state": state.to_dict(),
        "harvest_registries": _harvest_registry_status(),
    })


@app.get("/crawler", response_class=HTMLResponse)
async def crawler_list(request: Request):
    runs = sorted(state.runs.values(), key=lambda r: r.started_at, reverse=True)
    return templates.TemplateResponse(request, "crawler.html", {
        "active_nav": "crawler",
        "state": state.to_dict(),
        "runs": [r.to_dict() for r in runs],
        "pages": _list_created_pages(),
        # Only registries that have actually been fetched (count is not
        # None) are useful as a crawl's seed source.
        "harvest_registries": [r for r in _harvest_registry_status() if r["count"] is not None],
        "license_options": LICENSE_OPTIONS,
        "category_suggestions": _category_suggestions(),
        "tag_suggestions": _all_tags(),
    })


@app.get("/crawler/runs/{run_id}", response_class=HTMLResponse)
async def crawler_run_detail(request: Request, run_id: str):
    run = state.runs.get(run_id)
    if run is None:
        return HTMLResponse("Unknown run_id.", status_code=404)
    return templates.TemplateResponse(request, "crawler_run.html", {
        "active_nav": "crawler",
        "state": state.to_dict(),
        "run": run.to_dict(),
        "run_id": run_id,
        "discovered_groups": _discovered_grouped_by_seed(run),
        "scraped": _scraped_entries_for_run(run),
        "pages": [p for p in _list_created_pages() if p["url"] in run.discovered],
        "license_options": LICENSE_OPTIONS,
        "category_suggestions": _category_suggestions(),
        "tag_suggestions": _all_tags(),
    })


@app.get("/crawler/runs/{run_id}/stats-fragment", response_class=HTMLResponse)
async def crawler_run_stats_fragment(request: Request, run_id: str):
    """Polled by the run detail page's #stats-card (every 3s) so the
    crawled/accepted/rejected counters and "currently crawling" domain
    update live while this run is still running."""
    run = state.runs.get(run_id)
    if run is None:
        return HTMLResponse("Unknown run_id.", status_code=404)
    return templates.TemplateResponse(request, "_run_stats_content.html", {"run": run.to_dict()})


@app.get("/crawler/runs/{run_id}/discovered", response_class=HTMLResponse)
async def get_run_discovered(request: Request, run_id: str):
    # Must return the same HTML fragment crawler_run.html includes here -
    # this is used as an hx-swap target (outerHTML), not fetched as data.
    run = state.runs.get(run_id)
    if run is None:
        return HTMLResponse("Unknown run_id.", status_code=404)
    return templates.TemplateResponse(request, "_discovered_table.html", {
        "run_id": run_id,
        "discovered_groups": _discovered_grouped_by_seed(run),
    })


@app.get("/crawler/runs/{run_id}/scraped-table", response_class=HTMLResponse)
async def get_run_scraped_table(request: Request, run_id: str):
    """Polled after a "Scrape" click (see crawler_run.html) since
    /accept-and-scrape only starts a background thread and returns
    immediately - without this, a finished scrape never showed up until the
    next reload."""
    run = state.runs.get(run_id)
    if run is None:
        return HTMLResponse("Unknown run_id.", status_code=404)
    return templates.TemplateResponse(request, "_scraped_table.html", {
        "run_id": run_id,
        "scraped": _scraped_entries_for_run(run),
        "license_options": LICENSE_OPTIONS,
    })

@app.post("/start")
async def start_crawler(
    background_tasks: BackgroundTasks,
    seeds: str = Form(""),
    entity_class: str = Form(""),
    pages_per_seed: str = Form("150"),
    auto_accept_dated: bool = Form(False),
):
    if state.is_running:
        return RedirectResponse("/crawler", status_code=302)

    # Each line may be a plain seed or "@handle seed" (pasted straight from
    # data/community-sources.txt, or hand-typed the same way) - see
    # _parse_seed_line. Handles are collected separately so seed_list itself
    # stays a plain list of seeds, same shape harvest registries append to
    # below.
    parsed_lines = [_parse_seed_line(s.strip()) for s in seeds.splitlines() if s.strip()]
    seed_list = [seed for seed, _ in parsed_lines]
    seed_contributors = {seed: handle for seed, handle in parsed_lines if handle}
    entity_class = entity_class.strip()
    if entity_class:
        # Bulk-seed from an already-fetched harvest registry (e.g. every
        # German university's domain) instead of - or in addition to -
        # hand-typed seeds above; deduped in case a domain appears in both.
        seed_list = list(dict.fromkeys(seed_list + harvest_registry.load_registry_domains(entity_class)))
    if not seed_list:
        return RedirectResponse("/crawler", status_code=302)

    # Empty/0/blank field = unlimited (crawl each seed to exhaustion, stop
    # manually via the Stop button) - str Form field rather than int so an
    # emptied-out number input doesn't 422 before this branch runs.
    pages_per_seed_stripped = pages_per_seed.strip()
    budget = int(pages_per_seed_stripped) if pages_per_seed_stripped else None
    if budget is not None and budget <= 0:
        budget = None

    run = SeedRun(_new_run_id(), seed_list, budget, source_entity_class=entity_class or None, auto_accept_dated=auto_accept_dated)
    run.seed_contributors = seed_contributors
    state.runs[run.run_id] = run
    _save_run(run)
    background_tasks.add_task(focused_crawler, run)
    return RedirectResponse(f"/crawler/runs/{run.run_id}", status_code=302)

@app.post("/stop")
async def stop_crawler():
    with state.lock:
        state.should_stop = True
        redirect_run_id = state.current_run_id
    if redirect_run_id:
        return RedirectResponse(f"/crawler/runs/{redirect_run_id}", status_code=302)
    return RedirectResponse("/crawler", status_code=302)

@app.post("/crawler/runs/{run_id}/resume")
async def resume_crawler(run_id: str, background_tasks: BackgroundTasks):
    """Restarts a stopped run's crawl_loop (see focused_crawler) picking up
    from its persisted seed_state - the resumability the Stop button never
    had for a run that outlives the process, whether stopped on purpose or
    by a server crash/restart."""
    if state.is_running:
        return RedirectResponse(f"/crawler/runs/{run_id}", status_code=302)
    run = state.runs.get(run_id)
    if run is None or run.status != "stopped":
        return RedirectResponse(f"/crawler/runs/{run_id}", status_code=302)
    background_tasks.add_task(focused_crawler, run)
    return RedirectResponse(f"/crawler/runs/{run_id}", status_code=302)

def _accept_and_start_scrape(run: SeedRun, url: str) -> None:
    """Marks `url` accepted on `run` (still kept for the run's accepted_count
    stat and /delete-unscraped's cleanup) and kicks off its background
    scrape - the one thing both a manual Discovered-table Scrape click
    (/accept-and-scrape) and auto-scraping a dated page during a live crawl
    (see _crawl_one_seed) need to do. Callers must NOT hold state.lock when
    calling this - it acquires it itself."""
    with state.lock:
        if url in run.discovered and url not in run.accepted:
            run.accepted.append(url)
            run.discovered[url]["status"] = "accepted"
        state.scraping.add(url)
    _save_run(run)
    threading.Thread(target=_scrape_and_record, args=(url,), daemon=True).start()


@app.post("/accept-and-scrape")
async def accept_and_scrape(run_id: str = Form(...), url: str = Form(...)):
    """Discovered -> Scrape in one click - no manual Accept step, no
    separate Accepted-Pages table to switch to."""
    run = state.runs.get(run_id)
    if run is None:
        return JSONResponse({"error": "Unknown run_id."}, status_code=404)
    _accept_and_start_scrape(run, url)
    return JSONResponse({"status": "started", "url": url})


@app.post("/reject")
async def reject_url(run_id: str = Form(...), url: str = Form(...)):
    run = state.runs.get(run_id)
    if run is None:
        return HTMLResponse("Unknown run_id.", status_code=404)
    with state.lock:
        run.rejected.add(url)
        if url in run.discovered:
            run.discovered[url]["status"] = "rejected"
        if url in run.accepted:
            run.accepted.remove(url)
    _save_run(run)
    return RedirectResponse(f"/crawler/runs/{run_id}", status_code=302)

@app.post("/crawler/runs/{run_id}/auto-accept-dated")
async def toggle_auto_accept_dated(run_id: str):
    """Flips a run's auto_accept_dated - a crawl can run for a long time, so
    this is reachable from the run's own page while it's still going, not
    just at Start-a-Crawl time."""
    run = state.runs.get(run_id)
    if run is None:
        return JSONResponse({"error": "Unknown run_id."}, status_code=404)
    with state.lock:
        run.auto_accept_dated = not run.auto_accept_dated
    _save_run(run)
    return JSONResponse({"auto_accept_dated": run.auto_accept_dated})


@app.get("/status")
async def get_status():
    """JSON endpoint for external polling/tooling."""
    return JSONResponse(state.to_dict())

@app.get("/status-fragment", response_class=HTMLResponse)
async def get_status_fragment(request: Request):
    """Polled by the shared header (every 3s, see _base.html's
    #status-indicator) - just the global running/idle badge; per-run stats
    live on that run's own page (see /crawler/runs/{run_id}/stats-fragment)."""
    return templates.TemplateResponse(request, "_status_fragment.html", {"state": state.to_dict()})


def _content_hash(result: dict) -> str:
    """Stable hash of a scrape's actual content, ignoring fields that always
    differ between runs regardless of whether the source page changed
    (extracted_at) - lets re-scrapes detect "did this really change" instead
    of always looking different."""
    stable = {k: v for k, v in result.items() if k not in ("extracted_at", "url")}
    encoded = json.dumps(stable, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scrape_and_record(url: str) -> None:
    """Fetches+extracts `url` (core/scraper.py), saves the YAML, and updates
    state.scraped/scrape_errors/scraping - shared by _accept_and_start_scrape
    (one URL, triggered manually or by auto-scrape) and rescrape (every
    already-scraped URL for a run), so all of them go through the exact same
    content-hash/changed-detection logic instead of near-duplicate copies
    drifting apart."""
    from scraper import (
        SimpleScraper,  # assumes scraper.py is in parent dir or PYTHONPATH
    )

    try:
        scraper = SimpleScraper()
        result = scraper.scrape(url)
        filename = _filename_for(url)
        scraper.save(result, str(SCRAPED_DIR / filename))

        new_hash = _content_hash(result)
        with state.lock:
            previous = state.scraped.get(url)
            changed = None if previous is None else new_hash != previous.get("content_hash")
            state.scraped[url] = {
                "url": url,
                "kind": result.get("kind", "unknown"),
                "filename": filename,
                "scraped_at": datetime.now().isoformat(),
                "content_hash": new_hash,
                "changed": changed,
            }
            owning_run = _find_run_for_url(url)
            if owning_run is not None:
                owning_run.discovered[url]["status"] = "scraped"
            state.scrape_errors.pop(url, None)
            state.scraping.discard(url)

        print(f"[Admin] Scraper finished for {url} -> {filename} (changed={changed})")
    except Exception as e:
        with state.lock:
            state.scrape_errors[url] = str(e)[:300]
            state.scraping.discard(url)
        print(f"[Admin] Scraper error for {url}: {e}")


class RescrapeState:
    """Tracks one rescrape run so the dashboard can poll its progress -
    module-level (not on CrawlerState) since it's a one-shot batch operation,
    not part of any single SeedRun's own lifecycle. Still single-flight
    globally (one rescrape batch at a time) even though the URL set it
    operates on is now chosen per call (see /crawler/runs/{run_id}/rescrape-all)."""
    def __init__(self):
        self.running = False
        self.total = 0
        self.done = 0
        self.changed_urls: List[str] = []

    def to_dict(self):
        return {
            "running": self.running,
            "total": self.total,
            "done": self.done,
            "changed_urls": self.changed_urls,
        }


rescrape_state = RescrapeState()


@app.post("/crawler/runs/{run_id}/rescrape-all")
async def rescrape_run(run_id: str):
    """Re-scrapes every already-scraped URL that THIS run discovered
    (sequentially, in the background) - scoped per run rather than globally,
    since a run's own page is where "did any of my sources change" is asked
    from, and where the changed-URL alert makes sense to react to."""
    run = state.runs.get(run_id)
    if run is None:
        return JSONResponse({"error": "Unknown run_id."}, status_code=404)
    if rescrape_state.running:
        return JSONResponse({"error": "A re-scrape is already running."}, status_code=409)

    urls = [u for u in state.scraped.keys() if u in run.discovered]
    rescrape_state.running = True
    rescrape_state.total = len(urls)
    rescrape_state.done = 0
    rescrape_state.changed_urls = []

    def _run_all():
        try:
            for url in urls:
                with state.lock:
                    state.scraping.add(url)
                _scrape_and_record(url)
                if state.scraped.get(url, {}).get("changed"):
                    rescrape_state.changed_urls.append(url)
                rescrape_state.done += 1
        finally:
            rescrape_state.running = False

    threading.Thread(target=_run_all, daemon=True).start()
    return JSONResponse({"status": "started", "total": len(urls)})


@app.post("/crawler/runs/{run_id}/scrape-all")
async def scrape_all_discovered(run_id: str):
    """Scrapes every URL this run has discovered but not yet scraped or
    rejected, sequentially in the background - same batch machinery as
    rescrape-all (rescrape_state/RescrapeState) and the same single-flight
    guard (only one batch scrape makes sense at a time, and both write into
    state.scraping), just a different URL set and nothing to compare
    against (changed_urls stays empty). Marks each URL accepted as it starts
    (same bookkeeping as a per-row Scrape click/_accept_and_start_scrape),
    just done inline in this loop rather than via that helper - it spawns
    its own thread per call, which would defeat the point of scraping this
    batch one at a time."""
    run = state.runs.get(run_id)
    if run is None:
        return JSONResponse({"error": "Unknown run_id."}, status_code=404)
    if rescrape_state.running:
        return JSONResponse({"error": "A scrape batch is already running."}, status_code=409)

    urls = [u for u in run.discovered if u not in state.scraped and u not in run.rejected]
    rescrape_state.running = True
    rescrape_state.total = len(urls)
    rescrape_state.done = 0
    rescrape_state.changed_urls = []

    def _run_all():
        try:
            for url in urls:
                with state.lock:
                    if url not in run.accepted:
                        run.accepted.append(url)
                    run.discovered[url]["status"] = "accepted"
                    state.scraping.add(url)
                _scrape_and_record(url)
                rescrape_state.done += 1
        finally:
            rescrape_state.running = False
            _save_run(run)

    threading.Thread(target=_run_all, daemon=True).start()
    return JSONResponse({"status": "started", "total": len(urls)})


@app.get("/rescrape-status")
async def rescrape_status():
    """Polled by the run detail page's "Re-scrape All" button while a batch
    re-scrape is running."""
    return JSONResponse(rescrape_state.to_dict())


@app.get("/scrape-status")
async def scrape_status(url: str):
    """Polled by the dashboard's Scrape button while state.scraping still
    contains `url`, so the button's disabled/"Running…" state reflects the
    real background scrape rather than /accept-and-scrape's near-instant
    response. `error` surfaces a failure (e.g. a scraper bug) that used to
    only ever be printed server-side."""
    return JSONResponse({
        "done": url in state.scraped,
        "error": state.scrape_errors.get(url),
    })


class HarvestRegistryState:
    """Tracks in-flight harvest registry fetches per entity_class, same
    background-thread-plus-polling pattern as RescrapeState/state.scraping -
    a registry fetch is one blocking network call (Wikidata SPARQL), too slow
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
    (see harvest/registry.py's USER_AGENT)."""
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
    fetch_registry() implements so far (see harvest/registry.py)."""
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


def _text_for_llm_extraction(raw_data: dict) -> str:
    """Best-effort plain-text view of whatever the scraper produced, for
    feeding to the LLM. html_page is the main case (see core/extraction.py's
    docstring for why); the others are included for completeness but are
    usually already structured enough not to need this."""
    kind = raw_data.get("kind")
    if kind in ("html_page", "image_page"):
        return raw_data.get("clean_markdown_full") or raw_data.get("clean_markdown_preview", "")
    if kind == "tabular_text":
        columns = raw_data.get("columns", [])
        rows = raw_data.get("rows_preview", [])
        lines = [" | ".join(columns)]
        lines += [" | ".join(str(row.get(c, "")) for c in columns) for row in rows]
        return "\n".join(lines)
    if kind == "directory_listing":
        return "\n".join(e.get("name", "") for e in raw_data.get("entries", []))
    if kind == "plain_text":
        return raw_data.get("preview", "")
    return ""


@app.post("/extract-llm")
async def extract_llm(url: str = Form(...)):
    """Runs LLM-based date extraction (core/extraction.py) on an already-
    scraped result and merges it into the saved scraped YAML as `llm_events`,
    so a subsequent Create Page picks it up automatically (raw_data is copied
    verbatim from that same file). For pages the regex-based extract_dates()
    can't handle - see core/extraction.py's docstring."""
    from core.extraction import ExtractionError, extract_dated_events

    if url not in state.scraped:
        return JSONResponse({"error": "This URL has not been scraped yet."}, status_code=400)

    filename = state.scraped[url]["filename"]
    raw_path = SCRAPED_DIR / filename
    raw_data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    text = _text_for_llm_extraction(raw_data)

    try:
        events = await asyncio.to_thread(extract_dated_events, text)
    except ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    raw_data["llm_events"] = events
    with raw_path.open("w", encoding="utf-8") as f:
        yaml.dump(raw_data, f, allow_unicode=True, sort_keys=False)

    return JSONResponse({"status": "ok", "count": len(events), "events": events})


@app.post("/suggest-tags")
async def suggest_tags_route(url: str = Form(...)):
    """Suggests tags for an already-scraped result (core/extraction.py's
    suggest_tags()), preferring the site's existing tag vocabulary (_all_tags())
    over inventing new ones - see the create-page form's "Suggest Tags" button."""
    from core.extraction import ExtractionError, suggest_tags

    if url not in state.scraped:
        return JSONResponse({"error": "This URL has not been scraped yet."}, status_code=400)

    filename = state.scraped[url]["filename"]
    raw_path = SCRAPED_DIR / filename
    raw_data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    text = _text_for_llm_extraction(raw_data)
    owning_run = _find_run_for_url(url)
    title = owning_run.discovered.get(url, {}).get("title", url) if owning_run else url

    try:
        tags = await asyncio.to_thread(suggest_tags, text, title, _all_tags())
    except ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    return JSONResponse({"status": "ok", "tags": tags})


@app.post("/suggest-title")
async def suggest_title_route(url: str = Form(...)):
    """Cleans up an already-scraped result's raw <title> tag (core/
    extraction.py's suggest_title()) - the raw title (crawl_page()) is often
    polluted with year ranges and a duplicated site name, see the create-page
    form's "Suggest Title" button."""
    from core.extraction import ExtractionError, suggest_title

    if url not in state.scraped:
        return JSONResponse({"error": "This URL has not been scraped yet."}, status_code=400)

    filename = state.scraped[url]["filename"]
    raw_path = SCRAPED_DIR / filename
    raw_data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    text = _text_for_llm_extraction(raw_data)
    owning_run = _find_run_for_url(url)
    raw_title = owning_run.discovered.get(url, {}).get("title", url) if owning_run else url

    try:
        title = await asyncio.to_thread(suggest_title, text, raw_title)
    except ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    return JSONResponse({"status": "ok", "title": title})


@app.post("/suggest-category")
async def suggest_category_route(url: str = Form(...)):
    """Suggests a category for an already-scraped result (core/
    extraction.py's suggest_category()), preferring the site's existing
    category vocabulary (_category_suggestions()) over inventing a new one -
    see the create-page form's "Suggest Category" button."""
    from core.extraction import ExtractionError, suggest_category

    if url not in state.scraped:
        return JSONResponse({"error": "This URL has not been scraped yet."}, status_code=400)

    filename = state.scraped[url]["filename"]
    raw_path = SCRAPED_DIR / filename
    raw_data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))
    text = _text_for_llm_extraction(raw_data)
    owning_run = _find_run_for_url(url)
    title = owning_run.discovered.get(url, {}).get("title", url) if owning_run else url

    try:
        category = await asyncio.to_thread(suggest_category, text, title, _category_suggestions())
    except ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    return JSONResponse({"status": "ok", "category": category})


@app.post("/delete-unscraped")
async def delete_unscraped():
    """Purge every discovered/accepted/rejected entry that hasn't actually
    been scraped yet, across every run - a cleanup action for review queues
    that grew too big, not a way to remove real scraped output (that stays
    on disk in /scraped regardless)."""
    with state.lock:
        for run in state.runs.values():
            run.discovered = {u: v for u, v in run.discovered.items() if u in state.scraped}
            run.accepted = [u for u in run.accepted if u in state.scraped]
            run.rejected = {u for u in run.rejected if u in state.scraped}
    for run in state.runs.values():
        _save_run(run)
    return RedirectResponse("/crawler", status_code=302)


@app.get("/scraped/{filename}", response_class=HTMLResponse)
async def get_scraped_yaml(filename: str):
    """Raw YAML output for one scraped entry, plain text so the browser just
    shows it. filename is our own generated hash-suffixed name, not
    user-controlled path input, but resolve()+parent-check still guards
    against any '../' shenanigans."""
    path = (SCRAPED_DIR / filename).resolve()
    if path.parent != SCRAPED_DIR.resolve() or not path.exists():
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")


@app.post("/create-page")
async def create_page(
    url: str = Form(...),
    title: str = Form(...),
    category: str = Form(...),
    tags: str = Form(""),
    license: str = Form(...),
    run_id: str = Form(""),
    contributed_by: str = Form(""),
):
    """Promotes an already-scraped result into data/{category}/{slug}/, which
    the Astro build picks up dynamically via lib/pages.ts as /{category}/{slug}/
    (see PLAN.md section 2 for the constitutional-rule conflict this
    deliberately accepts). Two files, on purpose: data.yaml is rewritten every
    time (the facts), page.yaml is only written the first time (so a human's
    title/description/tags edits survive a later re-scrape of the same URL) -
    see lib/pages-schema.ts. run_id is optional and only used to redirect back
    to the run this URL came from (see _scraped_table.html's hidden field) -
    the created page itself doesn't record it (data.yaml has no notion of
    "which crawl run", only "which source URL")."""
    if url not in state.scraped:
        return HTMLResponse("This URL has not been scraped yet.", status_code=400)
    if license not in LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    validation_error = _validate_category_segments(_slugify_category_path(category))
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)

    scraped_entry = state.scraped[url]
    raw_path = SCRAPED_DIR / scraped_entry["filename"]
    raw_data = yaml.safe_load(raw_path.read_text(encoding="utf-8"))

    category_path, slug = _category_and_slug_for_page(url, category, title)
    folder = DATA_ROOT / category_path / slug
    folder.mkdir(parents=True, exist_ok=True)
    _write_category_meta_if_new(category)

    source = {
        "url": url,
        "license": license,
        "retrieved_at": date.today().isoformat(),
        "extraction": "parser",  # scraper.py is deterministic content-sniffing, not an LLM call
    }
    contributed_by = contributed_by.strip()
    if contributed_by:
        # Credits whoever suggested this URL (see data/community-sources.txt's
        # "@handle url" format and _parse_seed_line) - optional field on
        # lib/schema.ts's sourceSchema, rendered by SourceList.astro. Left
        # out entirely rather than an empty string when nobody's credited,
        # so existing data.yaml files with no notion of this field stay
        # exactly as they are.
        source["contributed_by"] = contributed_by

    data = {
        "subject": {"slug": slug, "category": category_path},
        # source.py uses the SAME field names as lib/schema.ts's sourceSchema
        # (existing, established vocabulary) - url/license/retrieved_at/extraction.
        "source": source,
        "raw_data": raw_data,
    }
    with (folder / "data.yaml").open("w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    page_path = folder / "page.yaml"
    if not page_path.exists():
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        page = {"title": title, "description": "", "tags": tag_list}
        with page_path.open("w", encoding="utf-8") as f:
            yaml.dump(page, f, allow_unicode=True, sort_keys=False)

    if run_id:
        return RedirectResponse(f"/crawler/runs/{run_id}", status_code=302)
    return RedirectResponse("/crawler", status_code=302)


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
async def delete_page(full_path: str, return_to: str = Form("/crawler")):
    """Deletes a created page's whole folder (data.yaml + page.yaml) from
    data/ - the Admin UI's Delete button (and bulk "Delete Selected") on the
    created-pages table. return_to is allowlisted (not just blocklisted)
    against the only two pages that render this button - a blocklist like
    "must start with '/' and not '//'" still lets through backslash tricks
    browsers treat as protocol-relative ("/\evil.com")."""
    folder = _resolve_page_folder(full_path)
    if folder is None:
        return HTMLResponse("Not found", status_code=404)
    shutil.rmtree(folder)
    if not _SAFE_RETURN_TO.match(return_to):
        return_to = "/crawler"
    return RedirectResponse(return_to, status_code=302)


@app.post("/pages/{full_path:path}/edit")
async def edit_page(
    full_path: str,
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    category: str = Form(...),
    license: str = Form(...),
    return_to: str = Form("/crawler"),
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
    source = data.get("source") or {}
    if isinstance(source, list):
        source = source[0] if source else {}
    source["license"] = license
    data["source"] = source
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
        return_to = "/crawler"
    return RedirectResponse(return_to, status_code=302)


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
