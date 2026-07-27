"""End-to-end coverage (through the actual FastAPI routes) for: the
/page-data + /page-meta path-traversal guards, and the review-approval
flow (/review/.../approve|modify|reject) that replaced the old
/create-page - a candidate is staged, then approved/modified/rejected via
the actual route, verifying the write lands in data/ and the decision in
review-state. Isolated from the real repo via monkeypatched
DATA_ROOT/STAGING_ROOT/REVIEW_STATE_ROOT (tmp_path), so this never touches
real data/."""

import re
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import approval, crawl_config, review_state, staging  # noqa: E402
from review import service  # noqa: E402
from review.app import app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(staging, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(review_state, "REVIEW_STATE_ROOT", tmp_path / "review-state")
    monkeypatch.setattr(review_state, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(crawl_config, "CRAWL_SOURCES_DIR", tmp_path / "crawl_sources")
    return TestClient(app)


def _stage_candidate(source_id: str, run_ts: str, subject_slug: str, event: dict, subject_name: str | None = None, category: str | None = None, url: str = "https://example.invalid/events") -> dict:
    doc_hash = staging.write_document(source_id, run_ts, url, "text/calendar", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    candidate = staging.build_candidate(source_id, subject_slug, event, doc_hash, subject_name=subject_name, category=category)
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
        self._seed_nested_page(service.DATA_ROOT)
        response = client.get("/page-data/sport/fussball/bundesliga/spieltag-1")
        assert response.status_code == 200
        assert "spieltag-1" in response.text

    def test_serves_page_yaml_for_a_deeply_nested_page(self, client):
        self._seed_nested_page(service.DATA_ROOT)
        response = client.get("/page-meta/sport/fussball/bundesliga/spieltag-1")
        assert response.status_code == 200
        assert "Spieltag 1" in response.text

    def test_404s_for_a_category_folder_that_is_not_a_page(self, client):
        # "sport/fussball" exists as an intermediate category node (holds
        # spieltag-1), but has no page.yaml/data.yaml of its own - the guard
        # must reject it, not just check that it resolves under DATA_ROOT.
        self._seed_nested_page(service.DATA_ROOT)
        response = client.get("/page-data/sport/fussball")
        assert response.status_code == 404

    def test_404s_on_a_path_traversal_attempt(self, client):
        self._seed_nested_page(service.DATA_ROOT)
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
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT, category="veranstaltungen")

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        data_path = service.DATA_ROOT / "veranstaltungen" / "hechingen" / "data.yaml"
        assert data_path.exists()
        datei = yaml.safe_load(data_path.read_text(encoding="utf-8"))
        assert datei["windows"][0]["name"] == "Stadtfest"

        # No review-state entry: the window being in data.yaml IS the record.
        assert review_state.already_approved("veranstaltungen", "hechingen", VALID_EVENT)
        assert review_state.load("test-source") == {"rejected": []}

    def test_an_approved_candidate_leaves_the_queue(self, client):
        """It leaves because it is now in data.yaml, not because anything was
        written to review-state - delete it from the file by hand and it is
        offered again."""
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT, category="veranstaltungen")
        client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
        )
        assert service._review_queue() == []

        data_path = service.DATA_ROOT / "veranstaltungen" / "hechingen" / "data.yaml"
        datei = yaml.safe_load(data_path.read_text(encoding="utf-8"))
        datei["windows"] = []
        data_path.write_text(yaml.dump(datei), encoding="utf-8")

        assert len(service._review_queue()) == 1

    def test_approving_into_another_category_does_not_loop(self, client):
        """The source writes to data/veranstaltungen/, but the operator files
        this one under data/kultur/. The source's own page then doesn't hold
        it, so without suppressing it the next run would offer it again and
        the override would have to be repeated forever."""
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT, category="veranstaltungen")

        client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "kultur", "license": "tos_checked"},
        )

        assert (service.DATA_ROOT / "kultur" / "hechingen" / "data.yaml").exists()
        assert service._review_queue() == []

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
        datei = yaml.safe_load((service.DATA_ROOT / "veranstaltungen" / "hechingen" / "data.yaml").read_text(encoding="utf-8"))
        assert datei["windows"][0]["name"] == "Stadtfest Hechingen"
        assert datei["windows"][0]["to"] == "2026-08-16"

        # The correction is in data.yaml. The ORIGINAL identity is retired,
        # or the source would re-extract it and re-queue it every run.
        assert review_state.is_rejected(review_state.load("test-source"), "hechingen", VALID_EVENT)
        assert service._review_queue() == []


