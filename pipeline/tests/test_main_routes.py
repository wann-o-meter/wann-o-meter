"""End-to-end coverage (through the actual FastAPI routes) for: the
/page-data + /page-meta path-traversal guards, and the review-approval
flow (/review/.../approve|modify|reject) that replaced the old
/create-page - a candidate is staged, then approved/modified/rejected via
the actual route, verifying the write lands in data/ and the decision in
review-state. Isolated from the real repo via monkeypatched
DATA_ROOT/STAGING_ROOT/REVIEW_STATE_ROOT (tmp_path), so this never touches
real data/."""

import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

import main  # noqa: E402
from core import approval, review_state, staging  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(staging, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    return TestClient(main.app)


def _stage_candidate(source_id: str, run_ts: str, subject_slug: str, event: dict) -> dict:
    doc_hash = staging.write_document(source_id, run_ts, "https://example.invalid/events", "text/calendar", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    candidate = staging.build_candidate(source_id, subject_slug, event, doc_hash)
    staging.write_candidate(source_id, run_ts, candidate)
    return candidate


class TestPageDataAndMetaGuards:
    def _seed_nested_page(self, data_root):
        folder = data_root / "sport" / "fussball" / "bundesliga" / "spieltag-1"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "data.yaml").write_text(yaml.dump({"subject": {"slug": "spieltag-1"}}), encoding="utf-8")
        (folder / "page.yaml").write_text(yaml.dump({"title": "Spieltag 1"}), encoding="utf-8")
        return folder

    def test_serves_data_yaml_for_a_deeply_nested_page(self, client):
        self._seed_nested_page(main.DATA_ROOT)
        response = client.get("/page-data/sport/fussball/bundesliga/spieltag-1")
        assert response.status_code == 200
        assert "spieltag-1" in response.text

    def test_serves_page_yaml_for_a_deeply_nested_page(self, client):
        self._seed_nested_page(main.DATA_ROOT)
        response = client.get("/page-meta/sport/fussball/bundesliga/spieltag-1")
        assert response.status_code == 200
        assert "Spieltag 1" in response.text

    def test_404s_for_a_category_folder_that_is_not_a_page(self, client):
        # "sport/fussball" exists as an intermediate category node (holds
        # spieltag-1), but has no page.yaml/data.yaml of its own - the guard
        # must reject it, not just check that it resolves under DATA_ROOT.
        self._seed_nested_page(main.DATA_ROOT)
        response = client.get("/page-data/sport/fussball")
        assert response.status_code == 404

    def test_404s_on_a_path_traversal_attempt(self, client):
        self._seed_nested_page(main.DATA_ROOT)
        response = client.get("/page-data/../../../../../../etc/passwd")
        assert response.status_code == 404

    def test_404s_for_a_nonexistent_page(self, client):
        response = client.get("/page-data/sport/fussball/bundesliga/does-not-exist")
        assert response.status_code == 404


VALID_EVENT = {
    "type": "market", "year": 2026, "from": "2026-08-15", "to": "2026-08-15",
    "precision": "exact", "ics": True, "name": "Stadtfest",
}


class TestReviewApprove:
    def test_approve_writes_the_event_and_records_the_decision(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        data_path = main.DATA_ROOT / "veranstaltungen" / "hechingen" / "data.yaml"
        assert data_path.exists()
        datei = yaml.safe_load(data_path.read_text(encoding="utf-8"))
        assert datei["windows"][0]["name"] == "Stadtfest"

        st = review_state.load("test-source")
        assert st["decisions"][candidate["content_hash"]]["status"] == "approved"

    def test_approve_rejects_an_invalid_license(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "veranstaltungen", "license": "not-a-real-license"},
        )

        assert response.status_code == 400

    def test_approve_404s_for_an_unknown_candidate(self, client):
        response = client.post(
            "/review/test-source/test-source_doesnotexist/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
        )
        assert response.status_code == 404


class TestReviewModify:
    def test_modify_writes_the_corrected_event_and_records_the_correction(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/modify",
            data={
                "category": "veranstaltungen", "license": "tos_checked",
                "type": "market", "name": "Stadtfest Hechingen", "year": "2026",
                "from": "2026-08-15", "to": "2026-08-16", "precision": "exact",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        datei = yaml.safe_load((main.DATA_ROOT / "veranstaltungen" / "hechingen" / "data.yaml").read_text(encoding="utf-8"))
        assert datei["windows"][0]["name"] == "Stadtfest Hechingen"
        assert datei["windows"][0]["to"] == "2026-08-16"

        st = review_state.load("test-source")
        decision = st["decisions"][candidate["content_hash"]]
        assert decision["status"] == "modified"
        assert decision["corrected_event"]["name"] == "Stadtfest Hechingen"


class TestReviewReject:
    def test_reject_records_the_decision_without_writing_anything(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)

        response = client.post(f"/review/test-source/{candidate['candidate_id']}/reject", follow_redirects=False)

        assert response.status_code == 302
        assert not (main.DATA_ROOT / "veranstaltungen").exists()
        st = review_state.load("test-source")
        assert st["decisions"][candidate["content_hash"]]["status"] == "rejected"

    def test_rejected_candidate_no_longer_appears_in_the_review_queue(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        client.post(f"/review/test-source/{candidate['candidate_id']}/reject")

        response = client.get("/review")

        assert response.status_code == 200
        assert candidate["candidate_id"] not in response.text


class TestStagingDocument:
    def test_serves_a_staged_document_snapshot(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        response = client.get(f"/staging-document/test-source/20260724-000000/{candidate['document']}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")

    def test_404s_on_path_traversal_in_source_id(self, client):
        response = client.get("/staging-document/../../../../etc/doc_hash")
        assert response.status_code == 404

    def test_404s_for_an_unknown_document(self, client):
        response = client.get("/staging-document/test-source/20260724-000000/does-not-exist")
        assert response.status_code == 404
