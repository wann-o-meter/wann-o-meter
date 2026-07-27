"""Pipeline status polling for the dashboard."""


from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from review import service

router = APIRouter()


@router.get("/status")
async def get_status():
    """JSON endpoint for external polling/tooling."""
    return JSONResponse(service.state.to_dict())

@router.get("/status-fragment", response_class=HTMLResponse)
async def get_status_fragment(request: Request):
    """Polled by the shared header (every 3s, see _base.html's
    #status-indicator) - just the global running/idle badge for in-flight
    crawl_sources runs (see PipelineState)."""
    return service.templates.TemplateResponse(request, "_status_fragment.html", {"state": service.state.to_dict()})