class TestReviewReject:
    def test_reject_records_the_decision_without_writing_anything(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)

        response = client.post(f"/review/test-source/{candidate['candidate_id']}/reject", follow_redirects=False)

        assert response.status_code == 302
        assert not (service.DATA_ROOT / "veranstaltungen").exists()
        assert review_state.is_rejected(review_state.load("test-source"), "hechingen", VALID_EVENT)

    def test_rejected_candidate_no_longer_appears_in_the_review_queue(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        client.post(f"/review/test-source/{candidate['candidate_id']}/reject")

        response = client.get("/review")

        assert response.status_code == 200
        assert candidate["candidate_id"] not in response.text


def _eclipse_event(date: str) -> dict:
    """Mirrors what crawl_runner._window produces for a date-table source:
    every row carries the SAME name, only the date differs."""
    return {
        "type": "event", "year": int(date[:4]), "from": date, "to": date,
        "precision": "exact", "ics": True, "name": "Sonnenfinsternis",
    }


class TestPageTitleOnApproval:
    """page.yaml is written by whichever path approves first and never
    rewritten, so the review UI passing the raw slug as title used to pin
    e.g. "eclipse-gsfc-nasa-gov" as a page heading permanently - even though
    the same source's auto-waved-through candidates got a cleaned-up name."""

    def _title(self) -> str:
        return yaml.safe_load((service.DATA_ROOT / "sofi" / "sofi" / "page.yaml").read_text(encoding="utf-8"))["title"]

    def test_approving_uses_the_candidates_suggested_name(self, client):
        candidate = _stage_candidate(
            "test-source", "20260724-000000", "sofi", VALID_EVENT, subject_name="Sonnenfinsternis",
        )

        client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "sofi", "license": "tos_checked"},
        )

        assert self._title() == "Sonnenfinsternis"

    def test_modifying_uses_it_too(self, client):
        candidate = _stage_candidate(
            "test-source", "20260724-000000", "sofi", VALID_EVENT, subject_name="Sonnenfinsternis",
        )

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/modify",
            data={
                "category": "sofi", "license": "tos_checked", "type": "market",
                "name": "Stadtfest", "year": "2026",
                "from": "2026-08-16", "to": "2026-08-16", "precision": "exact",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert self._title() == "Sonnenfinsternis"

    def test_a_candidate_staged_before_subject_name_existed_still_works(self, client):
        """Candidates already on disk from an earlier run have no
        subject_name key at all - that must fall back to the slug, not
        crash the approval."""
        candidate = _stage_candidate("test-source", "20260724-000000", "sofi", VALID_EVENT)
        del candidate["subject_name"]
        staging.write_candidate("test-source", "20260724-000000", candidate)

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "sofi", "license": "tos_checked"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert self._title() == "sofi"


class TestBulkApprove:
    def test_the_queue_renders_a_checkbox_and_a_real_license_per_pending_candidate(self, client):
        """The other tests here all POST, and every one of them empties the
        queue - so they only ever render review.html's empty branch and would
        stay green even if the form itself were broken. This one renders the
        NON-empty branch and pins the two values the POST depends on: the
        checkbox name _approve_one is fed from, and a license string that is
        actually in LICENSE_VALUES (an empty <option value=""> would fail
        every row at submit time)."""
        candidate = _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event("2026-08-12"))

        response = client.get("/review")

        assert response.status_code == 200
        assert f'name="selected" value="test-source/{candidate["candidate_id"]}"' in response.text
        assert '/review/bulk-edit' in response.text
        assert any(f'<option value="{value}">' in response.text for value in service.LICENSE_VALUES)

    def test_the_single_candidate_form_prefills_the_sources_category(self, client):
        candidate = _stage_candidate(
            "test-source", "20260724-000000", "sonnenfinsternis", _eclipse_event("2026-08-12"),
            category="astronomie",
        )

        response = client.get(f"/review/test-source/{candidate['candidate_id']}")

        assert response.status_code == 200
        assert 'name="category" list="category-suggestions" value="astronomie"' in response.text

    def test_a_candidate_is_filed_under_its_sources_category_not_its_slug(self, client):
        """The aggregation case: a source configured to write into
        data/astronomie/sonnenfinsternis/ must land there when approved in
        bulk too. Defaulting the category to the slug would file it under
        data/sonnenfinsternis/sonnenfinsternis/ - a different page than the
        same source's auto-approved candidates, which is exactly the split
        subject_slug exists to close."""
        candidate = _stage_candidate(
            "test-source", "20260724-000000", "sonnenfinsternis", _eclipse_event("2026-08-12"),
            subject_name="Sonnenfinsternis", category="astronomie",
        )

        client.post(
            "/review/bulk-edit",
            data={"selected": [f"test-source/{candidate['candidate_id']}"], "license": "tos_checked"},
        )

        assert (service.DATA_ROOT / "astronomie" / "sonnenfinsternis" / "data.yaml").exists()
        assert not (service.DATA_ROOT / "sonnenfinsternis").exists()

    def test_a_source_that_has_never_run_is_reported_not_a_500(self, client, tmp_path):
        """_is_known_source_id() accepts a source that only has a config file -
        data/_sources/stuttgarter-fruehlingsfest-de.yaml is exactly that today.
        _latest_run_ts() is then None, and _load_candidate() would build
        STAGING_ROOT / source_id / None and raise TypeError, turning one
        unrunnable row into a 500 for the whole batch."""
        (tmp_path / "crawl_sources").mkdir(parents=True, exist_ok=True)
        (tmp_path / "crawl_sources" / "never-run.yaml").write_text(
            "id: never-run\nseed_url: https://example.invalid/\ncategory: astronomie\n"
            "scope:\n  allowed_domains: [example.invalid]\n",
            encoding="utf-8",
        )

        response = client.post(
            "/review/bulk-edit",
            data={"selected": ["never-run/never-run:deadbeef"], "license": "tos_checked"},
        )

        assert response.status_code == 200

    def test_the_reject_button_records_rejections_and_writes_no_page(self, client):
        """Both bulk buttons submit the same form, so the only thing telling
        them apart is `action` (see review.html - one name, two values). If
        that branch were dropped, a Reject click would silently approve every
        checked row and write pages nobody asked for."""
        candidates = [
            _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event(date))
            for date in ["2026-08-12", "2027-08-02"]
        ]

        response = client.post(
            "/review/bulk-edit",
            data={
                "selected": [f"test-source/{c['candidate_id']}" for c in candidates],
                "license": "tos_checked",
                "action": "reject",
            },
        )

        assert response.status_code == 200
        st = review_state.load("test-source")
        assert all(review_state.is_rejected(st, "sofi", c["event"]) for c in candidates)
        assert not (service.DATA_ROOT / "sofi").exists()
        assert service._review_queue() == []

    def test_an_unknown_action_is_refused(self, client):
        """`action` arrives straight from the form, so it's a trust boundary
        like any other Form field - an unrecognised value must not fall
        through to the approve branch by default."""
        candidate = _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event("2026-08-12"))

        response = client.post(
            "/review/bulk-edit",
            data={
                "selected": [f"test-source/{candidate['candidate_id']}"],
                "license": "tos_checked",
                "action": "delete-everything",
            },
        )

        assert response.status_code == 400
        assert review_state.load("test-source")["rejected"] == []

    def test_rejecting_does_not_require_a_valid_license(self, client):
        """A rejection writes no data.yaml, so there is no Quelle to stamp a
        license on - failing the batch over the license select would block
        the one action that needs nothing from it."""
        candidate = _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event("2026-08-12"))

        response = client.post(
            "/review/bulk-edit",
            data={
                "selected": [f"test-source/{candidate['candidate_id']}"],
                "license": "",
                "action": "reject",
            },
        )

        assert response.status_code == 200
        assert review_state.is_rejected(review_state.load("test-source"), "sofi", candidate["event"])

    def test_many_identically_named_events_each_land_as_their_own_window(self, client):
        """The case bulk approve exists for - a date-table source where every
        candidate shares a name. Guards approval.DEFAULT_REPLACE_KEY still
        including "from": with a key of just ("type", "name") these three
        would collapse into one window and a 200-row approval would silently
        write one row."""
        dates = ["2026-08-12", "2027-08-02", "2028-07-22"]
        candidates = [
            _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event(date))
            for date in dates
        ]

        response = client.post(
            "/review/bulk-edit",
            data={
                "selected": [f"test-source/{c['candidate_id']}" for c in candidates],
                "license": "tos_checked",
            },
        )

        assert response.status_code == 200
        datei = yaml.safe_load((service.DATA_ROOT / "sofi" / "sofi" / "data.yaml").read_text(encoding="utf-8"))
        assert sorted(w["from"] for w in datei["windows"]) == dates

    def test_every_approved_row_is_recorded_and_leaves_the_queue(self, client):
        candidates = [
            _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event(date))
            for date in ("2026-08-12", "2027-08-02")
        ]

        client.post(
            "/review/bulk-edit",
            data={
                "selected": [f"test-source/{c['candidate_id']}" for c in candidates],
                "license": "tos_checked",
            },
        )

        assert all(review_state.already_approved("sofi", "sofi", c["event"]) for c in candidates)
        assert service._review_queue() == []

    def test_one_bad_row_is_reported_without_dropping_the_good_ones(self, client):
        good = _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event("2026-08-12"))

        response = client.post(
            "/review/bulk-edit",
            data={
                "selected": [f"test-source/{good['candidate_id']}", "test-source/deadbeef", "malformed"],
                "license": "tos_checked",
            },
        )

        assert response.status_code == 200
        assert "1 approved, 2 failed" in response.text
        assert (service.DATA_ROOT / "sofi" / "sofi" / "data.yaml").exists()

    def test_an_invalid_license_writes_nothing(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "sofi", _eclipse_event("2026-08-12"))

        response = client.post(
            "/review/bulk-edit",
            data={"selected": [f"test-source/{candidate['candidate_id']}"], "license": "not-a-license"},
        )

        assert response.status_code == 400
        assert not (service.DATA_ROOT / "sofi").exists()


