"""Unit tests for core/store.py's merge-vs-replace distinction (per-window
source citation feature). merge_zeitfenster() has to tell apart two cases
that a plain replace_key match cannot distinguish on its own:

  - two runs reporting the SAME window (same replace_key AND same from/to)
    -> MERGE: keep one window, union source_urls so both citations survive.
  - two runs reporting a DIFFERENT window under the same replace_key (a
    correction / updated information) -> REPLACE: drop the old entry.

These tests construct synthetic "runs" the way two different source adapters
would produce them, rather than going through a real adapter, since the
distinction lives entirely in core/store.py and is independent of any one
source."""

import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import store  # noqa: E402


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
        "sources": sources or [],
    }


def test_second_source_reporting_the_same_window_merges_citations():
    """Two different sources independently reporting the exact same date
    range for the same (type, year) must end up on ONE window with BOTH
    source_urls attached - not one silently overwriting the other."""
    file = make_file([make_window(source_urls=["https://source-a.example/ferien"])])

    incoming = [make_window(source_urls=["https://source-b.example/ferien"])]
    store.merge_zeitfenster(file, incoming, replace_key=("type", "year"))

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
    store.merge_zeitfenster(file, incoming, replace_key=("type", "year"))

    assert len(file["windows"]) == 1
    assert file["windows"][0]["source_urls"] == ["https://source-a.example/ferien"]


def test_same_replace_key_but_different_date_range_replaces_instead_of_merging():
    """A source reporting a different date range under the same replace_key
    is a correction, not agreement - the old entry (and its citation) must
    be dropped, not merged in alongside the new one."""
    file = make_file([make_window(source_urls=["https://source-a.example/ferien"])])

    incoming = [
        make_window(
            **{"from": "2028-07-20", "to": "2028-09-02"},
            source_urls=["https://source-b.example/ferien"],
        )
    ]
    store.merge_zeitfenster(file, incoming, replace_key=("type", "year"))

    assert len(file["windows"]) == 1
    assert file["windows"][0]["from"] == "2028-07-20"
    assert file["windows"][0]["source_urls"] == ["https://source-b.example/ferien"]


def test_non_overlapping_windows_are_simply_added():
    """A new window with a replace_key that doesn't match anything existing
    (e.g. a different year) is just appended - no merge, no replace."""
    file = make_file([make_window(year=2027, source_urls=["https://source-a.example/ferien"])])

    incoming = [make_window(year=2028, source_urls=["https://source-b.example/ferien"])]
    store.merge_zeitfenster(file, incoming, replace_key=("type", "year"))

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
    store.merge_zeitfenster(file, incoming, replace_key=("type", "year"))

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
    store.merge_zeitfenster(file, [incoming_window], replace_key=("type", "year"))

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

    assert len(file["sources"]) == 1
    assert file["sources"][0]["retrieved_at"] == "2026-07-01"


def test_append_quelle_keeps_distinct_urls_separate():
    file = make_file(sources=[{"url": "https://source-a.example/ferien", "retrieved_at": "2026-01-01", "license": "official_par5", "extraction": "llm"}])

    store.append_quelle(
        file, {"url": "https://source-b.example/ferien", "retrieved_at": "2026-01-01", "license": "official_par5", "extraction": "llm"}
    )

    assert len(file["sources"]) == 2
