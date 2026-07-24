import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import approval  # noqa: E402

VALID_EVENT = {
    "type": "market",
    "year": 2026,
    "from": "2026-08-15",
    "to": "2026-08-15",
    "precision": "exact",
    "ics": False,
    "name": "Stadtfest",
}

VALID_QUELLE = {
    "url": "https://example.org/veranstaltungen",
    "license": "tos_checked",
    "retrieved_at": "2026-07-24",
    "extraction": "llm",
}


@pytest.fixture(autouse=True)
def _isolate_data_root(tmp_path, monkeypatch):
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")
    return tmp_path / "data"


def test_writes_data_yaml_and_page_yaml_for_a_new_subject(_isolate_data_root):
    path = approval.write_event("veranstaltungen", "hechingen", "Stadtfest Hechingen", VALID_EVENT, VALID_QUELLE)

    assert path.exists()
    datei = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert datei["subject"] == {"slug": "hechingen", "category": "veranstaltungen"}
    assert len(datei["windows"]) == 1
    assert datei["windows"][0]["type"] == "market"

    page_path = path.parent / "page.yaml"
    assert page_path.exists()
    assert yaml.safe_load(page_path.read_text(encoding="utf-8"))["title"] == "Stadtfest Hechingen"


def test_page_yaml_is_not_overwritten_on_a_second_write(_isolate_data_root):
    approval.write_event("veranstaltungen", "hechingen", "Stadtfest Hechingen", VALID_EVENT, VALID_QUELLE)
    path = approval.write_event(
        "veranstaltungen", "hechingen", "A Different Title (should be ignored)",
        {**VALID_EVENT, "from": "2027-08-15", "to": "2027-08-15", "year": 2027}, VALID_QUELLE,
    )

    page_path = path.parent / "page.yaml"
    assert yaml.safe_load(page_path.read_text(encoding="utf-8"))["title"] == "Stadtfest Hechingen"


def test_raises_approval_error_without_writing_anything_on_invalid_event(_isolate_data_root, tmp_path):
    invalid_event = {**VALID_EVENT, "precision": "not-a-real-precision"}

    with pytest.raises(approval.ApprovalError):
        approval.write_event("veranstaltungen", "hechingen", "Stadtfest Hechingen", invalid_event, VALID_QUELLE)

    assert not (tmp_path / "data" / "veranstaltungen" / "hechingen" / "data.yaml").exists()


def test_second_window_for_the_same_subject_merges_instead_of_replacing(_isolate_data_root):
    approval.write_event("veranstaltungen", "hechingen", "Stadtfest Hechingen", VALID_EVENT, VALID_QUELLE)
    path = approval.write_event(
        "veranstaltungen", "hechingen", "Stadtfest Hechingen",
        {**VALID_EVENT, "type": "flea_market", "from": "2026-09-01", "to": "2026-09-01", "name": "Flohmarkt"},
        VALID_QUELLE,
    )

    datei = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(datei["windows"]) == 2


def test_same_type_and_name_on_a_different_date_is_kept_as_its_own_window(_isolate_data_root):
    """The eclipse regression: a source whose windows all share one generic
    type ("event", "Sonnenfinsternis") - with replace_key=("type",) every
    approval replaced the previous one, so 151 approvals left 1 window."""
    approval.write_event("wissenschaft", "finsternisse", "Finsternisse", VALID_EVENT, VALID_QUELLE)
    path = approval.write_event(
        "wissenschaft", "finsternisse", "Finsternisse",
        {**VALID_EVENT, "year": 2027, "from": "2027-08-02", "to": "2027-08-02"},
        VALID_QUELLE,
    )

    datei = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [w["from"] for w in datei["windows"]] == ["2026-08-15", "2027-08-02"]


def test_a_corrected_end_date_replaces_the_earlier_window(_isolate_data_root):
    approval.write_event("wissenschaft", "finsternisse", "Finsternisse", VALID_EVENT, VALID_QUELLE)
    path = approval.write_event(
        "wissenschaft", "finsternisse", "Finsternisse",
        {**VALID_EVENT, "to": "2026-08-17"}, VALID_QUELLE,
    )

    datei = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert len(datei["windows"]) == 1
    assert datei["windows"][0]["to"] == "2026-08-17"