class TestChainToNextReviewCandidate:
    def test_deciding_the_only_candidate_redirects_back_to_the_queue(self, client):
        candidate = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/approve",
            data={"category": "veranstaltungen", "license": "tos_checked"},
            follow_redirects=False,
        )

        assert response.headers["location"] == "/review"

    def test_deciding_one_of_two_candidates_redirects_straight_to_the_other(self, client):
        first = _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        second_event = {**VALID_EVENT, "name": "Weihnachtsmarkt", "from": "2026-12-01", "to": "2026-12-24"}
        second = _stage_candidate("test-source", "20260724-000000", "stuttgart", second_event)

        response = client.post(
            f"/review/test-source/{first['candidate_id']}/reject",
            follow_redirects=False,
        )

        assert response.headers["location"] == f"/review/test-source/{second['candidate_id']}"


class TestPlaintextFromMarkdown:
    def test_strips_link_syntax_but_keeps_the_label(self):
        result = service._plaintext_from_markdown("[09338](../5MCSEmap/1901-2000/1924-08-30.gif) 1924 Aug 30")
        assert result == "09338 1924 Aug 30"

    def test_strips_bold_and_italic_markers(self):
        assert service._plaintext_from_markdown("**bold** and *italic*") == "bold and italic"

    def test_strips_bold_markers_that_wrap_across_a_line_break(self):
        # Regression: "." doesn't match "\n" by default, so a **bold**
        # span whose content wraps onto its own line (real shape from a
        # staged eclipse.gsfc.nasa.gov snapshot) left the bare "**"
        # markers behind as their own lines instead of being stripped.
        result = service._plaintext_from_markdown("**\n 1901 to 2000 ( 1901 CE to 2000 CE )\n**")
        assert "**" not in result
        assert "1901 to 2000 ( 1901 CE to 2000 CE )" in result

    def test_strips_heading_markers(self):
        assert service._plaintext_from_markdown("## Statistics for Solar Eclipses") == "Statistics for Solar Eclipses"

    def test_collapses_runs_of_blank_lines_to_exactly_one_blank_line(self):
        # Not zero: a wall of text with no paragraph breaks at all is just
        # as hard to scan as ten blank lines in a row.
        result = service._plaintext_from_markdown("first\n\n\n\nsecond\n\n\nthird")
        assert result == "first\n\nsecond\n\nthird"

    def test_collapses_a_run_of_lone_space_lines_to_one_blank_line_not_just_every_other_one(self):
        # Regression: a naive "\n{2,}" collapse on lines that are each a
        # single lingering space (not truly empty) only removed every
        # other blank line - verified against a real staged
        # eclipse.gsfc.nasa.gov snapshot, which has exactly this shape.
        text = "Catalog of Solar Eclipses: 1901 to 2000\n \n \n \n \n \n \n \n \n \nFive Millennium Catalog"
        result = service._plaintext_from_markdown(text)
        assert result == "Catalog of Solar Eclipses: 1901 to 2000\n\nFive Millennium Catalog"

    def test_a_dense_realistic_row_reads_cleanly(self):
        row = (
            "[09338](../5MCSEmap/1901-2000/1924-08-30.gif) 1924 Aug 30 "
            "[08:23:00](../SEplot/SEplot1901/SE1924Aug30P.GIF) 24 -932 "
            "[153](../SEsaros/SEsaros153.html) P t- [ 1.3123](../SEsearch/SEdata.php?Ecl=19240830) "
            "0.4245 71N 173E 0"
        )
        result = service._plaintext_from_markdown(row)
        assert "[" not in result and "](" not in result
        assert "1924 Aug 30" in result


class TestHighlightDates:
    def test_highlights_an_exact_iso_date_match(self):
        result = service._highlight_dates("seen on 2026-08-15 in the table", ["2026-08-15"])
        assert result == "seen on <mark>2026-08-15</mark> in the table"

    def test_highlights_the_human_readable_variant_too(self):
        # eclipse.gsfc.nasa.gov's actual catalog format, verified against a
        # real staged snapshot - a source's date formatting varies, so both
        # this and the plain ISO form are tried.
        result = service._highlight_dates("row: 1901 Jan 07 partial", ["1901-01-07"])
        assert result == "row: <mark>1901 Jan 07</mark> partial"

    def test_no_match_returns_escaped_text_unchanged_otherwise(self):
        result = service._highlight_dates("<script>nothing matches here</script>", ["2026-08-15"])
        assert result == "&lt;script&gt;nothing matches here&lt;/script&gt;"

    def test_output_is_always_html_escaped_even_around_a_match(self):
        result = service._highlight_dates("<b>2026-08-15</b>", ["2026-08-15"])
        assert result == "&lt;b&gt;<mark>2026-08-15</mark>&lt;/b&gt;"

    def test_human_variant_is_none_for_a_recurring_month_only_window(self):
        # "--08" (a recurring window's month-only from/to, see
        # datePartSchema) isn't a full date - _highlight_dates still tries
        # a literal match for whatever string it's given (harmless either
        # way), but the "YYYY Mon DD" human-readable guess only makes sense
        # for a full ISO date and must not be attempted here.
        assert service._human_date_variant("--08") is None

    def test_none_dates_are_skipped_without_erroring(self):
        result = service._highlight_dates("plain text", [None, "2026-08-15"])
        assert result == "plain text"


