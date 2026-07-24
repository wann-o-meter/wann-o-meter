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
from core import approval, crawl_config, review_state, staging  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(staging, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    monkeypatch.setattr(crawl_config, "CRAWL_SOURCES_DIR", tmp_path / "crawl_sources")
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

    def test_target_file_is_stored_repo_relative_not_absolute(self, client):
        # A migration/approval-time absolute path would be wrong (or just
        # confusing) once review-state/*.yaml is committed and checked out
        # somewhere else - see approval.DATA_ROOT.parent-relative fix.
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
        )

        st = review_state.load("test-source")
        target_file = st["decisions"][candidate["content_hash"]]["target_file"]
        assert not Path(target_file).is_absolute()
        assert target_file == "data/veranstaltungen/hechingen/data.yaml"

    def test_approve_404s_for_an_unknown_source(self, client):
        response = client.post(
            "/review/unknown-source/unknown-source_deadbeef/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
        )
        assert response.status_code == 404

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


class TestPathTraversalGuards:
    """Unit-level coverage for the guards behind /review/{source_id}/... and
    /staging-document/{source_id}/{run_ts}/{doc_hash} - source_id/run_ts/
    doc_hash all come straight from the URL. An HTTP-level test here would
    be misleading: httpx/Starlette normalize a literal "../" out of a URL
    path before it ever reaches route matching, so a request like
    GET /staging-document/../../../../etc/x never actually exercises this
    code - it 404s on "no route matched", not on the guard. These call the
    guard functions directly instead, which is what actually matters if a
    differently-behaved client (or a future direct caller) ever sends a
    traversal-shaped value through."""

    def test_is_known_source_id_rejects_traversal_shaped_values(self, client):
        assert main._is_known_source_id("..") is False
        assert main._is_known_source_id("../../etc") is False

    def test_is_known_source_id_accepts_a_real_staged_source(self, client):
        _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        assert main._is_known_source_id("test-source") is True

    def test_load_candidate_rejects_a_traversal_shaped_run_ts(self, client, tmp_path):
        _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        (tmp_path / "secret.yaml").write_text("content_hash: leaked", encoding="utf-8")

        assert main._load_candidate("test-source", "..", "x") is None

    def test_doc_hash_regex_rejects_anything_but_hex(self):
        assert main._DOC_HASH_RE.match("deadbeef0123") is not None
        assert main._DOC_HASH_RE.match("../../etc/passwd") is None
        assert main._DOC_HASH_RE.match("doc*.yaml") is None


