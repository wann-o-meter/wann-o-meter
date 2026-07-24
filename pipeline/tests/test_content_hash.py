import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core.content_hash import content_hash, normalize_event  # noqa: E402

BASE_WINDOW = {
    "type": "market",
    "year": 2026,
    "from": "2026-08-15",
    "to": "2026-08-15",
    "name": "Stadtfest Hechingen",
    "precision": "exact",
    "ics": False,
}


def _hash(window, subject_slug="hechingen"):
    return content_hash(normalize_event(window, subject_slug))


def test_identical_events_hash_the_same():
    assert _hash(dict(BASE_WINDOW)) == _hash(dict(BASE_WINDOW))


def test_stable_against_name_whitespace_and_case_differences():
    a = _hash({**BASE_WINDOW, "name": "Stadtfest Hechingen"})
    b = _hash({**BASE_WINDOW, "name": "  stadtfest hechingen  "})
    assert a == b


def test_field_order_in_the_source_dict_does_not_matter():
    reordered = {k: BASE_WINDOW[k] for k in reversed(list(BASE_WINDOW))}
    assert _hash(dict(BASE_WINDOW)) == _hash(reordered)


def test_sensitive_to_a_changed_date():
    assert _hash(dict(BASE_WINDOW)) != _hash({**BASE_WINDOW, "from": "2026-08-16", "to": "2026-08-16"})


def test_sensitive_to_a_changed_type():
    assert _hash(dict(BASE_WINDOW)) != _hash({**BASE_WINDOW, "type": "festival"})


def test_sensitive_to_a_changed_subject_slug():
    # Two different subjects under the same source could coincidentally
    # produce byte-identical windows (e.g. two towns both having a market on
    # the same date) - they must not collide.
    assert _hash(dict(BASE_WINDOW), subject_slug="hechingen") != _hash(dict(BASE_WINDOW), subject_slug="balingen")


def test_sensitive_to_a_changed_rrule():
    a = _hash({**BASE_WINDOW, "rrule": "FREQ=YEARLY"})
    b = _hash({**BASE_WINDOW, "rrule": "FREQ=MONTHLY"})
    assert a != b


def test_ignores_last_verified():
    a = _hash(dict(BASE_WINDOW))
    b = _hash({**BASE_WINDOW, "last_verified": "2026-07-24"})
    assert a == b


def test_ignores_source_urls():
    a = _hash(dict(BASE_WINDOW))
    b = _hash({**BASE_WINDOW, "source_urls": ["https://example.org/events"]})
    assert a == b


def test_ignores_ics_and_precision():
    a = _hash(dict(BASE_WINDOW))
    b = _hash({**BASE_WINDOW, "ics": True, "precision": "approximate"})
    assert a == b