class TestReviewCandidateDetailHighlighting:
    def test_an_html_document_snapshot_is_shown_with_the_candidates_date_highlighted(self, client):
        doc_hash = staging.write_document(
            "test-source", "20260724-000000", "https://example.invalid/events",
            "text/html", b"<html><body><p>Stadtfest am 2026-08-15 in Hechingen</p></body></html>",
        )
        candidate = staging.build_candidate("test-source", "hechingen", VALID_EVENT, doc_hash)
        staging.write_candidate("test-source", "20260724-000000", candidate)

        response = client.get(f"/review/test-source/{candidate['candidate_id']}")

        assert response.status_code == 200
        assert "<mark>2026-08-15</mark>" in response.text


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
        assert service._is_known_source_id("..") is False
        assert service._is_known_source_id("../../etc") is False

    def test_is_known_source_id_accepts_a_real_staged_source(self, client):
        _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        assert service._is_known_source_id("test-source") is True

    def test_load_candidate_rejects_a_traversal_shaped_run_ts(self, client, tmp_path):
        _stage_candidate("test-source", "20260724-000000", "hechingen", VALID_EVENT)
        (tmp_path / "secret.yaml").write_text("content_hash: leaked", encoding="utf-8")

        assert service._load_candidate("test-source", "..", "x") is None

    def test_doc_hash_regex_rejects_anything_but_hex(self):
        assert service._DOC_HASH_RE.match("deadbeef0123") is not None
        assert service._DOC_HASH_RE.match("../../etc/passwd") is None
        assert service._DOC_HASH_RE.match("doc*.yaml") is None


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


class TestDeleteCrawlSource:
    def test_removes_the_config_file_and_redirects(self, client, tmp_path):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        path = tmp_path / "crawl_sources" / "stuttgart-veranstaltungen.yaml"
        assert path.exists()

        response = client.post("/crawl-sources/stuttgart-veranstaltungen/delete", follow_redirects=False)

        assert response.status_code == 303
        assert not path.exists()

    def test_404s_for_an_unknown_source(self, client):
        response = client.post("/crawl-sources/does-not-exist/delete")
        assert response.status_code == 404

    def test_409s_while_the_source_is_running(self, client):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        service.state.running_sources.add("stuttgart-veranstaltungen")
        try:
            response = client.post("/crawl-sources/stuttgart-veranstaltungen/delete")
            assert response.status_code == 409
        finally:
            service.state.running_sources.discard("stuttgart-veranstaltungen")


class TestRunningProgressSurvivesAReload:
    """A crawl runs in a background thread, so it outlives the page that
    started it - reloading mid-run used to show a bare "Running…" with the
    progress line blank, because state.progress reached the JSON poll but was
    never passed to the template."""

    def _running(self, client, progress):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        service.state.running_sources.add("stuttgart-veranstaltungen")
        service.state.progress["stuttgart-veranstaltungen"] = progress

    def _cleanup(self):
        service.state.running_sources.discard("stuttgart-veranstaltungen")
        service.state.progress.pop("stuttgart-veranstaltungen", None)

    def test_the_full_page_renders_the_stored_progress(self, client):
        self._running(client, {"phase": "crawling", "detail": "Fetching page 3: https://example.org/a"})
        try:
            response = client.get("/crawl-sources")
        finally:
            self._cleanup()

        assert "Crawling" in response.text
        assert "Fetching page 3: https://example.org/a" in response.text

    def test_the_htmx_table_fragment_renders_it_too(self, client):
        self._running(client, {"phase": "extracting", "detail": "Document 2/7"})
        try:
            response = client.get("/crawl-sources-table")
        finally:
            self._cleanup()

        assert "Extracting" in response.text
        assert "Document 2/7" in response.text


class TestSourcePages:
    def test_falls_back_to_the_staged_documents_when_no_live_run_state_exists(self, client):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        staging.write_document(
            "stuttgart-veranstaltungen", "20260724-000000",
            "https://example.org/veranstaltungen/2026", "text/html", b"<html>x</html>",
        )
        service.state.pages.pop("stuttgart-veranstaltungen", None)

        rows = service._source_pages("stuttgart-veranstaltungen")

        assert rows == [{"url": "https://example.org/veranstaltungen/2026", "status": "crawled"}]

    def test_prefers_live_run_state_so_dropped_urls_stay_visible(self, client):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        staging.write_document(
            "stuttgart-veranstaltungen", "20260724-000000",
            "https://example.org/kept", "text/html", b"<html>x</html>",
        )
        service.state.pages["stuttgart-veranstaltungen"] = {
            "https://example.org/kept": "2 event(s) found",
            "https://example.org/blocked": "robots-blocked",
        }
        try:
            rows = service._source_pages("stuttgart-veranstaltungen")
        finally:
            service.state.pages.pop("stuttgart-veranstaltungen", None)

        # The staging-only view could never show the blocked URL - it never
        # became a document.
        assert rows == [
            {"url": "https://example.org/kept", "status": "2 event(s) found"},
            {"url": "https://example.org/blocked", "status": "robots-blocked"},
        ]

    def test_is_empty_for_a_source_that_never_ran(self, client):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        service.state.pages.pop("stuttgart-veranstaltungen", None)
        assert service._source_pages("stuttgart-veranstaltungen") == []

    def test_status_endpoint_carries_the_page_rows(self, client):
        client.post("/crawl-sources/new", data=FULL_NEW_SOURCE_FORM)
        service.state.pages["stuttgart-veranstaltungen"] = {"https://example.org/a": "crawled"}
        try:
            response = client.get("/crawl-sources/stuttgart-veranstaltungen/status")
        finally:
            service.state.pages.pop("stuttgart-veranstaltungen", None)

        assert response.status_code == 200
        assert response.json()["pages"] == [{"url": "https://example.org/a", "status": "crawled"}]


