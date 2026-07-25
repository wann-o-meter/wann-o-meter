import sys
from pathlib import Path

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import approval, consent, crawler  # noqa: E402
from core.crawl_config import CrawlSource  # noqa: E402

FAKE_SITE = {
    "https://example.org/events": (
        b'<html><body><a href="/events/market">market</a></body></html>',
        "text/html",
    ),
    "https://example.org/events/market": (b"<html><body>market</body></html>", "text/html"),
}


@pytest.fixture(autouse=True)
def _ledger_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(consent, "CONSENT_PATH", tmp_path / "consent.yaml")
    monkeypatch.setattr(consent, "OUTBOX_DIR", tmp_path / "outbox")
    monkeypatch.delenv("SMTP_HOST", raising=False)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def fake_fetch_bytes(url, config=None):
        if url not in FAKE_SITE:
            raise RuntimeError(f"test tried to fetch un-fixtured URL: {url}")
        return FAKE_SITE[url]

    monkeypatch.setattr(crawler, "fetch_bytes", fake_fetch_bytes)
    monkeypatch.setattr(crawler._RobotsCache, "allowed", lambda self, url: True)
    monkeypatch.setattr(crawler, "MIN_SECONDS_BETWEEN_REQUESTS_PER_DOMAIN", 0)


def _source():
    return CrawlSource(
        id="test-source",
        seed_url="https://example.org/events",
        category="veranstaltungen",
        allowed_domains=["example.org"],
        path_prefix="/events",
        max_depth=2,
        formats=["html"],
        event_type_hint="test",
        schedule="manual",
    )


def test_domain_normalization_treats_www_and_bare_host_as_one_decision():
    assert consent.normalize_domain("https://www.Example.org:8443/x") == "example.org"
    assert consent.normalize_domain("example.org") == "example.org"


def test_unknown_domains_are_not_blocked():
    assert not consent.is_denied("https://example.org/events")


def test_denied_domain_is_never_crawled_and_says_why():
    consent.set_status("example.org", "denied", note="copyright banner forbids AI use")
    statuses = []
    docs = crawler.crawl(_source(), on_page=lambda url, status: statuses.append((url, status)))
    assert docs == []
    assert ("https://example.org/events", "consent-denied") in statuses


def test_granted_and_pending_domains_still_crawl():
    for status in ("granted", "pending", "unknown"):
        consent.set_status("example.org", status)
        assert crawler.crawl(_source()), f"{status} must not block the crawl"


def test_approval_refuses_to_write_a_denied_domain(tmp_path, monkeypatch):
    monkeypatch.setattr(approval, "DATA_ROOT", tmp_path / "data")
    consent.set_status("example.org", "denied")
    event = {"type": "test", "year": 2027, "from": "2027-05-01", "to": "2027-05-02",
             "precision": "exact", "ics": True}
    quelle = {"url": "https://example.org/events", "license": "tos_checked",
              "retrieved_at": "2027-01-01", "extraction": "llm"}
    with pytest.raises(approval.ApprovalError, match="not consented"):
        approval.write_event("veranstaltungen", "markt", "Markt", event, quelle)
    assert not (tmp_path / "data").exists()


def test_history_records_every_decision():
    consent.set_status("example.org", "pending", contact_email="info@example.org")
    consent.set_status("example.org", "granted", note="said yes by email")
    record = consent.get("example.org")
    assert record["status"] == "granted"
    assert record["contact_email"] == "info@example.org"
    assert [entry["status"] for entry in record["history"]] == ["pending", "granted"]
    assert record["requested_at"] and record["responded_at"]


def test_request_without_smtp_writes_a_draft_and_marks_pending():
    message = consent.send_request("example.org", "info@example.org")
    assert "not sent" in message
    drafts = list((consent.OUTBOX_DIR).glob("example.org-*.eml"))
    assert len(drafts) == 1
    body = drafts[0].read_text(encoding="utf-8")
    assert "example.org" in body and "Zustimmung" in body
    assert consent.status("example.org") == "pending"


def test_a_denied_domain_also_blocks_its_subdomains():
    consent.set_status("example.org", "denied")
    assert consent.is_denied("https://events.example.org/kirmes")
    assert consent.get("events.example.org")["inherited_from"] == "example.org"
    # ...but not a different site that merely ends the same way
    assert not consent.is_denied("https://notexample.org/x")


def test_a_subdomain_can_override_its_parent():
    consent.set_status("example.org", "denied")
    consent.set_status("events.example.org", "granted")
    assert not consent.is_denied("https://events.example.org/kirmes")
    assert consent.is_denied("https://other.example.org/x")


def test_recording_a_new_decision_clears_the_old_note():
    consent.set_status("example.org", "denied", note="banner forbids it")
    consent.set_status("example.org", "granted", note="")
    assert consent.get("example.org")["note"] == ""
    assert "banner forbids it" in str(consent.get("example.org")["history"])


def test_pages_already_citing_a_domain_are_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(consent, "DATA_ROOT", tmp_path)
    (tmp_path / "veranstaltungen" / "markt").mkdir(parents=True)
    (tmp_path / "veranstaltungen" / "markt" / "data.yaml").write_text(
        "subject: {slug: markt, category: veranstaltungen}\n"
        "windows:\n  - {type: markt, source_urls: ['https://www.example.org/events']}\n"
        "source:\n  - {url: 'https://elsewhere.test/x'}\n",
        encoding="utf-8",
    )
    # Legacy shape: `source` as a bare object, still on disk across
    # data/saisonkalender - iterating it yields keys, not sources.
    (tmp_path / "saisonkalender" / "apfel").mkdir(parents=True)
    (tmp_path / "saisonkalender" / "apfel" / "data.yaml").write_text(
        "subject: {slug: apfel, category: saisonkalender}\n"
        "windows: []\n"
        "source: {url: 'https://old.example.org/a', license: dl_de_by}\n",
        encoding="utf-8",
    )
    assert consent.pages_citing("example.org") == ["saisonkalender/apfel", "veranstaltungen/markt"]
    assert consent.pages_citing("unrelated.test") == []


def test_a_denied_domain_is_not_even_fetched_to_find_a_contact(monkeypatch):
    consent.set_status("example.org", "denied")
    monkeypatch.setattr("core.fetch.fetch_bytes", lambda *a, **k: pytest.fail("must not fetch a denied domain"))
    assert consent.find_contact("https://example.org") is None


def test_request_rejects_a_non_address():
    with pytest.raises(consent.ConsentError):
        consent.send_request("example.org", "not-an-email")
