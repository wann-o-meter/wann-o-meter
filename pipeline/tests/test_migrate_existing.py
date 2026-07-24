import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import content_hash, review_state  # noqa: E402
from tools import migrate_existing  # noqa: E402

SCHULFERIEN_WINDOW = {
    "type": "school_holidays-easter", "year": 2026, "from": "2026-03-25", "to": "2026-03-25",
    "precision": "exact", "ics": False, "name": "Osterferien",
}

SAISONKALENDER_WINDOW = {
    "type": "main_season", "name": "Hauptsaison", "year": None, "from": "--08", "to": "--11",
    "precision": "approximate", "ics": False,
}


def _write_data_yaml(path: Path, windows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump({"windows": windows, "source": [{"url": "https://example.invalid"}]}), encoding="utf-8")


@pytest.fixture(autouse=True)
def _isolate_review_state(tmp_path, monkeypatch):
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    monkeypatch.setattr(migrate_existing, "MIGRATION_SOURCE_MAP_PATH", tmp_path / "migration_source_map.yaml")
    (tmp_path / "migration_source_map.yaml").write_text(yaml.dump({"schulferien": "schulferien_kmk"}), encoding="utf-8")
    return tmp_path


@pytest.fixture
def data_root(tmp_path):
    root = tmp_path / "data"
    _write_data_yaml(root / "schulferien" / "bw" / "data.yaml", [SCHULFERIEN_WINDOW])
    _write_data_yaml(root / "saisonkalender" / "apfel" / "data.yaml", [SAISONKALENDER_WINDOW])
    return root


def test_migrates_a_mapped_category_into_its_real_source_id(data_root):
    counts = migrate_existing.migrate(data_root)

    assert counts == {"schulferien_kmk": 1, "legacy:saisonkalender/apfel": 1}

    state = review_state.load("schulferien_kmk")
    hash_ = content_hash.content_hash(content_hash.normalize_event(SCHULFERIEN_WINDOW, "bw"))
    assert state["decisions"][hash_]["status"] == "approved"


def test_unmapped_category_gets_a_synthetic_legacy_source_id(data_root):
    migrate_existing.migrate(data_root)

    state = review_state.load("legacy:saisonkalender/apfel")
    hash_ = content_hash.content_hash(content_hash.normalize_event(SAISONKALENDER_WINDOW, "apfel"))
    assert state["decisions"][hash_]["status"] == "approved"


def test_dry_run_reports_counts_without_writing_anything(data_root):
    counts = migrate_existing.migrate(data_root, dry_run=True)

    assert counts == {"schulferien_kmk": 1, "legacy:saisonkalender/apfel": 1}
    assert review_state.load("schulferien_kmk")["decisions"] == {}


def test_running_twice_does_not_duplicate_or_re_report(data_root):
    first = migrate_existing.migrate(data_root)
    second = migrate_existing.migrate(data_root)

    assert first == {"schulferien_kmk": 1, "legacy:saisonkalender/apfel": 1}
    assert second == {}  # nothing NEW to migrate the second time

    state = review_state.load("schulferien_kmk")
    assert len(state["decisions"]) == 1


def test_migrated_window_produces_zero_review_queue_entries_on_a_simulated_first_run(data_root):
    """The actual point of the migration: a future real run's freshly
    extracted candidate for the SAME window must be recognized as already
    approved (diff() waves it through), not queued."""
    migrate_existing.migrate(data_root)

    state = review_state.load("schulferien_kmk")
    fresh_candidate = {
        "candidate_id": "schulferien_kmk:whatever",
        "content_hash": content_hash.content_hash(content_hash.normalize_event(SCHULFERIEN_WINDOW, "bw")),
        "event": dict(SCHULFERIEN_WINDOW),
    }

    auto_waved_through, needs_review, disappeared = review_state.diff([fresh_candidate], state)

    assert len(auto_waved_through) == 1
    assert needs_review == []


def test_categories_with_no_data_yaml_are_silently_skipped(tmp_path):
    root = tmp_path / "data"
    (root / "feiertage").mkdir(parents=True)  # generator.ts-only, no data.yaml
    (root / "presets").mkdir(parents=True)

    counts = migrate_existing.migrate(root)

    assert counts == {}


def test_a_window_with_no_windows_key_or_empty_list_is_skipped(tmp_path):
    root = tmp_path / "data"
    _write_data_yaml(root / "schulferien" / "empty" / "data.yaml", [])

    counts = migrate_existing.migrate(root)

    assert counts == {}
