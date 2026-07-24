#!/usr/bin/env python3
"""
Wann-Plattform Admin Dashboard
FastAPI + Jinja2 (SSR) + HTMX

Features:
- Configure and run scoped crawl sources (pipeline/config/crawl_sources/*.yaml)
- Review extracted candidates (approve/modify/reject) against their source
  document snapshot, with already-reviewed candidates auto-waved-through
- Maintain already-created pages (edit/delete/tag)
- Harvest registries (bulk entity lists from Wikidata)
"""

import asyncio
import json
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import uvicorn
import yaml
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from core import approval, crawl_config, crawl_runner, review_state, staging
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

    def to_dict(self) -> dict:
        return {
            "is_running": bool(self.running_sources),
            "running_sources": sorted(self.running_sources),
        }


state = PipelineState()

app = FastAPI(title="Wann-Plattform Admin")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

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

# Allowlist for /pages/{full_path}/delete's return_to - the only pages that
# render its Delete button (see _pages_table.html), matched exactly rather
# than blocklisted, so no "starts with a single /" style check has to
# anticipate every open-redirect trick (protocol-relative "//", backslash
# variants a browser treats the same way, etc).
_SAFE_RETURN_TO = re.compile(r"^/(?:crawl-sources|review)(?:/[^/]+)?/?$")


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


def _known_source_ids() -> List[str]:
    """Every source_id with either a crawl_sources/*.yaml config or an
    existing staging/ directory - the latter covers sources.yaml-based
    automated sources too (e.g. schulferien_kmk, run via `python -m
    core.runner`), since both subsystems write into the same
    pipeline/staging/ + review-state/ structure (Decision B: one unified
    review queue regardless of which subsystem produced a candidate)."""
    ids = set(crawl_config.load_all_crawl_sources().keys())
    if staging.STAGING_ROOT.exists():
        ids.update(p.name for p in staging.STAGING_ROOT.iterdir() if p.is_dir())
    return sorted(ids)


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
    decisions = review_state.load(source_id)["decisions"]
    pending = []
    for path in sorted(candidates_dir.glob("*.yaml")):
        candidate = yaml.safe_load(path.read_text(encoding="utf-8"))
        if candidate["content_hash"] not in decisions:
            candidate["run_ts"] = run_ts
            pending.append(candidate)
    return pending


def _review_queue() -> List[dict]:
    return [c for source_id in _known_source_ids() for c in _pending_candidates_for(source_id)]


def _all_disappeared() -> List[dict]:
    out = []
    for source_id in _known_source_ids():
        disappeared = review_state.load(source_id)["disappeared"]
        for content_hash, entry in disappeared.items():
            out.append({"source_id": source_id, "content_hash": content_hash, **entry})
    return out


def _load_candidate(source_id: str, run_ts: str, candidate_id: str) -> Optional[dict]:
    path = staging.STAGING_ROOT / source_id / run_ts / "candidates" / f"{candidate_id.replace(':', '_')}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run_crawl_source_and_record(source_id: str) -> None:
    try:
        source = crawl_config.load_all_crawl_sources().get(source_id)
        if source is None:
            raise ValueError(f"Unknown crawl source '{source_id}'")
        result = crawl_runner.run(source)
        state.last_result[source_id] = result
        state.errors.pop(source_id, None)
    except Exception as e:
        state.errors[source_id] = str(e)[:300]
    finally:
        state.running_sources.discard(source_id)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {
        "active_nav": "harvest",
        "state": state.to_dict(),
        "harvest_registries": _harvest_registry_status(),
        "pages": _list_created_pages(),
        "category_suggestions": _category_suggestions(),
        "tag_suggestions": _all_tags(),
        "review_queue_count": len(_review_queue()),
        "disappeared_count": len(_all_disappeared()),
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
    })


@app.get("/review", response_class=HTMLResponse)
async def review_queue_view(request: Request):
    return templates.TemplateResponse(request, "review.html", {
        "active_nav": "review",
        "state": state.to_dict(),
        "queue": _review_queue(),
        "disappeared": _all_disappeared(),
    })


