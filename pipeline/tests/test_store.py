"""Unit tests for core/store.py's merge (per-window source citation
feature). merge_zeitfenster() keys on core/content_hash.window_key:

  - two runs reporting the SAME window (identical window_key)
    -> MERGE: keep one window, union source_urls so both citations survive.
  - two runs reporting DIFFERENT windows -> both are kept. A changed date
    range is a different window, not a replacement (see window_key for why
    the merge key and the already-approved key have to be the same one).

These tests construct synthetic "runs" the way two different source adapters
would produce them, rather than going through a real adapter, since the
distinction lives entirely in core/store.py and is independent of any one
source."""

import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import store  # noqa: E402
from core.content_hash import window_key  # noqa: E402


def make_window(**overrides):
    window = {
        "type": "school_holidays-summer",
        "year": 2028,
        "from": "2028-07-27",
        "to": "2028-09-09",
        "precision": "exact",
        "ics": False,
        "name": "Sommerferien",
        "source_urls": ["https://source-a.example/ferien"],
    }
    window.update(overrides)
    return window


def make_file(windows=None, sources=None):
    return {
        "subject": {"slug": "bw", "name": "Baden-Württemberg", "category": "vacation-windows", "region": "DE-BW"},
        "windows": windows or [],
        "source": sources or [],
    }


def test_second_source_reporting_the_same_window_merges_citations():
    """Two different sources independently reporting the exact same date
    range for the same (type, year) must end up on ONE window with BOTH
    source_urls attached - not one silently overwriting the other."""
    file = make_file([make_window(source_urls=["https://source-a.example/ferien"])])

    incoming = [make_window(source_urls=["https://source-b.example/ferien"])]
    store.merge_zeitfenster(file, incoming)

    assert len(file["windows"]) == 1
    assert file["windows"][0]["source_urls"] == [
        "https://source-a.example/ferien",
        "https://source-b.example/ferien",
    ]


def test_merging_the_same_source_again_does_not_duplicate_its_citation():
    """Re-running the same source for an unchanged window must not grow
    source_urls with a repeated entry."""
    file = make_file([make_window(source_urls=["https://source-a.example/ferien"])])

    incoming = [make_window(source_urls=["https://source-a.example/ferien"])]
    store.merge_zeitfenster(file, incoming)

    assert len(file["windows"]) == 1
    assert file["windows"][0]["source_urls"] == ["https://source-a.example/ferien"]


def test_a_different_date_range_is_its_own_window_not_a_replacement():
    """A different date range is a different window_key, so both are kept -
    the merge no longer guesses that one supersedes the other. Dropping the
    stale one is a hand-edit of data.yaml, which is a supported path now
    (core/review_state.already_approved won't re-queue what isn't there)."""
    file = make_file([make_window(source_urls=["https://source-a.example/ferien"])])

    incoming = [
        make_window(
            **{"from": "2028-07-20", "to": "2028-09-02"},
            source_urls=["https://source-b.example/ferien"],
        )
    ]
    store.merge_zeitfenster(file, incoming)

    assert sorted(w["from"] for w in file["windows"]) == ["2028-07-20", "2028-07-27"]


def test_non_overlapping_windows_are_simply_added():
    """A new window whose window_key matches nothing existing (e.g. a
    different year) is just appended."""
    file = make_file([make_window(year=2027, source_urls=["https://source-a.example/ferien"])])

    incoming = [make_window(year=2028, source_urls=["https://source-b.example/ferien"])]
    store.merge_zeitfenster(file, incoming)

    assert len(file["windows"]) == 2
    years = {w["year"] for w in file["windows"]}
    assert years == {2027, 2028}


def test_merge_preserves_windows_untouched_by_this_run():
    """A run that only reports one (type, year) must not disturb existing
    windows under other keys."""
    file = make_file(
        [
            make_window(type="school_holidays-summer", year=2028, source_urls=["https://source-a.example/ferien"]),
            make_window(
                type="school_holidays-autumn",
                year=2028,
                **{"from": "2028-10-30", "to": "2028-11-03"},
                source_urls=["https://source-a.example/ferien"],
            ),
        ]
    )

    incoming = [make_window(type="school_holidays-summer", year=2028, source_urls=["https://source-b.example/ferien"])]
    store.merge_zeitfenster(file, incoming)

    autumn = [w for w in file["windows"] if w["type"] == "school_holidays-autumn"]
    assert len(autumn) == 1
    assert autumn[0]["source_urls"] == ["https://source-a.example/ferien"]


def test_merge_works_without_source_urls_on_either_side():
    """Legacy windows (predating source_urls, see RawWindow.source_urls in
    lib/schema.ts) must still merge/replace correctly by date range even
    when neither side carries a source_urls key."""
    legacy_window = make_window()
    del legacy_window["source_urls"]
    file = make_file([legacy_window])

    incoming_window = make_window()
    del incoming_window["source_urls"]
    store.merge_zeitfenster(file, [incoming_window])

    assert len(file["windows"]) == 1
    assert "source_urls" not in file["windows"][0]


def test_append_quelle_dedups_by_url_instead_of_growing_unbounded():
    """Re-running an adapter against an unchanged URL should update the
    existing Source entry (freshest retrieved_at wins), not append a
    near-duplicate."""
    file = make_file(
        sources=[{"url": "https://source-a.example/ferien", "retrieved_at": "2026-01-01", "license": "official_par5", "extraction": "llm"}]
    )

    store.append_quelle(
        file, {"url": "https://source-a.example/ferien", "retrieved_at": "2026-07-01", "license": "official_par5", "extraction": "llm"}
    )

    assert len(file["source"]) == 1
    assert file["source"][0]["retrieved_at"] == "2026-07-01"


def test_append_quelle_keeps_distinct_urls_separate():
    file = make_file(sources=[{"url": "https://source-a.example/ferien", "retrieved_at": "2026-01-01", "license": "official_par5", "extraction": "llm"}])

    store.append_quelle(
        file, {"url": "https://source-b.example/ferien", "retrieved_at": "2026-01-01", "license": "official_par5", "extraction": "llm"}
    )

    assert len(file["source"]) == 2


def test_writing_two_windows_one_at_a_time_keeps_both():
    """The clobber core/approval.write_event used to be able to cause: it
    merges ONE event per call, and the old key-then-drop-siblings pass threw
    away every existing window sharing the incoming coarse key. Under
    its source config's ("type", "year") override that was live - data/schulferien/
    bw/data.yaml holds two Osterferien windows in 2026, and the next adapter
    run would have left one."""
    file = make_file([])

    for from_, to in [("2026-03-25", "2026-04-01"), ("2026-04-07", "2026-04-10")]:
        store.merge_zeitfenster(file, [make_window(year=2026, **{"from": from_, "to": to})])

    assert sorted(w["from"] for w in file["windows"]) == ["2026-03-25", "2026-04-07"]


def test_the_merge_key_is_the_shared_window_key():
    """The invariant the whole model rests on: core/store.py and
    core/review_state.py must decide "same window" with the SAME function. A
    merge key coarser than the already-approved key cannot terminate - see
    content_hash.window_key."""
    a = make_window(**{"from": "2028-07-27", "to": "2028-09-09"})
    b = make_window(**{"from": "2028-07-27", "to": "2028-09-10"})

    file = make_file([a])
    store.merge_zeitfenster(file, [b])

    assert window_key(a) != window_key(b)
    assert len(file["windows"]) == 2
