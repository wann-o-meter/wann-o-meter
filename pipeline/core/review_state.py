"""What a human said NO to (review-state/<source_id>.yaml), and the split of
a run's candidates into "already in the file" vs "needs a human".

data/{category}/{subject_slug}/data.yaml IS the record of what is approved -
this module only stores the negative set, because a rejection is the one
judgement that leaves no trace in the data. That asymmetry is the whole
design: with no second copy of the approved set there is nothing to drift
out of sync with, so editing data.yaml by hand is a supported way to correct
the data. Delete a window and the next run offers it again; add one and the
next run leaves it alone.

It used to keep a full copy of every approved event here too, keyed by a
hash that included the subject_slug. That copy silently diverged from
data/astronomie/sonnenfinsternis/data.yaml (452 windows renamed in the file,
456 decisions still holding the old name) with nothing to detect it, and
moving a page between slugs re-opened every decision it had.

Deliberately tracked in git (NOT gitignored, unlike pipeline/staging/): a
rejection is a human judgement and re-deriving it is not possible."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from core.content_hash import window_key

REVIEW_STATE_ROOT = Path(__file__).resolve().parent.parent / "review-state"
DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"


def _path_for(source_id: str) -> Path:
    return REVIEW_STATE_ROOT / f"{source_id}.yaml"


def load(source_id: str) -> Dict[str, Any]:
    path = _path_for(source_id)
    if not path.exists():
        return {"rejected": []}
    with path.open(encoding="utf-8") as f:
        state = yaml.safe_load(f) or {}
    state.setdefault("rejected", [])
    return state


def save(source_id: str, state: Dict[str, Any]) -> None:
    path = _path_for(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(state, f, allow_unicode=True, sort_keys=False)


def _entry_key(entry: Dict[str, Any]) -> Tuple[Any, ...]:
    return (entry.get("subject_slug"),) + window_key(entry)


def reject(state: Dict[str, Any], subject_slug: str, window: Dict[str, Any]) -> None:
    """Records "a human saw this window and said no", scoped to the page it
    would have landed on.

    Stored as plain fields, not a hash: the file stays readable and
    hand-editable (deleting a line un-rejects a window), and re-pointing a
    source at another page is then a field rewrite rather than a re-hash
    that can fail - see repoint().

    subject_slug is part of the entry even though window_key deliberately
    excludes it. One source can write many pages: schulferien_kmk's 156
    windows across 16 Bundeslaender collapse to only 90 distinct window_keys,
    because different states genuinely share identical date ranges. A
    slug-less rejection for BB would silently reject BE's real window too."""
    entry = {"subject_slug": subject_slug, **_identity_fields(window)}
    entry["decided_at"] = datetime.now(timezone.utc).isoformat()
    if not any(_entry_key(e) == _entry_key(entry) for e in state["rejected"]):
        state["rejected"].append(entry)


def _identity_fields(window: Dict[str, Any]) -> Dict[str, Any]:
    """The window projected down to what window_key reads, so a stored entry
    round-trips through window_key identically to the live window."""
    from core.content_hash import _IDENTITY_FIELDS

    projected = {}
    for field in _IDENTITY_FIELDS:
        value = window.get(field)
        if field == "name" and isinstance(value, str):
            value = value.strip().lower()
        projected[field] = value
    return projected


def is_rejected(state: Dict[str, Any], subject_slug: str, window: Dict[str, Any]) -> bool:
    key = (subject_slug,) + window_key(window)
    return any(_entry_key(e) == key for e in state["rejected"])


def repoint(state: Dict[str, Any], new_subject_slug: str) -> Dict[str, Any]:
    """Re-points every rejection at a different page. This is the whole cost
    of moving a source's output now: subject_slug is a plain field, so there
    is nothing to re-hash and nothing that can fail to round-trip."""
    return {"rejected": [{**e, "subject_slug": new_subject_slug} for e in state["rejected"]]}


def already_approved(category: str, subject_slug: str, window: Dict[str, Any]) -> bool:
    """Is this window already in the data.yaml it would be written to?

    THE approved-set lookup. It reads the real file, so a hand-edit is
    immediately authoritative - which is the point of keeping no second
    copy. Uses window_key, the same function core/store.merge_zeitfenster
    merges by; if these two ever disagreed the result would be an
    approve -> replace -> re-queue loop that never terminates."""
    return window_key(window) in _approved_keys(category, subject_slug)


def _approved_keys(category: str, subject_slug: str) -> set:
    path = DATA_ROOT / category / subject_slug / "data.yaml"
    if not path.exists():
        return set()
    datei = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {window_key(w) for w in (datei.get("windows") or [])}


def diff(
    candidates: List[Dict[str, Any]],
    state: Dict[str, Any],
    category: str,
    subject_slug: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Splits this run's candidates (see core/staging.py's build_candidate)
    into (auto_waved_through, needs_review).

    Precedence is: in the file -> wave through; else rejected -> skip; else
    queue. The file wins, so hand-adding a previously-rejected window keeps
    it - that is the ask, not a bug.

    Review is per PAGE, not per source: a second source reporting a window
    already approved on that page is waved through and just adds its
    citation. Aggregating overlapping sources onto one page is the point of
    subject_slug, and reviewing the same real-world date once per source is
    a tax with no payoff - the two eclipse catalogs independently rejected
    the identical two dates, four decisions for two judgements."""
    approved = _approved_keys(category, subject_slug)

    auto_waved_through: List[Dict[str, Any]] = []
    needs_review: List[Dict[str, Any]] = []
    seen: set = set()
    for candidate in candidates:
        key = window_key(candidate["event"])
        if key in approved:
            auto_waved_through.append(candidate)
        elif is_rejected(state, subject_slug, candidate["event"]):
            continue
        elif key not in seen:
            # Two sources reporting the same not-yet-reviewed window are one
            # queue row, not two - approving it clears both.
            seen.add(key)
            needs_review.append(candidate)

    return auto_waved_through, needs_review