class TestEditCrawlSource:
    """subject_slug is how several sources aggregate into one page, but it
    could only ever be set at create time - getting it wrong meant a split
    page or re-approving every candidate by hand."""

    def _source(self, client, id, category, subject_slug, seed="https://example.org/a"):
        client.post("/crawl-sources/new", data={
            "seed_url": seed, "id": id, "category": category, "subject_slug": subject_slug,
        })

    def _approve(self, client, source_id, subject_slug, category, date, url="https://example.invalid/events"):
        # source_urls on the event is what pageDataSchema's superRefine checks
        # against source[], so the merge has to carry both across together.
        event = {**_eclipse_event(date), "source_urls": [url]}
        candidate = _stage_candidate(
            source_id, "20260724-000000", subject_slug, event, category=category, url=url,
        )
        client.post(
            f"/review/{source_id}/{candidate['candidate_id']}/approve",
            data={"category": category, "license": "tos_checked"}, follow_redirects=False,
        )
        return candidate

    def test_changing_the_slug_moves_the_approvals_so_nothing_returns_to_the_queue(self, client):
        """The whole point of the route - and it is now just the folder move.
        The approved windows travel with data.yaml, so there is nothing to
        re-key and nothing that can fail to."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        candidate = self._approve(client, "nasa-a", "nasa-a", "astronomie", "2026-08-12")

        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        assert response.status_code == 303
        assert review_state.already_approved("astronomie", "sonnenfinsternis", candidate["event"])
        assert service._review_queue() == []

    def test_moves_the_page_folder_and_carries_its_page_yaml_over(self, client):
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        self._approve(client, "nasa-a", "nasa-a", "astronomie", "2026-08-12")
        (service.DATA_ROOT / "astronomie" / "nasa-a" / "page.yaml").write_text(
            yaml.dump({"title": "Sonnenfinsternis", "description": "Von der NASA", "tags": ["astronomie"]}),
            encoding="utf-8",
        )

        client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        assert not (service.DATA_ROOT / "astronomie" / "nasa-a").exists()
        new_folder = service.DATA_ROOT / "astronomie" / "sonnenfinsternis"
        datei = yaml.safe_load((new_folder / "data.yaml").read_text(encoding="utf-8"))
        assert [w["from"] for w in datei["windows"]] == ["2026-08-12"]
        assert datei["subject"] == {"slug": "sonnenfinsternis", "category": "astronomie"}
        page = yaml.safe_load((new_folder / "page.yaml").read_text(encoding="utf-8"))
        assert page["description"] == "Von der NASA"

    def test_merging_into_an_existing_page_unions_windows_and_citations(self, client):
        """The case the whole feature exists for: one source per century of a
        catalog, both writing into one page."""
        self._source(client, "nasa-a", "astronomie", "sonnenfinsternis", seed="https://example.org/2001-2100")
        self._approve(client, "nasa-a", "sonnenfinsternis", "astronomie", "2026-08-12", url="https://example.org/2001-2100")
        self._source(client, "nasa-b", "astronomie", "nasa-b", seed="https://example.org/1901-2000")
        self._approve(client, "nasa-b", "nasa-b", "astronomie", "1999-08-11", url="https://example.org/1901-2000")

        response = client.post("/crawl-sources/nasa-b/edit", data={
            "category": "astronomie", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        assert response.status_code == 303
        assert not (service.DATA_ROOT / "astronomie" / "nasa-b").exists()
        datei = yaml.safe_load((service.DATA_ROOT / "astronomie" / "sonnenfinsternis" / "data.yaml").read_text(encoding="utf-8"))
        assert sorted(w["from"] for w in datei["windows"]) == ["1999-08-11", "2026-08-12"]
        assert len(datei["source"]) == 2

    def test_the_same_window_from_two_sources_keeps_one_entry_with_both_citations(self, client):
        """store.merge_zeitfenster's reason for existing - two sources agreeing
        on a window is aggregation, not a duplicate."""
        self._source(client, "nasa-a", "astronomie", "sonnenfinsternis", seed="https://example.org/cat-a")
        self._approve(client, "nasa-a", "sonnenfinsternis", "astronomie", "2026-08-12", url="https://example.org/cat-a")
        self._source(client, "nasa-b", "astronomie", "nasa-b", seed="https://example.org/cat-b")
        self._approve(client, "nasa-b", "nasa-b", "astronomie", "2026-08-12", url="https://example.org/cat-b")

        client.post("/crawl-sources/nasa-b/edit", data={
            "category": "astronomie", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        datei = yaml.safe_load((service.DATA_ROOT / "astronomie" / "sonnenfinsternis" / "data.yaml").read_text(encoding="utf-8"))
        assert len(datei["windows"]) == 1
        assert len(datei["windows"][0]["source_urls"]) == 2

    def test_a_category_only_change_still_moves_the_folder(self, client):
        self._source(client, "nasa-a", "eclipse", "nasa-a")
        self._approve(client, "nasa-a", "nasa-a", "eclipse", "2026-08-12")

        client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "nasa-a",
        }, follow_redirects=False)

        assert (service.DATA_ROOT / "astronomie" / "nasa-a" / "data.yaml").exists()
        assert not (service.DATA_ROOT / "eclipse" / "nasa-a").exists()
        assert service._review_queue() == []

    def test_a_target_a_source_never_wrote_to_is_not_an_error(self, client):
        """A config can name a page it never actually wrote - nothing approved
        yet, or a config that drifted away from where its approvals landed."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")

        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        assert response.status_code == 303
        assert crawl_config.load_all_crawl_sources()["nasa-a"].subject_slug == "sonnenfinsternis"

    def test_rejections_follow_the_source_to_its_new_page(self, client):
        """A rejection is scoped to the page it was made for, so moving the
        source has to carry it across - otherwise every rejected window comes
        back the first time the source runs against its new target."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        candidate = _stage_candidate("nasa-a", "20260724-000000", "nasa-a", _eclipse_event("2026-08-12"), category="astronomie")
        client.post(f"/review/nasa-a/{candidate['candidate_id']}/reject")
        self._approve(client, "nasa-a", "nasa-a", "astronomie", "2027-08-02")

        client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        st = review_state.load("nasa-a")
        assert review_state.is_rejected(st, "sonnenfinsternis", candidate["event"])
        assert not review_state.is_rejected(st, "nasa-a", candidate["event"])

    def test_editing_only_the_title_leaves_the_folder_and_approvals_alone(self, client):
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        candidate = self._approve(client, "nasa-a", "nasa-a", "astronomie", "2026-08-12")

        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "nasa-a", "subject_name": "Sonnenfinsternis",
            "event_type_hint": "Sonnenfinsternis",
        }, follow_redirects=False)

        assert response.status_code == 303
        source = crawl_config.load_all_crawl_sources()["nasa-a"]
        assert (source.subject_name, source.event_type_hint) == ("Sonnenfinsternis", "Sonnenfinsternis")
        assert review_state.already_approved("astronomie", "nasa-a", candidate["event"])
        assert (service.DATA_ROOT / "astronomie" / "nasa-a" / "data.yaml").exists()

    def test_preserves_fields_the_form_does_not_edit(self, client):
        client.post("/crawl-sources/new", data={**FULL_NEW_SOURCE_FORM, "subject_slug": "veranstaltungen"})

        client.post("/crawl-sources/stuttgart-veranstaltungen/edit", data={
            "category": "veranstaltungen", "subject_slug": "stadtfeste",
        }, follow_redirects=False)

        source = crawl_config.load_all_crawl_sources()["stuttgart-veranstaltungen"]
        assert source.max_depth == 2
        assert source.path_prefix == "/veranstaltungen"
        assert source.formats == ["html", "ics"]
        assert source.schedule == "weekly"
        assert source.allowed_domains == ["example.org", "www.example.org"]

    def test_switching_extraction_mode_persists_and_omitting_it_leaves_it_alone(self, client):
        """Regex-vs-model was settable only at create time - the edit row now
        carries it, but a POST without the field must not reset it to auto."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        base = {"category": "astronomie", "subject_slug": "nasa-a"}

        client.post("/crawl-sources/nasa-a/edit", data={**base, "extraction_mode": "static"},
                    follow_redirects=False)
        assert crawl_config.load_all_crawl_sources()["nasa-a"].extraction_mode == "static"

        client.post("/crawl-sources/nasa-a/edit", data=base, follow_redirects=False)
        assert crawl_config.load_all_crawl_sources()["nasa-a"].extraction_mode == "static"

    def test_the_edit_row_shows_the_source_s_current_extraction_mode(self, client):
        """The dropdown is fed by a Jinja global, so a missing wire-up renders
        an empty <select> rather than failing - assert on the marked option."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "nasa-a", "extraction_mode": "static",
        }, follow_redirects=False)

        row = re.search(
            r'id="crawl-source-edit-nasa-a".*?</select>',
            client.get("/crawl-sources").text, re.S,
        )
        assert row and '<option value="static" selected' in row.group(0)

    def test_rejects_an_unknown_extraction_mode(self, client):
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "nasa-a", "extraction_mode": "vibes",
        }, follow_redirects=False)
        assert response.status_code == 400

    def test_rejects_an_invalid_subject_slug(self, client):
        """A slug becomes a directory name under data/ - a trust boundary, and
        on edit it is NOT silently slugified: the operator is matching another
        source's slug exactly, so a typo has to be reported, not rewritten."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")

        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "../../etc",
        })

        assert response.status_code == 400
        assert crawl_config.load_all_crawl_sources()["nasa-a"].subject_slug == "nasa-a"

    def test_rejects_a_reserved_category(self, client):
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "feiertage", "subject_slug": "nasa-a",
        })
        assert response.status_code == 400

    def test_404s_for_an_unknown_source(self, client):
        response = client.post("/crawl-sources/does-not-exist/edit", data={
            "category": "astronomie", "subject_slug": "x",
        })
        assert response.status_code == 404

    def test_409s_while_the_source_is_running(self, client):
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        service.state.running_sources.add("nasa-a")
        try:
            response = client.post("/crawl-sources/nasa-a/edit", data={
                "category": "astronomie", "subject_slug": "sonnenfinsternis",
            })
            assert response.status_code == 409
        finally:
            service.state.running_sources.discard("nasa-a")

    def test_a_config_pointing_at_a_page_that_is_not_on_disk_still_moves(self, client):
        """A config can drift away from where its approvals actually landed.
        There is no shadow state left to corrupt, so this just re-points the
        source - the page it used to name stays on the site and stays visible
        in the Pages table, rather than being silently swallowed."""
        self._source(client, "nasa-a", "astronomie", "nasa-a")
        self._approve(client, "nasa-a", "nasa-a", "astronomie", "2026-08-12")
        path = crawl_config.CRAWL_SOURCES_DIR / "nasa-a.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        raw["category"] = "eclipse"
        path.write_text(yaml.dump(raw), encoding="utf-8")

        response = client.post("/crawl-sources/nasa-a/edit", data={
            "category": "eclipse", "subject_slug": "sonnenfinsternis",
        }, follow_redirects=False)

        assert response.status_code == 303
        assert (service.DATA_ROOT / "astronomie" / "nasa-a" / "data.yaml").exists()

    def test_moving_a_source_drops_its_staged_candidates(self, client):
        """They name the page the source USED to write to, so leaving them
        would refill the queue with rows the new page already holds. staging/
        is gitignored and the next run rebuilds it."""
        self._source(client, "nasa-a", "eclipse", "nasa-a")
        self._approve(client, "nasa-a", "nasa-a", "eclipse", "2026-08-12")
        _stage_candidate("nasa-a", "20260724-000000", "nasa-a", _eclipse_event("2027-08-02"), category="eclipse")
        assert len(service._review_queue()) == 1

        client.post("/crawl-sources/nasa-a/edit", data={
            "category": "astronomie", "subject_slug": "nasa-a",
        }, follow_redirects=False)

        assert not (staging.STAGING_ROOT / "nasa-a").exists()
        assert service._review_queue() == []


