"""The review queue: inspect a candidate, then approve/modify/reject it."""


from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from core import approval, review_state, staging
from review import service

router = APIRouter()


@router.get("/review", response_class=HTMLResponse)
async def review_queue_view(request: Request):
    return service.templates.TemplateResponse(request, "review.html", {
        "active_nav": "review",
        "state": service.state.to_dict(),
        "queue": service._review_queue(),
        "license_options": service.LICENSE_OPTIONS,
    })

@router.get("/review/{source_id}/document/{doc_hash}", response_class=HTMLResponse)
async def review_document(request: Request, source_id: str, doc_hash: str):
    """The whole staged document with every pending date highlighted and
    rejectable in place - the counterpart to the one-candidate-at-a-time
    view, for a source that is one big date table. Reviewing 200 rows by
    stepping through 200 separate pages loses the thing that makes a table
    readable: its neighbours."""
    if not service._is_known_source_id(source_id) or not service._DOC_HASH_RE.match(doc_hash):
        return HTMLResponse("Not found", status_code=404)
    run_ts = service._latest_run_ts(source_id)
    if run_ts is None:
        return HTMLResponse("Not found - only text snapshots can be reviewed inline.", status_code=404)
    documents_dir = staging.STAGING_ROOT / source_id / run_ts / "documents"
    doc_path = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None) if documents_dir.exists() else None
    if doc_path is None or doc_path.suffix not in (".md", ".ics"):
        return HTMLResponse("Not found - only text snapshots can be reviewed inline.", status_code=404)

    candidates = [c for c in service._pending_candidates_for(source_id) if c["document"] == doc_hash]
    raw_text = doc_path.read_text(encoding="utf-8")
    plain_text = service._plaintext_from_markdown(raw_text) if doc_path.suffix == ".md" else raw_text

    return service.templates.TemplateResponse(request, "review_document.html", {
        "active_nav": "review",
        "state": service.state.to_dict(),
        "source_id": source_id,
        "doc_hash": doc_hash,
        "document_meta": staging.read_document_meta(source_id, run_ts, doc_hash),
        "document_html": service._highlight_candidates(plain_text, candidates, source_id),
        "pending_count": len(candidates),
        "license_options": service.LICENSE_OPTIONS,
        # Shown so it's obvious which page a click here publishes to - the
        # whole selection lands in one data.yaml.
        "category": service._target_category_for(candidates[0]) if candidates else "",
        "subject_slug": candidates[0]["subject_slug"] if candidates else "",
    })

@router.get("/review/{source_id}/{candidate_id}", response_class=HTMLResponse)
async def review_candidate_detail(request: Request, source_id: str, candidate_id: str):
    if not service._is_known_source_id(source_id):
        return HTMLResponse("Not found", status_code=404)
    run_ts = service._latest_run_ts(source_id)
    if run_ts is None:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    candidate = service._load_candidate(source_id, run_ts, candidate_id)
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
        plain_text = service._plaintext_from_markdown(raw_text) if doc_path.suffix == ".md" else raw_text
        document_html = service._highlight_dates(plain_text, [event.get("from"), event.get("to")])

    return service.templates.TemplateResponse(request, "_candidate_review.html", {
        "state": service.state.to_dict(),
        "source_id": source_id,
        "candidate": candidate,
        "document_meta": doc_meta,
        "document_html": document_html,
        "document_url": f"/staging-document/{source_id}/{run_ts}/{doc_hash}" if doc_path and not is_text else None,
        "license_options": service.LICENSE_OPTIONS,
        "category_suggestions": service._category_suggestions(),
        "next_candidate": service._next_review_candidate(exclude=(source_id, candidate_id)),
    })

@router.get("/staging-document/{source_id}/{run_ts}/{doc_hash}")
async def get_staging_document(source_id: str, run_ts: str, doc_hash: str):
    """Serves one staged document snapshot for the review UI. All three
    path segments come straight from the URL: source_id is checked against
    the same allowlist as /review/{source_id}/... (_is_known_source_id),
    doc_hash is checked against the hex-only shape staging.write_document
    actually generates it in (rejects a glob/traversal payload before it
    ever reaches documents_dir.glob()), and the resolve()+parent-check
    catches anything else (e.g. a "../"-laden run_ts)."""
    if not service._is_known_source_id(source_id) or not service._DOC_HASH_RE.match(doc_hash):
        return HTMLResponse("Not found", status_code=404)
    documents_dir = (staging.STAGING_ROOT / source_id / run_ts / "documents").resolve()
    if staging.STAGING_ROOT.resolve() not in documents_dir.parents:
        return HTMLResponse("Not found", status_code=404)
    match = next((p for p in documents_dir.glob(f"{doc_hash}.*") if p.suffix != ".yaml"), None) if documents_dir.exists() else None
    if match is None:
        return HTMLResponse("Not found", status_code=404)
    media_type = service._STAGING_DOCUMENT_MEDIA_TYPES.get(match.suffix, "application/octet-stream")
    return Response(content=match.read_bytes(), media_type=media_type)