@app.get("/review/{source_id}/{candidate_id}", response_class=HTMLResponse)
async def review_candidate_detail(request: Request, source_id: str, candidate_id: str):
    run_ts = _latest_run_ts(source_id)
    candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)

    doc_hash = candidate["document"]
    doc_meta = staging.read_document_meta(source_id, run_ts, doc_hash)
    documents_dir = staging.STAGING_ROOT / source_id / run_ts / "documents"
    doc_path = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None)
    is_text = doc_path is not None and doc_path.suffix in (".md", ".ics")

    return templates.TemplateResponse(request, "_candidate_review.html", {
        "state": state.to_dict(),
        "source_id": source_id,
        "candidate": candidate,
        "document_meta": doc_meta,
        "document_text": doc_path.read_text(encoding="utf-8") if is_text else None,
        "document_url": f"/staging-document/{source_id}/{run_ts}/{doc_hash}" if doc_path and not is_text else None,
        "license_options": LICENSE_OPTIONS,
        "category_suggestions": _category_suggestions(),
    })


_STAGING_DOCUMENT_MEDIA_TYPES = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".gif": "image/gif", ".ics": "text/calendar", ".md": "text/markdown; charset=utf-8",
}


@app.get("/staging-document/{source_id}/{run_ts}/{doc_hash}")
async def get_staging_document(source_id: str, run_ts: str, doc_hash: str):
    """Serves one staged document snapshot for the review UI - same guard
    pattern as /page-data (resolve()+parent-check), since source_id/run_ts
    come straight from the URL."""
    documents_dir = (staging.STAGING_ROOT / source_id / run_ts / "documents").resolve()
    if staging.STAGING_ROOT.resolve() not in documents_dir.parents:
        return HTMLResponse("Not found", status_code=404)
    match = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None) if documents_dir.exists() else None
    if match is None:
        return HTMLResponse("Not found", status_code=404)
    media_type = _STAGING_DOCUMENT_MEDIA_TYPES.get(match.suffix, "application/octet-stream")
    return Response(content=match.read_bytes(), media_type=media_type)


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


@app.post("/review/{source_id}/{candidate_id}/approve")
async def approve_candidate(
    source_id: str,
    candidate_id: str,
    category: str = Form(...),
    license: str = Form(...),
):
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

    quelle = _quelle_for_candidate(source_id, candidate, license)
    try:
        approval.write_event(category_path, candidate["subject_slug"], candidate["subject_slug"], candidate["event"], quelle)
    except approval.ApprovalError as e:
        return HTMLResponse(f"Validation failed, nothing written:\n{e}", status_code=400)
    _write_category_meta_if_new(category)

    target_file = str(approval.DATA_ROOT / category_path / candidate["subject_slug"] / "data.yaml")
    st = review_state.load(source_id)
    review_state.record_decision(st, candidate["content_hash"], "approved", target_file, candidate["event"])
    review_state.save(source_id, st)
    return RedirectResponse("/review", status_code=302)


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
        approval.write_event(category_path, candidate["subject_slug"], candidate["subject_slug"], corrected_event, quelle)
    except approval.ApprovalError as e:
        return HTMLResponse(f"Validation failed, nothing written:\n{e}", status_code=400)
    _write_category_meta_if_new(category)

    target_file = str(approval.DATA_ROOT / category_path / candidate["subject_slug"] / "data.yaml")
    st = review_state.load(source_id)
    review_state.record_decision(
        st, candidate["content_hash"], "modified", target_file, candidate["event"], corrected_event=corrected_event
    )
    review_state.save(source_id, st)
    return RedirectResponse("/review", status_code=302)


@app.post("/review/{source_id}/{candidate_id}/reject")
async def reject_candidate(source_id: str, candidate_id: str):
    run_ts = _latest_run_ts(source_id)
    candidate = _load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)

    st = review_state.load(source_id)
    review_state.record_decision(st, candidate["content_hash"], "rejected", "", candidate["event"])
    review_state.save(source_id, st)
    return RedirectResponse("/review", status_code=302)


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
        return_to = "/crawl-sources"
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
