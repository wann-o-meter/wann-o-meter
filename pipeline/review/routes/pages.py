"""Dashboard, and maintenance of already-created pages."""

import shutil

import yaml
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core.extraction import ExtractionError
from review import service

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """The published pages - the end of the Sources -> Review -> Pages
    pipeline, and the thing an operator actually comes back to look at. The
    harvest registry used to share this page, which made the landing screen
    a mix of two unrelated concerns; it has /harvest to itself now."""
    return service.templates.TemplateResponse(request, "dashboard.html", {
        "active_nav": "pages",
        "state": service.state.to_dict(),
        "pages": service._list_created_pages(),
        "license_options": service.LICENSE_OPTIONS,
        "category_suggestions": service._category_suggestions(),
        "tag_suggestions": service._all_tags(),
        "review_queue_count": len(service._review_queue()),
    })

@router.get("/page-data/{full_path:path}", response_class=HTMLResponse)
async def get_page_data_yaml(full_path: str):
    """Raw data.yaml for a created page, same guard pattern as /scraped/{filename}."""
    return service._serve_page_file(full_path, "data.yaml")

@router.get("/page-meta/{full_path:path}", response_class=HTMLResponse)
async def get_page_meta_yaml(full_path: str):
    """Raw page.yaml for a created page, same guard pattern as /scraped/{filename}."""
    return service._serve_page_file(full_path, "page.yaml")

@router.post("/pages/{full_path:path}/delete")
async def delete_page(full_path: str, return_to: str = Form("/crawl-sources")):
    """Deletes a created page's whole folder (data.yaml + page.yaml) from
    data/ - the Admin UI's Delete button (and bulk "Delete Selected") on the
    created-pages table. return_to is allowlisted (not just blocklisted)
    against the only two pages that render this button - a blocklist like
    "must start with '/' and not '//'" still lets through backslash tricks
    browsers treat as protocol-relative ("/\\evil.com")."""
    folder = service._resolve_page_folder(full_path)
    if folder is None:
        return HTMLResponse("Not found", status_code=404)
    shutil.rmtree(folder)
    if not service._SAFE_RETURN_TO.match(return_to):
        return_to = "/crawl-sources"
    return RedirectResponse(return_to, status_code=302)

@router.post("/pages/{full_path:path}/edit")
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
    folder = service._resolve_page_folder(full_path)
    if folder is None:
        return HTMLResponse("Not found", status_code=404)
    if license not in service.LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    new_segments = service._slugify_category_path(category)
    validation_error = service._validate_category_segments(new_segments)
    if validation_error:
        return HTMLResponse(validation_error, status_code=400)
    new_category_path = "/".join(new_segments)

    parts = full_path.strip("/").split("/")
    slug = parts[-1]
    current_category_path = "/".join(parts[:-1])

    if new_category_path != current_category_path:
        target = service.DATA_ROOT / new_category_path / slug
        if target.exists():
            return HTMLResponse(f"A page already exists at /{new_category_path}/{slug}/.", status_code=409)
        target.parent.mkdir(parents=True, exist_ok=True)
        folder = folder.rename(target)
        service._write_category_meta_if_new(category)

    data = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
    # The license applies to EVERY citation, and the list is kept. Collapsing
    # it to source[0] destroyed the others - and an aggregated page is the
    # normal case (several sources, one page, see CrawlSource.subject_slug),
    # so changing the license on data/astronomie/sonnenfinsternis/ dropped a
    # citation that its own windows still referenced, which pageDataSchema's
    # superRefine then failed the whole site build on.
    data["source"] = [{**q, "license": license} for q in service._as_quelle_list(data)]
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

    if not service._SAFE_RETURN_TO.match(return_to):
        return_to = "/crawl-sources"
    return RedirectResponse(return_to, status_code=302)

@router.get("/pages/{full_path:path}/suggest-tags")
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
    folder = service._resolve_page_folder(full_path)
    if folder is None:
        return JSONResponse({"error": "Not found"}, status_code=404)

    page = yaml.safe_load((folder / "page.yaml").read_text(encoding="utf-8")) or {}
    datei = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8")) or {}
    # The windows ARE the page's text - there is no prose to summarise, so
    # the tag prompt gets what the page actually says.
    text = "\n".join(str(w.get("name") or "") for w in (datei.get("windows") or [])[:50])
    try:
        tags = service.suggest_tags(text or page.get("title", ""), page.get("title", ""), service._all_tags())
    except ExtractionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return JSONResponse({"tags": tags})

@router.post("/pages/{full_path:path}/add-tag")
async def add_tag_to_page(full_path: str, tag: str = Form(...)):
    """Adds one tag to an already-created page's page.yaml, deduped - backs
    the created-pages table's bulk "Add Tag" action (JSON, not a redirect,
    since the bulk action fires one fetch() per selected page and reloads
    once every request settles)."""
    folder = service._resolve_page_folder(full_path)
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