class TestStagingDocument:
    def test_serves_a_staged_document_snapshot(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        response = client.get(f"/staging-document/test-source/20260724-000000/{candidate['document']}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")

    def test_404s_for_an_unknown_source(self, client):
        response = client.get("/staging-document/unknown-source/20260724-000000/anything")
        assert response.status_code == 404

    def test_404s_for_an_unknown_document_under_a_known_source(self, client):
        _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        response = client.get("/staging-document/test-source/20260724-000000/does-not-exist")
        assert response.status_code == 404


# Only seed_url is required - id/category/allowed_domains/path_prefix are
# all derived from it (see create_crawl_source's docstring). This is the
# minimal, no-Advanced-options submission an operator actually uses.
MINIMAL_NEW_SOURCE_FORM = {"seed_url": "https://www.example.org/veranstaltungen"}

FULL_NEW_SOURCE_FORM = {
    "seed_url": "https://example.org/veranstaltungen",
    "id": "Stuttgart Veranstaltungen",
    "category": "veranstaltungen",
    "allowed_domains": "example.org, www.example.org",
    "path_prefix": "/veranstaltungen",
    "max_depth": "2",
    "formats": ["html", "ics"],
    "event_type_hint": "Stadtfest",
    "schedule": "weekly",
}


class TestCreateCrawlSource:
    def test_a_bare_seed_url_derives_id_domain_category_and_path_prefix(self, client, tmp_path):
        response = client.post("/crawl-sources/new", data=MINIMAL_NEW_SOURCE_FORM, follow_redirects=False)

        assert response.status_code == 303
        path = tmp_path / "crawl_sources" / "example-org.yaml"
        assert path.exists()

        source = crawl_config.load_crawl_source(path)
        assert source.id == "example-org"
        assert source.seed_url == "https://www.example.org/veranstaltungen"
        assert source.category == "example-org"
        assert source.allowed_domains == ["example.org"]  # "www." stripped
        assert source.path_prefix == "/veranstaltungen"
        assert source.max_depth == 2
        assert source.formats == ["html"]
        assert source.schedule == "manual"

    def test_advanced_options_override_every_derived_field(self, client, tmp_path):
        response = client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM, follow_redirects=False)

        assert response.status_code == 303
        path = tmp_path / "crawl_sources" / "stuttgart-veranstaltungen.yaml"
        assert path.exists()

        source = crawl_config.load_crawl_source(path)
        assert source.id == "stuttgart-veranstaltungen"
        assert source.category == "veranstaltungen"
        assert source.allowed_domains == ["example.org", "www.example.org"]
        assert source.path_prefix == "/veranstaltungen"
        assert source.max_depth == 2
        assert set(source.formats) == {"html", "ics"}
        assert source.schedule == "weekly"

    def test_rejects_a_seed_url_without_a_scheme_or_domain(self, client):
        response = client.post("/crawl-sources/new", data={"seed_url": "not-a-url"})
        assert response.status_code == 400

    def test_rejects_a_duplicate_id(self, client):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        response = client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        assert response.status_code == 409

    def test_two_bare_urls_on_the_same_domain_derive_distinct_ids_via_path(self, client, tmp_path):
        first = client.post("/crawl-sources/new", data={"seed_url": "https://eclipse.gsfc.nasa.gov/solar/"}, follow_redirects=False)
        second = client.post("/crawl-sources/new", data={"seed_url": "https://eclipse.gsfc.nasa.gov/lunar/"}, follow_redirects=False)

        assert first.status_code == 303
        assert second.status_code == 303
        assert (tmp_path / "crawl_sources" / "eclipse-gsfc-nasa-gov.yaml").exists()
        assert (tmp_path / "crawl_sources" / "eclipse-gsfc-nasa-gov-lunar.yaml").exists()

    def test_a_seed_url_pointing_at_one_specific_page_derives_the_parent_directory_as_scope(self, client, tmp_path):
        # A path_prefix equal to the exact file (".../SEcat5/page.html")
        # would only ever match that one page again (startswith check in
        # core/crawler.py's in_scope()) - the parent directory is what
        # actually scopes a crawl to "this section of the site".
        response = client.post(
            "/crawl-sources/new",
            data={"seed_url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        source = crawl_config.load_crawl_source(tmp_path / "crawl_sources" / "eclipse-gsfc-nasa-gov.yaml")
        assert source.path_prefix == "/SEcat5"

    def test_a_third_bare_url_sharing_domain_and_first_path_segment_still_409s(self, client):
        client.post("/crawl-sources/new", data={"seed_url": "https://eclipse.gsfc.nasa.gov/lunar/"})
        client.post("/crawl-sources/new", data={"seed_url": "https://eclipse.gsfc.nasa.gov/lunar/2030"})
        response = client.post("/crawl-sources/new", data={"seed_url": "https://eclipse.gsfc.nasa.gov/lunar/2031"})
        assert response.status_code == 409

    def test_rejects_a_reserved_category(self, client):
        response = client.post("/crawl-sources/new", data={**FULL_NEW_SOURCE_FORM, "category": "feiertage"})
        assert response.status_code == 400

    def test_rejects_an_out_of_range_max_depth(self, client):
        response = client.post("/crawl-sources/new", data={**FULL_NEW_SOURCE_FORM, "max_depth": "99"})
        assert response.status_code == 400
