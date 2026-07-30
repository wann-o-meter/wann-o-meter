"""Crawl-source CRUD plus run/status polling."""

import shutil
import threading
from urllib.parse import urlparse

import yaml
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core import crawl_config, review_state, staging
from review import service

router = APIRouter()


@router.get("/crawl-sources", response_class=HTMLResponse)
async def crawl_sources_list(request: Request):
    return service.templates.TemplateResponse(
        request,
        "crawl_sources.html",
        {
            "active_nav": "crawl-sources",
            "state": service.state.to_dict(),
            "sources": crawl_config.load_all_crawl_sources(),
            "running_sources": service.state.running_sources,
            "errors": service.state.errors,
            "last_result": service.state.last_result,
            "progress": service.state.progress,
            "category_suggestions": service._category_suggestions(),
            "format_options": service.CRAWL_FORMAT_OPTIONS,
        },
    )


@router.get("/crawl-sources-table", response_class=HTMLResponse)
async def crawl_sources_table(request: Request):
    """htmx refresh target after a Run click (see crawl_sources.html's JS
    poll) - same "re-render the whole table from the server" approach as
    the old harvest registry table, so count/error/button state all come
    from one source of truth."""
    return service.templates.TemplateResponse(
        request,
        "_crawl_sources_table.html",
        {
            "sources": crawl_config.load_all_crawl_sources(),
            "running_sources": service.state.running_sources,
            "errors": service.state.errors,
            "last_result": service.state.last_result,
            "progress": service.state.progress,
        },
    )


@router.post("/crawl-sources/{source_id}/run")
async def run_crawl_source(source_id: str):
    sources = crawl_config.load_all_crawl_sources()
    if source_id not in sources:
        return JSONResponse({"error": f"Unknown crawl source '{source_id}'"}, status_code=404)
    if source_id in service.state.running_sources:
        return JSONResponse({"error": "This source is already running."}, status_code=409)
    service.state.running_sources.add(source_id)
    threading.Thread(target=service._run_crawl_source_and_record, args=(source_id,), daemon=True).start()
    return JSONResponse({"status": "started", "source_id": source_id})


@router.get("/crawl-sources/{source_id}/status")
async def crawl_source_status(source_id: str):
    """Polled by crawl_sources.html's Run button while a crawl is in
    flight - same reasoning as the harvest registry status poll: the POST
    above returns almost instantly, the real crawl runs in the background
    thread."""
    return JSONResponse(
        {
            "running": source_id in service.state.running_sources,
            "error": service.state.errors.get(source_id),
            "result": service.state.last_result.get(source_id),
            "progress": service.state.progress.get(source_id),
            # Carried on this same poll rather than a second endpoint/timer -
            # two polls against one source would just double the request rate
            # to show two halves of the same run.
            "pages": service._source_pages(source_id),
        }
    )


@router.post("/crawl-sources/{source_id}/delete")
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
    if source_id in service.state.running_sources:
        return HTMLResponse("This source is currently running - wait for it to finish first.", status_code=409)

    source.config_path.unlink()
    service.state.errors.pop(source_id, None)
    service.state.last_result.pop(source_id, None)
    return RedirectResponse("/crawl-sources", status_code=303)


@router.post("/crawl-sources/new")
async def create_crawl_source(
    seed_url: str = Form(...),
    id: str = Form(""),
    category: str = Form(""),
    allowed_domains: str = Form(""),
    path_prefix: str = Form(""),
    max_depth: int = Form(crawl_config.DEFAULT_MAX_DEPTH),
    formats: list[str] = Form(["html"]),
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
        id = service._slugify(id)
    else:
        # Two seed URLs on the same domain (e.g. /solar and /lunar sections)
        # would otherwise both derive the same domain-only id - fall back to
        # domain+first-path-segment before giving up and asking for a
        # custom id.
        id = service._slugify(domain)
        if (crawl_config.CRAWL_SOURCES_DIR / f"{id}.yaml").exists():
            path_segments = [s for s in parsed.path.split("/") if s]
            if path_segments:
                id = f"{id}-{service._slugify(path_segments[0])}"
    path = crawl_config.CRAWL_SOURCES_DIR / f"{id}.yaml"
    if path.exists():
        return HTMLResponse(
            f"A crawl source '{id}' already exists - set a custom ID under Advanced options "
            "(this domain already has a source at that same path).",
            status_code=409,
        )

    category_path = "/".join(service._slugify_category_path(category or id))
    validation_error = service._validate_category_segments(category_path.split("/") if category_path else [])
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)

    domains = [d.strip() for d in allowed_domains.split(",") if d.strip()] or [domain]
    scope = {"allowed_domains": domains}
    derived_path_prefix = path_prefix.strip() or service._derive_path_prefix(parsed.path)
    if derived_path_prefix:
        scope["path_prefix"] = derived_path_prefix

    raw = {
        "id": id,
        "seed_url": seed_url,
        "category": category_path,
        # Blank means "its own page", i.e. the id - the same default
        # crawl_config._parse applies. A shared value is what aggregates
        # several sources into one page.
        "subject_slug": service._slugify(subject_slug) if subject_slug.strip() else id,
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


@router.post("/crawl-sources/{source_id}/edit")
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
    if source_id in service.state.running_sources:
        return HTMLResponse("This source is currently running - wait for it to finish first.", status_code=409)

    category_path = "/".join(service._slugify_category_path(category))
    validation_error = service._validate_category_segments(category_path.split("/") if category_path else [])
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)

    raw = yaml.safe_load(source.config_path.read_text(encoding="utf-8")) or {}
    raw.update(
        {
            "category": category_path,
            # Deliberately NOT _slugify'd, unlike the create route: on an edit
            # the operator is matching another source's slug character for
            # character, and silently rewriting a typo into a valid-but-different
            # slug would quietly create a third page instead of saying so.
            # _parse's _SLUG_RE is the validator.
            "subject_slug": subject_slug.strip(),
            "subject_name": subject_name.strip(),
            "event_type_hint": event_type_hint.strip(),
        }
    )
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
        old_folder = service.DATA_ROOT / source.category / source.subject_slug
        new_folder = service.DATA_ROOT / category_path / parsed.subject_slug
        error = service._migrate_page_folder(old_folder, new_folder, parsed.subject_slug, category_path)
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
