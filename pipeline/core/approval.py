"""Writes one approved/modified/re-verified event into data/ - the ONLY
place store.merge_windows + validate.pruefe_subject_file are invoked
from, now that core/runner.py and the scoped crawler no longer write
directly (see core/review_state.py's diff() and review/service.py's /review routes,
the two callers of write_event below).

Direct filesystem write, no git operations (Decision B, superseding
core/publish.py's per-run PR mechanism) - a human commits/pushes/opens a PR
for whatever accumulates here themselves, the same as any other local
change to this repo."""

from pathlib import Path
from typing import Any

from core import store, validate

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"


class ApprovalError(Exception):
    """Raised when the approved event fails real Zod validation. Nothing is
    written when this happens - unlike the old runner.py (which validated
    an entire batch before writing anything), validation now happens per
    candidate, at the moment a human clicks Approve/Modify, so a caller
    must leave the candidate's review-state decision unset on failure - it
    stays in the queue, retryable once the underlying issue is fixed."""


def write_event(
    category: str,
    subject_slug: str,
    subject_name: str,
    event: dict[str, Any],
    source: dict[str, Any],
) -> Path:
    """Merges `event` (one RawWindow-shaped dict) into
    data/{category}/{subject_slug}/data.yaml via store.merge_windows and
    writes page.yaml the first time only. Raises ApprovalError, writing
    nothing, if the result fails Zod validation.

    There is no replace_key: window identity is core/content_hash.window_key
    everywhere now, so what counts as "the same window" here and what counts
    as "already approved" in core/review_state can no longer disagree."""
    file_path = DATA_ROOT / category / subject_slug / "data.yaml"
    file = store.load_or_create(file_path, subject_slug, category)
    store.merge_windows(file, [event])
    store.append_source(file, source)

    try:
        validate.pruefe_subject_file(file)
    except validate.ValidationError as e:
        raise ApprovalError(str(e)) from e

    store.speichere(file_path, file)
    store.schreibe_page_yaml_falls_neu(file_path.parent / "page.yaml", subject_name)
    return file_path
