#!/usr/bin/env python3
"""Wann-Plattform Admin: FastAPI + Jinja2 (SSR) + HTMX.

The local review app, and the project's approval step - an LLM can guess, so a
human sees every candidate before it reaches data/. GitHub is the merge gate
and the audit log, which is a different job. Nothing here writes to data/
except an explicit approval.

Assembly only: each router owns one resource, review/service.py holds the
logic they share.
"""

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from review.routes import crawl_sources, harvest, pages, review, status

app = FastAPI(title="Wann-Plattform Admin")
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")

# Registration order is the order the routes were declared in the single file
# these came from. It matters: /review/bulk-edit has to be matched before
# /review/{source_id}/{candidate_id} can swallow it.
for router in (pages.router, harvest.router, crawl_sources.router, review.router, status.router):
    app.include_router(router)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
