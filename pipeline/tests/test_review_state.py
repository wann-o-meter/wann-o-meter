"""Unit tests for core/review_state.py, whose whole job is now the negative
set plus the split of a run's candidates.

The invariant every test here defends: data/{category}/{slug}/data.yaml IS
the record of what is approved. There is no second copy, so hand-editing the
file is authoritative - delete a window and it comes back as a candidate, add
one and it is left alone."""

import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import review_state  # noqa: E402
from core.content_hash import window_key  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    monkeypatch.setattr(review_state, "DATA_ROOT", tmp_path / "data")
    return tmp_path


def _event(date="2026-08-15", name="Stadtfest", **overrides):
    return {
        "type": "market",
        "year": int(date[:4]),
        "from": date,
        "to": date,
        "precision": "exact",
        "ics": True,
        "name": name,
        **overrides,
    }


def _candidate(event, subject_slug="hechingen"):
    return {"candidate_id": f"src:{event['from']}", "source_id": "src", "subject_slug": subject_slug, "event": event}


def _write_page(tmp_path, category, slug, windows):
    folder = tmp_path / "data" / category / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "data.yaml").write_text(
        yaml.dump({"subject": {"slug": slug, "category": category}, "windows": windows, "source": []}),
        encoding="utf-8",
    )


class TestTheFileIsTheRecord:
    def test_a_window_already_in_data_yaml_is_not_requeued(self, _isolate):
        event = _event()
        _write_page(_isolate, "veranstaltungen", "hechingen", [event])

        waved, pending = review_state.diff(
            [_candidate(event)],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )

        assert len(waved) == 1
        assert pending == []

    def test_a_window_deleted_from_data_yaml_by_hand_resurfaces(self, _isolate):
        """The user's actual ask. Under the old model the approved copy in
        review-state kept saying "decided", so a hand-deleted window was gone
        for good and the file could never be corrected by editing it."""
        event = _event()
        _write_page(_isolate, "veranstaltungen", "hechingen", [event])
        _write_page(_isolate, "veranstaltungen", "hechingen", [])  # hand-deleted

        waved, pending = review_state.diff(
            [_candidate(event)],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )

        assert waved == []
        assert [c["event"]["from"] for c in pending] == ["2026-08-15"]

    def test_a_window_added_to_data_yaml_by_hand_is_left_alone(self, _isolate):
        """The other half of hand-editability: a window you wrote yourself is
        approved, and a run that re-reports it must not ask about it."""
        event = _event()
        _write_page(_isolate, "veranstaltungen", "hechingen", [event])

        _, pending = review_state.diff(
            [_candidate(event)],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )

        assert pending == []

    def test_a_page_that_does_not_exist_yet_queues_everything(self, _isolate):
        _, pending = review_state.diff(
            [_candidate(_event())],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )
        assert len(pending) == 1

    def test_an_edited_date_in_data_yaml_requeues_the_source_version(self, _isolate):
        """Correcting a date by hand leaves the source's original unapproved,
        so it comes back - which is right: it IS still a claim nobody has
        ruled on. Rejecting it once retires it for good."""
        _write_page(_isolate, "veranstaltungen", "hechingen", [_event(date="2026-08-16")])

        _, pending = review_state.diff(
            [_candidate(_event(date="2026-08-15"))],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )

        assert [c["event"]["from"] for c in pending] == ["2026-08-15"]


