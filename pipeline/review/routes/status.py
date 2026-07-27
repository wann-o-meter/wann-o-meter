"""Pipeline status polling for the dashboard."""

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

import yaml
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from core import approval, crawl_config, crawl_runner, review_state, staging, store, validate
from core.extraction import ExtractionError
from sources import registry as harvest_registry

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
