import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import crawl_config, crawler  # noqa: E402
from core.crawl_config import CrawlConfigError, CrawlSource  # noqa: E402

FAKE_SITE = {
    "https://example.org/events": (
        b"<html><body>"
        b'<a href="/events/market">market</a>'
        b'<a href="/events/market/">market again, trailing slash</a>'
        b'<a href="/events/market#details">market, fragment</a>'
        b'<a href="https://other.org/steal-focus">off scope</a>'
        b'<a href="/blog/unrelated">off path prefix</a>'
        b"</body></html>",
        "text/html",
    ),
    "https://example.org/events/market": (
        b"<html><body>"
        b'<a href="/events/market/deep">one level deeper</a>'
        b"</body></html>",
        "text/html",
    ),
    "https://example.org/events/market/deep": (
        b"<html><body>"
        b'<a href="/events/market/deep/deeper">too deep</a>'
        b"</body></html>",
        "text/html",
    ),
    "https://example.org/events/market/deep/deeper": (b"<html><body>should never be fetched</body></html>", "text/html"),
    "https://other.org/steal-focus": (b"<html><body>off-domain, must not be fetched</body></html>", "text/html"),
    "https://example.org/blog/unrelated": (b"<html><body>off path_prefix, must not be fetched</body></html>", "text/html"),
}