class TestRejections:
    def test_a_rejected_window_is_never_queued_again(self, _isolate):
        event = _event()
        state = review_state.load("src")
        review_state.reject(state, "hechingen", event)

        waved, pending = review_state.diff([_candidate(event)], state, "veranstaltungen", "hechingen")

        assert (waved, pending) == ([], [])

    def test_rejection_is_scoped_to_its_subject_slug(self, _isolate):
        """One source writes many pages - schulferien_kmk's 156 windows across
        16 Bundeslaender collapse to only 90 distinct window_keys, because
        different states genuinely share date ranges. A slug-less rejection
        for one would silently reject the other's real window."""
        event = _event()
        state = review_state.load("src")
        review_state.reject(state, "bb", event)

        assert review_state.is_rejected(state, "bb", event)
        assert not review_state.is_rejected(state, "be", event)

    def test_a_window_in_the_file_wins_over_a_rejection(self, _isolate):
        """Precedence: the file is truth. Hand-adding a window you previously
        rejected keeps it - that is the ask, not a bug."""
        event = _event()
        state = review_state.load("src")
        review_state.reject(state, "hechingen", event)
        _write_page(_isolate, "veranstaltungen", "hechingen", [event])

        waved, pending = review_state.diff([_candidate(event)], state, "veranstaltungen", "hechingen")

        assert len(waved) == 1
        assert pending == []

    def test_rejecting_twice_stores_one_entry(self, _isolate):
        state = review_state.load("src")
        review_state.reject(state, "hechingen", _event())
        review_state.reject(state, "hechingen", _event())

        assert len(state["rejected"]) == 1

    def test_a_rejection_matches_a_differently_cased_name(self, _isolate):
        """window_key normalizes `name`, and a stored entry has to round-trip
        through it identically or the rejection silently stops matching."""
        state = review_state.load("src")
        review_state.reject(state, "hechingen", _event(name="  STADTFEST "))

        assert review_state.is_rejected(state, "hechingen", _event(name="Stadtfest"))

    def test_rejections_survive_a_save_load_round_trip(self, _isolate):
        state = review_state.load("src")
        review_state.reject(state, "hechingen", _event())
        review_state.save("src", state)

        assert review_state.is_rejected(review_state.load("src"), "hechingen", _event())

    def test_repoint_rewrites_the_subject_slug_of_every_rejection(self, _isolate):
        """The entire cost of moving a source's output now - no hashing, so
        nothing can fail to round-trip and there is no refusal path."""
        state = review_state.load("src")
        review_state.reject(state, "old-slug", _event())
        review_state.reject(state, "old-slug", _event(date="2027-08-02"))

        moved = review_state.repoint(state, "sonnenfinsternis")

        assert {e["subject_slug"] for e in moved["rejected"]} == {"sonnenfinsternis"}
        assert review_state.is_rejected(moved, "sonnenfinsternis", _event())


class TestPerPageReview:
    def test_two_sources_reporting_one_unreviewed_window_yield_one_queue_row(self, _isolate):
        """Reviewing the same real-world date once per source is a tax with no
        payoff - the two eclipse catalogs independently rejected the identical
        two dates, four decisions for two judgements."""
        event = _event()
        _, pending = review_state.diff(
            [_candidate(event), {**_candidate(event), "source_id": "other", "candidate_id": "other:x"}],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )

        assert len(pending) == 1

    def test_a_second_source_reporting_an_approved_window_is_waved_through(self, _isolate):
        event = _event()
        _write_page(_isolate, "veranstaltungen", "hechingen", [event])

        waved, pending = review_state.diff(
            [{**_candidate(event), "source_id": "other"}],
            review_state.load("src"),
            "veranstaltungen",
            "hechingen",
        )

        assert len(waved) == 1
        assert pending == []


def test_the_already_approved_lookup_uses_the_merge_key(_isolate):
    """The non-termination guard: core/store.merge_windows and this module
    must decide "same window" with the same function, or an approved window
    can fail its own lookup and re-queue forever."""
    event = _event()
    _write_page(_isolate, "veranstaltungen", "hechingen", [event])

    assert review_state.already_approved("veranstaltungen", "hechingen", event)
    assert review_state.already_approved("veranstaltungen", "hechingen", {**event, "precision": "approximate"})
    assert window_key(event) == window_key({**event, "precision": "approximate"})


def test_a_missing_file_loads_as_an_empty_negative_set(_isolate):
    assert review_state.load("never-seen") == {"rejected": []}
