import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import review_state  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_review_state(tmp_path, monkeypatch):
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")


def _candidate(content_hash, year, **event_overrides):
    event = {"type": "market", "year": year, "from": f"{year}-08-15", "to": f"{year}-08-15", "name": "Stadtfest", **event_overrides}
    return {"candidate_id": f"src:{content_hash}", "source_id": "src", "content_hash": content_hash, "event": event}


def test_load_returns_empty_state_when_no_file_exists():
    state = review_state.load("brand-new-source")
    assert state == {"decisions": {}, "disappeared": {}}


def test_save_and_load_round_trip(tmp_path):
    state = review_state.load("src")
    review_state.record_decision(state, "hash1", "approved", "data/x/y/data.yaml", {"year": 2026})
    review_state.save("src", state)

    reloaded = review_state.load("src")
    assert reloaded["decisions"]["hash1"]["status"] == "approved"


def test_unknown_hash_goes_to_needs_review():
    state = review_state.load("src")
    candidates = [_candidate("new-hash", 2026)]

    waved, needs_review, disappeared = review_state.diff(candidates, state)

    assert waved == []
    assert [c["content_hash"] for c in needs_review] == ["new-hash"]
    assert disappeared == []


def test_approved_hash_auto_waves_through():
    state = review_state.load("src")
    review_state.record_decision(state, "known-hash", "approved", "data/x/y/data.yaml", {"year": 2026, "name": "Stadtfest"})
    candidates = [_candidate("known-hash", 2026)]

    waved, needs_review, disappeared = review_state.diff(candidates, state)

    assert [c["content_hash"] for c in waved] == ["known-hash"]
    assert needs_review == []


def test_rejected_hash_is_silently_dropped():
    state = review_state.load("src")
    review_state.record_decision(state, "rejected-hash", "rejected", "", {"year": 2026})
    candidates = [_candidate("rejected-hash", 2026)]

    waved, needs_review, disappeared = review_state.diff(candidates, state)

    assert waved == []
    assert needs_review == []
    assert disappeared == []


def test_modified_hash_waves_through_with_the_correction_not_the_fresh_extraction():
    state = review_state.load("src")
    original = {"year": 2026, "name": "Stadtfest", "from": "2026-08-15", "to": "2026-08-15"}
    corrected = {"year": 2026, "name": "Stadtfest Hechingen", "from": "2026-08-15", "to": "2026-08-16"}
    review_state.record_decision(state, "modified-hash", "modified", "data/x/y/data.yaml", original, corrected_event=corrected)
    candidates = [_candidate("modified-hash", 2026)]  # fresh extraction, differs from the correction

    waved, needs_review, disappeared = review_state.diff(candidates, state)

    assert len(waved) == 1
    assert waved[0]["event"] == corrected


def test_stamp_last_verified_updates_the_decided_event():
    state = review_state.load("src")
    review_state.record_decision(state, "known-hash", "approved", "data/x/y/data.yaml", {"year": 2026})

    review_state.stamp_last_verified(state, "known-hash", when="2026-07-24")

    assert state["decisions"]["known-hash"]["event"]["last_verified"] == "2026-07-24"


def test_stamp_last_verified_updates_corrected_event_too():
    state = review_state.load("src")
    review_state.record_decision(
        state, "modified-hash", "modified", "data/x/y/data.yaml", {"year": 2026}, corrected_event={"year": 2026, "name": "fixed"}
    )

    review_state.stamp_last_verified(state, "modified-hash", when="2026-07-24")

    assert state["decisions"]["modified-hash"]["corrected_event"]["last_verified"] == "2026-07-24"


def test_disappeared_scoped_to_the_current_runs_years_not_flagged_for_other_years():
    # Regression test for the exact false-positive trap a naive full-set
    # diff would fall into: schulferien_kmk --jahr 2028 only ever produces
    # 2028's windows in one run - a previously-approved 2026 window must NOT
    # be flagged as disappeared just because THIS run didn't mention it.
    state = review_state.load("src")
    review_state.record_decision(state, "hash-2026", "approved", "data/x/y/data.yaml", {"year": 2026, "name": "Osterferien"})
    review_state.record_decision(state, "hash-2028-gone", "approved", "data/x/y/data.yaml", {"year": 2028, "name": "Herbstferien"})

    # This run only covers 2028, and hash-2028-gone's real-world event is no
    # longer on the source page, but hash-2026 was never in scope at all.
    candidates = [_candidate("hash-2028-still-here", 2028)]

    waved, needs_review, disappeared = review_state.diff(candidates, state)

    disappeared_hashes = {d["content_hash"] for d in disappeared}
    assert disappeared_hashes == {"hash-2028-gone"}
    assert "hash-2026" not in disappeared_hashes


def test_disappeared_year_less_recurring_window_is_always_checked():
    # A year: null (recurring) window has no "year" to scope by - every run
    # of that source should always be able to see it, so a genuine absence
    # is always meaningful, regardless of what other years are in scope.
    state = review_state.load("src")
    review_state.record_decision(state, "recurring-hash", "approved", "data/x/y/data.yaml", {"year": None, "name": "Hauptsaison"})

    candidates = [_candidate("unrelated-hash", 2028)]

    _, _, disappeared = review_state.diff(candidates, state)

    assert {d["content_hash"] for d in disappeared} == {"recurring-hash"}


def test_disappeared_hash_that_resurfaces_is_no_longer_flagged():
    state = review_state.load("src")
    review_state.record_decision(state, "hash-a", "approved", "data/x/y/data.yaml", {"year": 2028})
    review_state.mark_disappeared(state, "hash-a", "data/x/y/data.yaml")
    assert "hash-a" in state["disappeared"]

    candidates = [_candidate("hash-a", 2028)]
    waved, _, _ = review_state.diff(candidates, state)
    # record_decision (called again on a later approve) clears it; simulate
    # the same auto-clear that a fresh approval would trigger.
    review_state.record_decision(state, "hash-a", "approved", "data/x/y/data.yaml", {"year": 2028})

    assert "hash-a" not in state["disappeared"]
    assert [c["content_hash"] for c in waved] == ["hash-a"]
