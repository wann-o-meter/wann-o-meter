import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import approval, generic_source, review_state, runner, staging  # noqa: E402
from core.types import ExtractionResult  # noqa: E402

BATCH_CONFIG = (
    "kind: batch\n"
    "id: schulferien_kmk\n"
    "category: schulferien\n"
    "url: https://www.kmk.org/service/ferienregelung/ferienkalender.html\n"
    "license: official_par5\n"
    "strategy: llm\n"
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    monkeypatch.setattr(review_state, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")

    sources_dir = tmp_path / "_sources"
    sources_dir.mkdir()
    (sources_dir / "schulferien_kmk.yaml").write_text(BATCH_CONFIG, encoding="utf-8")
    monkeypatch.setattr(runner, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(runner, "fetch_bytes", lambda url: (b"<html></html>", "text/html"))

    result = ExtractionResult(
        subject={"slug": "by", "name": "Schulferien Bayern", "category": "schulferien"},
        file_path=tmp_path / "data" / "schulferien" / "by" / "data.yaml",
        zeitfenster=[
            {
                "type": "school_holidays-autumn",
                "year": 2028,
                "from": "2028-10-30",
                "to": "2028-11-03",
                "precision": "exact",
                "ics": False,
                "name": "Herbstferien",
            }
        ],
        source={
            "url": "https://www.kmk.org/service/ferienregelung/ferienkalender.html",
            "license": "official_par5",
            "retrieved_at": "2028-01-01",
            "extraction": "llm",
        },
    )
    monkeypatch.setattr(generic_source, "extract", lambda config, raw, params: [result])
    return tmp_path


def _staged_candidate(tmp_path):
    paths = list((tmp_path / "staging").glob("**/candidates/*.yaml"))
    assert len(paths) == 1, f"expected one staged candidate, got {paths}"
    return yaml.safe_load(paths[0].read_text(encoding="utf-8"))


def test_a_staged_candidate_carries_the_subjects_category_not_its_slug(isolated):
    """The review UI files an approval under the candidate's own `category`
    (review/service.py's _target_category_for). Defaulting it to subject_slug
    sent a hand-approved KMK candidate to data/by/by/ while the same run's
    auto-approved windows went to data/schulferien/by/ - two pages for one
    Bundesland, and a top-level `by` category created silently because it is
    not in RESERVED_CATEGORIES."""
    runner.run("schulferien_kmk", {"jahr": "2028"})

    candidate = _staged_candidate(isolated)
    assert candidate["category"] == "schulferien"
    assert candidate["subject_slug"] == "by"


def test_a_staged_candidate_carries_the_readable_subject_name(isolated):
    """page.yaml is written by whichever path approves FIRST and never
    rewritten, so a slug here pins "by" as the page heading permanently."""
    runner.run("schulferien_kmk", {"jahr": "2028"})

    assert _staged_candidate(isolated)["subject_name"] == "Schulferien Bayern"


def test_every_url_in_the_list_is_fetched_and_staged(isolated, monkeypatch):
    """One school year per PDF: two documents, two snapshots, one source."""
    (isolated / "_sources" / "schulferien_kmk.yaml").write_text(
        BATCH_CONFIG.replace(
            "url: https://www.kmk.org/service/ferienregelung/ferienkalender.html\n",
            "urls:\n  - https://kmk.invalid/FER2025_26.pdf\n  - https://kmk.invalid/FER2026_27.pdf\n",
        ),
        encoding="utf-8",
    )
    fetched = []
    monkeypatch.setattr(runner, "fetch_bytes", lambda url: (fetched.append(url), (url.encode(), "text/html"))[1])

    runner.run("schulferien_kmk", {})

    assert fetched == ["https://kmk.invalid/FER2025_26.pdf", "https://kmk.invalid/FER2026_27.pdf"]
    assert len(list((isolated / "staging").glob("**/documents/*.md"))) == 2
