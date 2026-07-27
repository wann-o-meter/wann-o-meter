"""Per-event content hash for the staging/review-state dedup (core/staging.py,
core/review_state.py) - "is this candidate the same as one a human already
decided on?" Distinct from review/service.py's _content_hash, which hashes an entire
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
from typing import Any, Dict, Tuple

_IDENTITY_FIELDS = ("type", "year", "from", "to", "name", "value", "unit", "rrule")


def window_key(window: Dict[str, Any]) -> Tuple[Any, ...]:
    """What makes two windows the SAME real-world window - the one identity
    function core/store.py merges by and core/review_state.py's
    already-approved lookup reads.

    They must not diverge. A merge key COARSER than the approved-lookup key
    is non-terminating: one run reports two windows sharing the coarse key,
    each write drops the other, both come back as candidates, forever. That
    is the shape of the incident core/approval.py:47-56 documents (151
    approvals producing a one-window data.yaml), and it was still live under
    its source config's ("type", "year") override - data/schulferien/bw/data.yaml
    holds 10 windows but only 8 distinct (type, year), so the next adapter
    run would silently have dropped two.

    No subject_slug: the data.yaml file path already scopes the subject, so
    keeping it out of the key is what lets a page be re-slugged by moving a
    folder instead of re-hashing a whole review history.

    `name` is case/whitespace-normalized for the same reason normalize_event
    did it - "Osterferien" and " osterferien " are one window."""
    return tuple(
        window.get(field).strip().lower()
        if field == "name" and isinstance(window.get(field), str)
        else window.get(field)
        for field in _IDENTITY_FIELDS
    )


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