def _source(**overrides):
    base: dict[str, Any] = dict(
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
    base.update(overrides)
    return CrawlSource(**base)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def fake_fetch_bytes(url, config=None):
        if url not in FAKE_SITE:
            raise RuntimeError(f"test tried to fetch un-fixtured URL: {url}")
        return FAKE_SITE[url]

    monkeypatch.setattr(crawler, "fetch_bytes", fake_fetch_bytes)
    monkeypatch.setattr(crawler._RobotsCache, "allowed", lambda self, url: True)
    monkeypatch.setattr(crawler, "MIN_SECONDS_BETWEEN_REQUESTS_PER_DOMAIN", 0)


def test_never_fetches_a_url_outside_allowed_domains():
    docs = crawler.crawl(_source())
    fetched_urls = {d.url for d in docs}
    assert not any("other.org" in u for u in fetched_urls)


def test_never_fetches_a_url_outside_the_path_prefix():
    docs = crawler.crawl(_source())
    fetched_urls = {d.url for d in docs}
    assert not any("/blog/" in u for u in fetched_urls)


def test_a_source_with_no_path_prefix_at_all_still_scopes_by_domain():
    """path_prefix is Optional[str] and is None - not "" - for every
    bare-domain seed, which is the common whole-site source."""
    source = _source(seed_url="https://example.org", path_prefix=None)
    assert crawler.in_scope("https://example.org/anything/deep", source)
    assert not crawler.in_scope("https://other.org/anything", source)


def test_a_www_seed_matches_the_www_less_domain_the_create_route_derives():
    """The create route stores netloc.removeprefix("www."), the seed keeps its
    "www." - so a bare-domain seed scoped itself out of its own crawl."""
    source = _source(seed_url="https://www.example.org", allowed_domains=["example.org"])
    assert crawler.in_scope("https://www.example.org/events", source)
    # ...and the other direction, for an operator who typed the www. form.
    assert crawler.in_scope(
        "https://example.org/events",
        _source(allowed_domains=["www.example.org"]),
    )


def test_host_matching_is_a_www_prefix_rule_and_not_a_substring_one():
    """The domain list is the crawl's trust boundary - stripping "www." must
    not turn into "any host that merely contains the allowed one"."""
    assert not crawler.in_scope("https://notexample.org/events", _source())
    assert not crawler.in_scope("https://example.org.attacker.com/events", _source())
    assert not crawler.in_scope("https://sub.example.org/events", _source())


def test_a_seed_url_with_a_trailing_slash_is_inside_its_own_scope():
    """_derive_path_prefix keeps the seed's trailing slash, normalize_url
    strips it - so a seed pasted from a browser scoped itself OUT of its own
    crawl and the source reported "0 docs" forever."""
    source = _source(seed_url="https://example.org/events/", path_prefix="/events/")
    assert crawler.in_scope("https://example.org/events", source)
    assert crawler.in_scope("https://example.org/events/2026", source)


def test_the_prefix_does_not_swallow_a_sibling_with_the_same_start():
    """"/events-archiv" is a different page, not a child of "/events"."""
    assert not crawler.in_scope("https://example.org/events-archiv", _source())


def test_a_seed_outside_its_own_scope_is_reported_rather_than_silent():
    reported = []
    crawler.crawl(
        _source(seed_url="https://example.org/blog/unrelated", path_prefix="/events"),
        on_page=lambda url, status: reported.append((url, status)),
    )
    assert reported and "seed is outside" in reported[0][1]


def test_never_fetches_past_max_depth():
    docs = crawler.crawl(_source(max_depth=2))
    fetched_urls = {d.url for d in docs}
    assert "https://example.org/events/market/deep/deeper" not in fetched_urls
    assert "https://example.org/events/market/deep" in fetched_urls


def test_max_depth_zero_only_fetches_the_seed():
    docs = crawler.crawl(_source(max_depth=0))
    assert [d.url for d in docs] == ["https://example.org/events"]


def test_normalization_collapses_trailing_slash_and_fragment_duplicates_to_one_fetch():
    docs = crawler.crawl(_source())
    market_hits = [d for d in docs if d.url == "https://example.org/events/market"]
    assert len(market_hits) == 1  # not 3, despite 3 differently-shaped links to it


def test_on_progress_is_called_once_per_actual_fetch_not_per_queued_link():
    messages = []
    docs = crawler.crawl(_source(max_depth=0), on_progress=messages.append)
    assert len(messages) == len(docs) == 1
    assert "https://example.org/events" in messages[0]


def test_formats_filter_excludes_documents_not_in_the_configured_list(monkeypatch):
    monkeypatch.setitem(FAKE_SITE, "https://example.org/events/flyer.pdf", (b"%PDF-1.4 fake", "application/pdf"))
    site_with_pdf = dict(FAKE_SITE)
    site_with_pdf["https://example.org/events"] = (
        FAKE_SITE["https://example.org/events"][0].replace(
            b"</body>", b'<a href="/events/flyer.pdf">flyer</a></body>'
        ),
        "text/html",
    )

    def fake_fetch_bytes(url, config=None):
        return site_with_pdf[url]

    monkeypatch.setattr(crawler, "fetch_bytes", fake_fetch_bytes)

    html_only = crawler.crawl(_source(formats=["html"]))
    assert not any(d.url.endswith(".pdf") for d in html_only)

    with_pdf = crawler.crawl(_source(formats=["html", "pdf"]))
    assert any(d.url.endswith(".pdf") for d in with_pdf)


class TestCrawlConfig:
    def test_loads_a_valid_source_config(self, tmp_path):
        (tmp_path / "test-source.yaml").write_text(
            yaml.dump({
                "id": "test-source",
                "seed_url": "https://example.org/events",
                "category": "veranstaltungen",
                "scope": {"allowed_domains": ["example.org"], "path_prefix": "/events"},
                "max_depth": 2,
                "formats": ["html", "pdf"],
                "event_type_hint": "Stadtfeste",
                "schedule": "yearly",
            }),
            encoding="utf-8",
        )
        source = crawl_config.load_crawl_source(tmp_path / "test-source.yaml")
        assert source.id == "test-source"
        assert source.allowed_domains == ["example.org"]
        assert source.max_depth == 2

    def test_rejects_max_depth_above_the_hard_cap(self, tmp_path):
        path = tmp_path / "test-source.yaml"
        path.write_text(
            yaml.dump({
                "id": "test-source",
                "seed_url": "https://example.org/events",
                "category": "veranstaltungen",
                "scope": {"allowed_domains": ["example.org"]},
                "max_depth": 10,
            }),
            encoding="utf-8",
        )
        with pytest.raises(CrawlConfigError, match="max_depth"):
            crawl_config.load_crawl_source(path)

    def test_rejects_missing_allowed_domains(self, tmp_path):
        path = tmp_path / "test-source.yaml"
        path.write_text(
            yaml.dump({"id": "test-source", "seed_url": "https://example.org/events", "category": "veranstaltungen", "scope": {}}),
            encoding="utf-8",
        )
        with pytest.raises(CrawlConfigError, match="allowed_domains"):
            crawl_config.load_crawl_source(path)

    def test_rejects_id_filename_mismatch(self, tmp_path):
        path = tmp_path / "wrong-name.yaml"
        path.write_text(
            yaml.dump({
                "id": "test-source",
                "seed_url": "https://example.org/events",
                "category": "veranstaltungen",
                "scope": {"allowed_domains": ["example.org"]},
            }),
            encoding="utf-8",
        )
        with pytest.raises(CrawlConfigError, match="does not match filename"):
            crawl_config.load_crawl_source(path)

    def test_load_all_returns_empty_dict_when_directory_is_missing(self, tmp_path):
        assert crawl_config.load_all_crawl_sources(tmp_path / "does-not-exist") == {}

    def test_load_all_loads_every_yaml_file_in_the_directory(self, tmp_path):
        for source_id in ("a", "b"):
            (tmp_path / f"{source_id}.yaml").write_text(
                yaml.dump({
                    "id": source_id,
                    "seed_url": "https://example.org/events",
                    "category": "veranstaltungen",
                    "scope": {"allowed_domains": ["example.org"]},
                }),
                encoding="utf-8",
            )
        sources = crawl_config.load_all_crawl_sources(tmp_path)
        assert set(sources) == {"a", "b"}
