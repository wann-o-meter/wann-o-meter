"""Per-event content hash for the staging/review-state dedup (core/staging.py,
core/review_state.py) - "is this candidate the same as one a human already
decided on?" Distinct from main.py's _content_hash, which hashes an entire
scrape result; this hashes one event/window's own identity.

Only fields that describe WHAT the event is go into the hash. Excluded on
purpose:
  - last_verified: a freshness stamp, not identity - including it would make
    the hash change every time a window is re-verified, defeating the whole
    point of recognizing "this is the same event as before".
  - source_urls: which source(s) reported the event, not what the event is -
    two sources citing the identical window shouldn't be treated as two
    different candidates.
  - ics/precision: bookkeeping/display choices, not event identity.
  - rrule IS included: a changed recurrence rule is a real content change
    and should re-trigger review.
"""

import hashlib
import json
from typing import Any, Dict

_IDENTITY_FIELDS = ("type", "year", "from", "to", "name", "value", "unit", "rrule")


def normalize_event(window: Dict[str, Any], subject_slug: str) -> Dict[str, Any]:
    """Projects a window/candidate dict down to just its identity fields,
    with the name field case/whitespace-normalized (two extractions of the
    same real-world event shouldn't hash differently over "Osterferien" vs
    " osterferien ")."""
    normalized: Dict[str, Any] = {"subject_slug": subject_slug}
    for field in _IDENTITY_FIELDS:
        value = window.get(field)
        if field == "name" and isinstance(value, str):
            value = value.strip().lower()
        normalized[field] = value
    return normalized


def content_hash(normalized: Dict[str, Any]) -> str:
    encoded = json.dumps(normalized, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
