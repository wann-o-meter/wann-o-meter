"""Wikidata registry harvesting (bulk entity lists)."""

import asyncio
import re
import threading

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from review import service
from sources import registry as harvest_registry

router = APIRouter()


@router.get("/harvest", response_class=HTMLResponse)
async def harvest_view(request: Request):
    """Stage 1 of the entity-first harvest pipeline (see sources/registry.py) -
    fetches a known entity class's registry into pipeline/data/registries/.
    Stages 2-7 don't exist yet, so nothing downstream consumes it: its one
    designed bridge into the crawler (registry.load_registry_domains) has no
    caller. Kept and given its own page rather than mixed into the pages
    dashboard, so the pipeline nav reads as the pipeline."""
    return service.templates.TemplateResponse(request, "harvest.html", {
        "active_nav": "harvest",
        "state": service.state.to_dict(),
        "harvest_registries": service._harvest_registry_status(),
    })

@router.get("/harvest/wikidata-search")
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

@router.post("/harvest/registries/config")
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

@router.post("/harvest/registry")
async def start_harvest_registry(entity_class: str = Form(...)):
    if entity_class not in harvest_registry.load_registries_config():
        return JSONResponse({"error": f"Unknown entity_class '{entity_class}'"}, status_code=400)
    if entity_class in service.harvest_registry_state.running:
        return JSONResponse({"error": "A fetch for this entity_class is already running."}, status_code=409)

    service.harvest_registry_state.running.add(entity_class)
    threading.Thread(target=service._fetch_harvest_registry_and_record, args=(entity_class,), daemon=True).start()
    return JSONResponse({"status": "started", "entity_class": entity_class})

@router.get("/harvest/registry-status")
async def harvest_registry_status_route(entity_class: str):
    """Polled by the dashboard's Fetch Registry button - same reasoning as
    /scrape-status: the POST above returns almost instantly, the real fetch
    happens in the background thread."""
    return JSONResponse({
        "running": entity_class in service.harvest_registry_state.running,
        "error": service.harvest_registry_state.errors.get(entity_class),
    })

@router.get("/harvest/registry-table", response_class=HTMLResponse)
async def harvest_registry_table(request: Request):
    return service.templates.TemplateResponse(request, "_harvest_registry_table.html", {
        "harvest_registries": service._harvest_registry_status(),
    })

@router.post("/harvest/registries/{entity_class}/delete", response_class=HTMLResponse)
async def delete_harvest_registry(request: Request, entity_class: str):
    """Removes entity_class from config/registries.yaml and deletes its
    fetched data/registries/<entity_class>.json, if any - the Admin UI's
    Delete Registry button. Refuses while a fetch is in-flight for it."""
    if entity_class in service.harvest_registry_state.running:
        return HTMLResponse("A fetch for this entity_class is running - wait for it to finish.", status_code=409)
    try:
        harvest_registry.delete_registry_config(entity_class)
    except ValueError as e:
        return HTMLResponse(str(e), status_code=400)
    service.harvest_registry_state.errors.pop(entity_class, None)
    return service.templates.TemplateResponse(request, "_harvest_registry_table.html", {
        "harvest_registries": service._harvest_registry_status(),
    })

@router.get("/harvest/registries/{entity_class}", response_class=HTMLResponse)
async def get_harvest_registry_json(entity_class: str):
    """Raw registry JSON for one entity_class, same guard pattern as
    /scraped/{filename}."""
    path = (harvest_registry.OUTPUT_DIR / f"{entity_class}.json").resolve()
    if path.parent != harvest_registry.OUTPUT_DIR.resolve() or not path.exists():
        return HTMLResponse("Not found", status_code=404)
    return HTMLResponse(path.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")