class TestDeletePageReturnTo:
    """return_to is allowlisted against the pages that render the Delete
    button. The allowlist is easy to leave stale, and doing so fails
    invisibly - the delete still works, it just lands you somewhere else."""

    def _page(self, client):
        folder = service.DATA_ROOT / "astronomie" / "sonnenfinsternis"
        folder.mkdir(parents=True)
        (folder / "data.yaml").write_text(yaml.dump({"subject": {"slug": "sonnenfinsternis"}}), encoding="utf-8")
        (folder / "page.yaml").write_text(yaml.dump({"title": "Sonnenfinsternis"}), encoding="utf-8")
        return folder

    @pytest.mark.parametrize("return_to", ["/", "/crawl-sources", "/review"])
    def test_returns_to_the_page_the_delete_came_from(self, client, return_to):
        folder = self._page(client)

        response = client.post(
            "/pages/astronomie/sonnenfinsternis/delete",
            data={"return_to": return_to}, follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == return_to
        assert not folder.exists()

    @pytest.mark.parametrize("return_to", ["//evil.example", "/\\evil.example", "https://evil.example", "/../etc"])
    def test_falls_back_instead_of_following_an_open_redirect(self, client, return_to):
        self._page(client)

        response = client.post(
            "/pages/astronomie/sonnenfinsternis/delete",
            data={"return_to": return_to}, follow_redirects=False,
        )

        assert response.headers["location"] == "/crawl-sources"


class TestReviewDocument:
    """The whole-document review view: every pending date in one snapshot,
    each one rejectable in place. Reviewing a 200-row date table one page at
    a time loses what makes a table readable - its neighbours."""

    def _stage_md(self, source_id="test-source", run_ts="20260724-000000"):
        # HTML in, .md snapshot out - staging converts it (see
        # staging._extension_and_bytes), and .md is what the view renders.
        body = (
            "<html><body><p>Total Solar Eclipse of 1999 Aug 11</p>"
            "<p>Annular Eclipse of 2026-02-17</p><p>Nothing here</p></body></html>"
        )
        return staging.write_document(
            source_id, run_ts, "https://eclipse.invalid/SEcat5", "text/html", body.encode("utf-8"),
        )

    def _candidate(self, doc_hash, date, name="Sonnenfinsternis", source_id="test-source", run_ts="20260724-000000"):
        event = {"type": "event", "year": int(date[:4]), "from": date, "to": date, "precision": "exact", "ics": True, "name": name}
        candidate = staging.build_candidate(source_id, "sofi", event, doc_hash)
        staging.write_candidate(source_id, run_ts, candidate)
        return candidate

    def test_every_pending_date_becomes_a_selectable_checkbox(self, client):
        """Both spellings the source might use - the ISO string and the
        "1999 Aug 11" form the NASA catalog actually writes. The checkbox
        name/value match /review's table exactly, so both post to the same
        bulk route."""
        doc_hash = self._stage_md()
        iso = self._candidate(doc_hash, "2026-02-17")
        human = self._candidate(doc_hash, "1999-08-11")

        response = client.get(f"/review/test-source/document/{doc_hash}")

        assert response.status_code == 200
        for candidate in (iso, human):
            assert f'name="selected" value="test-source/{candidate["candidate_id"]}"' in response.text
        assert "<span>2026-02-17</span>" in response.text
        assert "<span>1999 Aug 11</span>" in response.text

    def test_each_date_links_to_its_own_page_for_editing(self, client):
        doc_hash = self._stage_md()
        candidate = self._candidate(doc_hash, "2026-02-17")

        response = client.get(f"/review/test-source/document/{doc_hash}")

        assert f'href="/review/test-source/{candidate["candidate_id"]}"' in response.text

    def test_the_page_offers_both_approve_and_reject_in_bulk(self, client):
        """The document view used to be reject-only, so approving meant going
        back to a separate table that had no document context."""
        doc_hash = self._stage_md()
        self._candidate(doc_hash, "2026-02-17")

        response = client.get(f"/review/test-source/document/{doc_hash}")

        assert 'action="/review/bulk-edit"' in response.text
        assert 'name="action" value="approve"' in response.text
        assert 'name="action" value="reject"' in response.text
        assert any(f'<option value="{v}">' in response.text for v in service.LICENSE_VALUES)

    def test_each_date_can_be_rejected_on_the_spot(self, client):
        """A per-date reject inside the bulk form - HTML forbids nesting a
        form, so the button re-points its own submit with formaction."""
        doc_hash = self._stage_md()
        candidate = self._candidate(doc_hash, "2026-02-17")

        response = client.get(f"/review/test-source/document/{doc_hash}")

        assert f'formaction="/review/test-source/{candidate["candidate_id"]}/reject"' in response.text
        assert "formnovalidate" in response.text

    def test_the_inline_reject_rejects_only_that_date_and_comes_back(self, client):
        """The whole form is submitted, so the other checked dates ride along
        in `selected` - the single-candidate route must ignore them and act
        on the one in its URL only."""
        doc_hash = self._stage_md()
        target = self._candidate(doc_hash, "2026-02-17")
        other = self._candidate(doc_hash, "1999-08-11")

        response = client.post(
            f"/review/test-source/{target['candidate_id']}/reject",
            data={
                "return_to": "document", "license": "",
                "selected": [f"test-source/{target['candidate_id']}", f"test-source/{other['candidate_id']}"],
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == f"/review/test-source/document/{doc_hash}"
        st = review_state.load("test-source")
        assert review_state.is_rejected(st, "sofi", target["event"])
        assert not review_state.is_rejected(st, "sofi", other["event"])
        assert [c["candidate_id"] for c in service._review_queue()] == [other["candidate_id"]]

    def test_bulk_approving_from_the_document_returns_to_it(self, client):
        doc_hash = self._stage_md()
        a = self._candidate(doc_hash, "2026-02-17")
        b = self._candidate(doc_hash, "1999-08-11")

        response = client.post("/review/bulk-edit", data={
            "selected": [f"test-source/{a['candidate_id']}", f"test-source/{b['candidate_id']}"],
            "license": "tos_checked", "action": "approve", "return_to": "document",
        }, follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["location"] == f"/review/test-source/document/{doc_hash}"
        assert service._review_queue() == []

    def test_a_date_with_no_pending_candidate_is_left_as_plain_text(self, client):
        doc_hash = self._stage_md()
        self._candidate(doc_hash, "2026-02-17")

        response = client.get(f"/review/test-source/document/{doc_hash}")

        assert "Nothing here" in response.text
        assert "<span>1999 Aug 11</span>" not in response.text

    def test_rejecting_in_the_document_returns_to_the_document(self, client):
        """The point of the view is staying in one place - the normal reject
        route jumps to the next queue item instead."""
        doc_hash = self._stage_md()
        candidate = self._candidate(doc_hash, "2026-02-17")

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/reject",
            data={"return_to": "document"}, follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["location"] == f"/review/test-source/document/{doc_hash}"
        assert review_state.is_rejected(review_state.load("test-source"), "sofi", candidate["event"])

    def test_a_rejected_date_stops_being_highlighted(self, client):
        doc_hash = self._stage_md()
        candidate = self._candidate(doc_hash, "2026-02-17")
        client.post(f"/review/test-source/{candidate['candidate_id']}/reject", data={"return_to": "document"})

        response = client.get(f"/review/test-source/document/{doc_hash}")

        assert 'class="date-hit"' not in response.text
        assert "2026-02-17" in response.text

    def test_rejecting_without_the_flag_still_chains_to_the_next_candidate(self, client):
        doc_hash = self._stage_md()
        candidate = self._candidate(doc_hash, "2026-02-17")
        self._candidate(doc_hash, "1999-08-11")

        response = client.post(
            f"/review/test-source/{candidate['candidate_id']}/reject", follow_redirects=False,
        )

        assert response.headers["location"].startswith("/review/test-source/test-source:")

    def test_404s_for_an_unknown_source(self, client):
        response = client.get("/review/does-not-exist/document/" + "a" * 16)
        assert response.status_code == 404

    def test_404s_for_a_malformed_document_hash(self, client):
        self._stage_md()
        response = client.get("/review/test-source/document/../../etc/passwd")
        assert response.status_code == 404


class TestNavigation:
    """The nav is the pipeline: add a Source, Review what it found, it lands
    in Pages. Harvest is a separate track and used to occupy the landing
    page, which put two unrelated concerns on one screen."""

    def test_the_landing_page_is_pages_not_harvest(self, client):
        response = client.get("/")

        assert response.status_code == 200
        assert "harvest-registry-table" not in response.text

    def test_harvest_has_its_own_page(self, client):
        response = client.get("/harvest")

        assert response.status_code == 200
        assert "harvest-registry-table" in response.text
        assert 'id="pages-table"' not in response.text

    @pytest.mark.parametrize("path", ["/", "/harvest", "/crawl-sources", "/review"])
    def test_every_page_renders_the_full_nav(self, client, path):
        response = client.get(path)

        assert response.status_code == 200
        for label in (">Pages<", ">Sources<", ">Review<", ">Harvest<"):
            assert label in response.text


class TestSuggestTags:
    """suggest_tags existed from the beginning with no caller - _all_tags()'s
    own docstring already claimed to feed it."""

    def _page(self, client, tags=None):
        folder = service.DATA_ROOT / "astronomie" / "sonnenfinsternis"
        folder.mkdir(parents=True)
        (folder / "page.yaml").write_text(yaml.dump({"title": "Sonnenfinsternis", "tags": tags or []}), encoding="utf-8")
        (folder / "data.yaml").write_text(
            yaml.dump({"subject": {"slug": "sonnenfinsternis"}, "windows": [_eclipse_event("2026-08-12")], "source": []}),
            encoding="utf-8",
        )

    def test_suggests_tags_and_writes_nothing(self, client, monkeypatch):
        """A suggestion fills the form field so it can be edited first - the
        route must not save anything by itself."""
        self._page(client)
        monkeypatch.setattr(service, "suggest_tags", lambda text, title, existing, **kw: ["astronomie", "himmel"])

        response = client.get("/pages/astronomie/sonnenfinsternis/suggest-tags")

        assert response.status_code == 200
        assert response.json() == {"tags": ["astronomie", "himmel"]}
        page = yaml.safe_load((service.DATA_ROOT / "astronomie" / "sonnenfinsternis" / "page.yaml").read_text())
        assert page["tags"] == []

    def test_the_existing_vocabulary_is_offered_for_reuse(self, client, monkeypatch):
        """Reuse over fragmentation ("feiertag" vs "feiertage") only works if
        the suggester is actually told what is already in use."""
        self._page(client, tags=["astronomie"])
        seen = {}
        monkeypatch.setattr(service, "suggest_tags", lambda text, title, existing, **kw: seen.setdefault("existing", existing) or [])

        client.get("/pages/astronomie/sonnenfinsternis/suggest-tags")

        assert "astronomie" in seen["existing"]

    def test_a_failed_suggestion_is_reported_not_silently_empty(self, client, monkeypatch):
        self._page(client)

        def _boom(*a, **k):
            raise service.ExtractionError("no API key")
        monkeypatch.setattr(service, "suggest_tags", _boom)

        response = client.get("/pages/astronomie/sonnenfinsternis/suggest-tags")

        assert response.status_code == 502
        assert "no API key" in response.json()["error"]

    def test_404s_for_an_unknown_page(self, client):
        assert client.get("/pages/astronomie/does-not-exist/suggest-tags").status_code == 404


class TestSuggestionLists:
    """Every <datalist> is rendered once by _base.html, so a form can't be
    added without them - which is exactly how the page-title and page-slug
    fields ended up with no suggestions while the category field beside them
    had some."""

    def _page(self, category, slug, title, tags=()):
        folder = service.DATA_ROOT / category / slug
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "page.yaml").write_text(yaml.dump({"title": title, "tags": list(tags)}), encoding="utf-8")
        (folder / "data.yaml").write_text(
            yaml.dump({"subject": {"slug": slug, "category": category}, "windows": [], "source": []}), encoding="utf-8")

    @pytest.mark.parametrize("path", ["/", "/harvest", "/crawl-sources", "/review"])
    def test_no_page_references_a_datalist_it_does_not_render(self, client, path):
        """The bug this class exists for: a `list="..."` pointing at an id
        that isn't on the page silently degrades to no suggestions at all."""
        text = client.get(path).text
        defined = set(re.findall(r'<datalist id="([^"]+)"', text))
        used = set(re.findall(r'list="([^"]+)"', text))

        assert used - defined == set()

    def test_an_existing_category_title_and_page_are_all_offered(self, client):
        """The user's case: with a Sonnenfinsternis page under Astronomie,
        adding Mondfinsternis should suggest all three."""
        self._page("astronomie", "sonnenfinsternis", "Sonnenfinsternis", tags=["himmel"])

        text = client.get("/crawl-sources").text

        assert '<option value="Astronomie">' in text
        assert '<option value="Sonnenfinsternis">' in text
        assert '<option value="sonnenfinsternis">' in text
        assert '<option value="himmel">' in text

    def test_the_page_field_offers_existing_slugs(self, client):
        """Typing an existing slug is how two sources aggregate onto one page
        (see CrawlSource.subject_slug), so it has to be discoverable rather
        than something you have to already know."""
        self._page("astronomie", "sonnenfinsternis", "Sonnenfinsternis")

        text = client.get("/crawl-sources").text

        assert 'name="subject_slug" list="page-suggestions"' in text
        assert 'name="subject_name" list="title-suggestions"' in text


class TestEditPageKeepsEveryCitation:
    """An aggregated page is the normal case - several sources, one page (see
    CrawlSource.subject_slug). Changing its license used to collapse the
    source list to its first entry, dropping citations that the page's own
    windows still referenced, which pageDataSchema's superRefine then failed
    the entire site build on."""

    def _aggregated_page(self):
        folder = service.DATA_ROOT / "astronomie" / "sonnenfinsternis"
        folder.mkdir(parents=True)
        (folder / "page.yaml").write_text(yaml.dump({"title": "Sonnenfinsternis", "tags": []}), encoding="utf-8")
        (folder / "data.yaml").write_text(yaml.dump({
            "subject": {"slug": "sonnenfinsternis", "category": "astronomie"},
            "windows": [
                {**_eclipse_event("2026-08-12"), "source_urls": ["https://a.invalid/cat"]},
                {**_eclipse_event("1999-08-11"), "source_urls": ["https://b.invalid/cat"]},
            ],
            "source": [
                {"url": "https://a.invalid/cat", "license": "tos_checked", "retrieved_at": "2026-07-25", "extraction": "llm"},
                {"url": "https://b.invalid/cat", "license": "tos_checked", "retrieved_at": "2026-07-25", "extraction": "llm"},
            ],
        }), encoding="utf-8")
        return folder

    def test_changing_the_license_keeps_every_source_and_restamps_them_all(self, client):
        folder = self._aggregated_page()

        response = client.post("/pages/astronomie/sonnenfinsternis/edit", data={
            "title": "Sonnenfinsternis", "category": "astronomie", "license": "official_par5",
        }, follow_redirects=False)

        assert response.status_code == 302
        datei = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
        assert [s["url"] for s in datei["source"]] == ["https://a.invalid/cat", "https://b.invalid/cat"]
        assert {s["license"] for s in datei["source"]} == {"official_par5"}

    def test_every_cited_url_still_has_a_source_entry_afterwards(self, client):
        """The exact invariant pageDataSchema's superRefine enforces - stated
        here so a regression fails in pytest rather than in `bun run build`."""
        folder = self._aggregated_page()

        client.post("/pages/astronomie/sonnenfinsternis/edit", data={
            "title": "Sonnenfinsternis", "category": "astronomie", "license": "official_par5",
        })

        datei = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))
        cited = {u for w in datei["windows"] for u in (w.get("source_urls") or [])}
        assert cited <= {s["url"] for s in datei["source"]}
