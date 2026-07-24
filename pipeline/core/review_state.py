"""Persistent per-source review decisions (review-state/<source_id>.yaml) and
the diff logic that uses them to auto-wave-through already-reviewed
candidates on a re-crawl, so only genuinely new/changed events reach a human.

Deliberately tracked in git (NOT gitignored, unlike pipeline/staging/) -
rejected and modified candidates are kept permanently as future prompt-
improvement material, and the approved set IS the review history."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

REVIEW_STATE_ROOT = Path(__file__).resolve().parent.parent / "review-state"


def _path_for(source_id: str) -> Path:
    return REVIEW_STATE_ROOT / f"{source_id}.yaml"


def load(source_id: str) -> Dict[str, Any]:
    path = _path_for(source_id)
    if not path.exists():
        return {"decisions": {}, "disappeared": {}}
    with path.open(encoding="utf-8") as f:
        state = yaml.safe_load(f) or {}
    state.setdefault("decisions", {})
    state.setdefault("disappeared", {})
    return state


def save(source_id: str, state: Dict[str, Any]) -> None:
    path = _path_for(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(state, f, allow_unicode=True, sort_keys=False)


def record_decision(
    state: Dict[str, Any],
    content_hash: str,
    status: str,
    target_file: str,
    event: Dict[str, Any],
    corrected_event: Optional[Dict[str, Any]] = None,
) -> None:
    """status: approved | rejected | modified. `event` is the canonical
    current window for this decision (the corrected fassung if modified,
    the extracted one if approved) - kept so a later diff() can scope
    disappearance-detection without needing to re-run extraction (see
    diff()'s docstring for why this matters)."""
    state["decisions"][content_hash] = {
        "status": status,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "target_file": target_file,
        "event": event,
        **({"corrected_event": corrected_event} if corrected_event is not None else {}),
    }
    state["disappeared"].pop(content_hash, None)


def stamp_last_verified(state: Dict[str, Any], content_hash: str, when: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Stamps last_verified on the stored decision and returns the event
    that should actually be WRITTEN (the corrected fassung if modified, the
    approved one otherwise) - callers must write THIS returned dict, not
    call this after already writing, or the stamp never reaches data/ (it
    would only exist in review-state's own copy)."""
    decision = state["decisions"].get(content_hash)
    if decision is None:
        return None
    # A plain date, not a full timestamp - lib/schema.ts's last_verified is
    # z.iso.date() (YYYY-MM-DD), not a datetime; a full isoformat() string
    # (with time + offset) fails that Zod validation at write time.
    stamp = when or datetime.now(timezone.utc).date().isoformat()
    decision["event"]["last_verified"] = stamp
    if "corrected_event" in decision:
        decision["corrected_event"]["last_verified"] = stamp
        return decision["corrected_event"]
    return decision["event"]


def diff(
    candidates: List[Dict[str, Any]],
    state: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Splits `candidates` (this run's freshly-extracted, per-window
    candidates, see core/staging.py's build_candidate) against `state` into
    (auto_waved_through, needs_review, disappeared).

    auto_waved_through entries carry the DECIDED event (the corrected
    fassung if the original decision was "modified" - the correction stays
    authoritative, not the fresh re-extraction, per spec) - callers should
    write THAT, not candidate["event"].

    Disappearance is scoped to what this run actually covers, not a naive
    "everything previously approved that's missing now": a run like
    `schulferien_kmk --jahr 2028` only ever produces 2028's windows, so a
    naive full diff would flag every OTHER already-approved year as
    "disappeared" on every single re-run. Scope is inferred from this run's
    own candidates' `event.year` - a previously-approved window is only
    considered for disappearance if its own year is either None (a
    year-less recurring window, which every run should still be able to
    see - if it's genuinely missing now, that IS meaningful) or matches one
    of the years this run's candidates actually cover. A stored decision
    whose year isn't covered by this run at all (e.g. a 2026 window when
    this run only ever fetches 2028) is simply out of scope, not flagged.
    """
    candidates_by_hash = {c["content_hash"]: c for c in candidates}
    in_scope_years = {c["event"].get("year") for c in candidates if c["event"].get("year") is not None}

    auto_waved_through: List[Dict[str, Any]] = []
    needs_review: List[Dict[str, Any]] = []

    for hash_, candidate in candidates_by_hash.items():
        decision = state["decisions"].get(hash_)
        if decision is None:
            needs_review.append(candidate)
            continue
        if decision["status"] == "rejected":
            continue  # still ignorieren
        # approved or modified: wave through with the DECIDED event, not the
        # fresh extraction (spec: "die Korrektur bleibt maßgeblich").
        decided_event = decision.get("corrected_event", decision["event"])
        auto_waved_through.append({**candidate, "event": decided_event})

    disappeared: List[Dict[str, Any]] = []
    for hash_, decision in state["decisions"].items():
        if hash_ in candidates_by_hash or decision["status"] == "rejected":
            continue
        stored_year = decision["event"].get("year")
        in_scope = stored_year is None or stored_year in in_scope_years
        if in_scope:
            disappeared.append({"content_hash": hash_, **decision})

    return auto_waved_through, needs_review, disappeared


def mark_disappeared(state: Dict[str, Any], content_hash: str, target_file: str) -> None:
    state["disappeared"].setdefault(
        content_hash, {"detected_at": datetime.now(timezone.utc).isoformat(), "target_file": target_file}
    )
