"""Writes one approved/modified/re-verified event into data/ - the ONLY
place store.merge_zeitfenster + validate.pruefe_subjekt_datei are invoked
from, now that core/runner.py and the scoped crawler no longer write
directly (see core/review_state.py's diff() and main.py's /review routes,
the two callers of write_event below).

Direct filesystem write, no git operations (Decision B, superseding
core/publish.py's per-run PR mechanism) - a human commits/pushes/opens a PR
for whatever accumulates here themselves, the same as any other local
change to this repo."""

from pathlib import Path
from typing import Any, Dict, Tuple

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
    event: Dict[str, Any],
    quelle: Dict[str, Any],
    replace_key: Tuple[str, ...] = ("type",),
) -> Path:
    """Merges `event` (one RawWindow-shaped dict) into
    data/{category}/{subject_slug}/data.yaml (reusing store.merge_zeitfenster's
    existing replace_key+date-range dedup/merge logic unchanged) and writes
    page.yaml the first time only. Raises ApprovalError, writing nothing,
    if the result fails Zod validation."""
    datei_pfad = DATA_ROOT / category / subject_slug / "data.yaml"
    datei = store.lade_oder_erstelle(datei_pfad, subject_slug, category)
    store.merge_zeitfenster(datei, [event], replace_key)
    store.append_quelle(datei, quelle)

    try:
        validate.pruefe_subjekt_datei(datei)
    except validate.ValidationError as e:
        raise ApprovalError(str(e)) from e

    store.speichere(datei_pfad, datei)
    store.schreibe_page_yaml_falls_neu(datei_pfad.parent / "page.yaml", subject_name)
    return datei_pfad