@router.post("/review/{source_id}/{candidate_id}/approve")
async def approve_candidate(
    source_id: str,
    candidate_id: str,
    category: str = Form(...),
    license: str = Form(...),
):
    error = service._approve_one(source_id, candidate_id, category, license)
    if error == "unknown source":
        return HTMLResponse("Not found", status_code=404)
    if error and error.startswith("not found"):
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    if error:
        return HTMLResponse(error, status_code=400)
    return service._redirect_to_next_review(source_id, candidate_id)

@router.post("/review/bulk-edit")
async def bulk_approve_candidates(
    request: Request,
    selected: list[str] = Form(default=[]),
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
    if action == "approve" and license not in service.LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    editted, failures = 0, []
    for value in selected:
        source_id, _, candidate_id = value.rpartition("/")
        if not source_id or not candidate_id:
            failures.append(f"{value}: malformed selection")
            continue
        if action == "reject":
            error = service._reject_one(source_id, candidate_id)
        else:
            # A source can be "known" on its config alone, before it has ever
            # run - _latest_run_ts is then None, and _load_candidate would do
            # STAGING_ROOT / source_id / None and raise. Guard it here rather
            # than let one unrunnable row 500 the whole batch.
            run_ts = service._latest_run_ts(source_id) if service._is_known_source_id(source_id) else None
            candidate = service._load_candidate(source_id, run_ts, candidate_id) if run_ts else None
            # Category default matches _candidate_review.html's prefilled field.
            category = service._target_category_for(candidate) if candidate else ""
            error = service._approve_one(source_id, candidate_id, category, license)
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
        run_ts = service._latest_run_ts(source_id) if service._is_known_source_id(source_id) else None
        candidate = service._load_candidate(source_id, run_ts, candidate_id) if run_ts else None
        if candidate:
            return RedirectResponse(f"/review/{source_id}/document/{candidate['document']}", status_code=302)

    # Renders the queue directly instead of redirecting to it, so the
    # per-row reasons survive - a redirect could only carry the counts, and
    # "12 approved, 3 failed" without the three reasons is exactly the kind
    # of silent partial success this route has to avoid. Re-POSTing on a
    # refresh is harmless: those rows are no longer pending, so every one
    # comes back "may already have been reviewed" and nothing is written twice.
    return service.templates.TemplateResponse(request, "review.html", {
        "active_nav": "review",
        "state": service.state.to_dict(),
        "queue": service._review_queue(),
        "license_options": service.LICENSE_OPTIONS,
        "bulk_action": "approved" if action == "approve" else "rejected",
        "bulk_done": editted,
        "bulk_failures": failures,
    })

@router.post("/review/{source_id}/{candidate_id}/modify")
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
    if not service._is_known_source_id(source_id):
        return HTMLResponse("Not found", status_code=404)
    run_ts = service._latest_run_ts(source_id)
    candidate = service._load_candidate(source_id, run_ts, candidate_id) if run_ts else None
    if candidate is None:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    if license not in service.LICENSE_VALUES:
        return HTMLResponse(f"Invalid license: {license}", status_code=400)

    category_path = "/".join(service._slugify_category_path(category))
    validation_error = service._validate_category_segments(category_path.split("/") if category_path else [])
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

    quelle = service._quelle_for_candidate(source_id, candidate, license)
    try:
        approval.write_event(category_path, candidate["subject_slug"], service._page_title_for(candidate), corrected_event, quelle)
    except approval.ApprovalError as e:
        return HTMLResponse(f"Validation failed, nothing written:\n{e}", status_code=400)
    service._write_category_meta_if_new(category)

    # The correction is already in data.yaml, so it needs no second record.
    # The ORIGINAL identity does: the source keeps re-extracting it, and
    # without retiring it the same wrong window would re-queue every run.
    st = review_state.load(source_id)
    review_state.reject(st, candidate["subject_slug"], candidate["event"])
    review_state.save(source_id, st)
    return service._redirect_to_next_review(source_id, candidate_id)

@router.post("/review/{source_id}/{candidate_id}/reject")
async def reject_candidate(source_id: str, candidate_id: str, return_to: str = Form("")):
    """return_to="document" comes from the in-document Reject buttons and
    sends you back to the document you were reading instead of jumping to
    the next queue item - the whole point of that view is staying in one
    place. Not a URL, just a flag: the destination is rebuilt from the
    candidate's own document, so nothing user-supplied reaches the redirect."""
    candidate = None
    if return_to == "document":
        run_ts = service._latest_run_ts(source_id)
        candidate = service._load_candidate(source_id, run_ts, candidate_id) if run_ts else None

    error = service._reject_one(source_id, candidate_id)
    if error:
        return HTMLResponse("Not found - this candidate may already have been reviewed.", status_code=404)
    if candidate:
        return RedirectResponse(f"/review/{source_id}/document/{candidate['document']}", status_code=302)
    return service._redirect_to_next_review(source_id, candidate_id)
