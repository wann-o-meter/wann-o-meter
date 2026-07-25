"""Scoped, single-source crawl loop (Ziel 1/6 of the pipeline overhaul) -
replaces main.py's old cross-run SeedRun/focused_crawler machinery entirely.
One simple BFS per source (no generic frontier/multi-domain prioritization -
there never really was one to remove; the old crawler was already a
per-seed loop, just without an explicit scope/depth/robots concept), bounded
by CrawlSource's allowed_domains/path_prefix/max_depth, respecting
robots.txt and a per-domain rate limit.

Returns raw documents only (url, content_type, bytes) - this module has NO
notion of events or extraction (spec's crawl/extract split, see
core/staging.py and core/runner.py for what happens to a crawl's output)."""

import time
import urllib.robotparser
from typing import Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from core.crawl_config import CrawlSource
from core.fetch import Config, fetch_bytes
from core.url_normalize import normalize_url

USER_AGENT = "wann-crawler/1.0 (+https://github.com/am9zZWY/wann; contact: am9zzwy@gmail.com)"
MIN_SECONDS_BETWEEN_REQUESTS_PER_DOMAIN = 1.0


class CrawledDocument:
    def __init__(self, url: str, content_type: str, content: bytes):
        self.url = url
        self.content_type = content_type
        self.content = content

    def __repr__(self) -> str:
        return f"CrawledDocument(url={self.url!r}, content_type={self.content_type!r}, {len(self.content)} bytes)"


def _host_key(host: str) -> str:
    """"www.site.de" and "site.de" are the same host written two ways, and the
    two writers disagree here too: the create route derives allowed_domains
    from netloc.removeprefix("www.") while the seed URL keeps its "www.".
    ONLY the "www." prefix is stripped - anything looser (matching registrable
    domains, or allowing arbitrary subdomains) would turn this into a scope
    escape on what is the crawl's trust boundary."""
    return host.lower().removeprefix("www.")


def in_scope(url: str, source: CrawlSource) -> bool:
    """Compared per path SEGMENT, and tolerant of a trailing slash on either
    side, because the two are written by different code that disagreed:
    _derive_path_prefix (main.py) keeps the seed URL's trailing slash, while
    normalize_url strips it before the URL ever reaches here. A seed pasted
    from a browser ("https://site.de/faq/wann/") therefore scoped itself out
    of its OWN crawl - silently, since an out-of-scope URL is not reported -
    and the source ran to "0 docs, 0 candidates" forever.

    Fixed here rather than at the two writers so every config already on
    disk is repaired on read, without a migration."""
    parsed = urlparse(url)
    if _host_key(parsed.netloc) not in {_host_key(d) for d in source.allowed_domains}:
        return False
    # Optional[str]: a bare-domain seed stores no path_prefix at all, so this
    # is None rather than "" for every whole-site source.
    prefix = (source.path_prefix or "").rstrip("/")
    path = parsed.path.rstrip("/") or "/"
    # Segment-aware, so prefix "/events" no longer also swallows
    # "/events-archiv" - a different page, not a child of the scope.
    if prefix and path != prefix and not path.startswith(prefix + "/"):
        return False
    return True


def _looks_like_html(content: bytes, content_type: str) -> bool:
    return content[:15].lstrip().lower().startswith(b"<!doctype html") or content[:6].lower() == b"<html>" or "html" in content_type.lower()


def sniff_format(content: bytes, content_type: str) -> str:
    """Coarse format label for CrawlSource.formats filtering - "which
    document types does this source track", a scope concept (like
    allowed_domains), not extraction. Deliberately shallow: full content
    sniffing already lives in scraper.py's extract_any() dispatch, which
    runs later, on documents this function already decided are worth
    keeping."""
    if _looks_like_html(content, content_type):
        return "html"
    if content[:4] == b"%PDF":
        return "pdf"
    if content_type.lower() == "text/calendar" or content.lstrip().startswith(b"BEGIN:VCALENDAR"):
        return "ics"
    if content_type.lower().startswith("image/"):
        return "image"
    return "other"


class _RobotsCache:
    """One RobotFileParser per domain, fetched at most once per crawl -
    fails OPEN (allows) if robots.txt is unreachable, since an unreachable
    robots.txt is far more often a transient network hiccup or a site with
    no robots.txt at all than a deliberate block, and failing closed would
    silently kill an entire scoped crawl over that ambiguity."""

    def __init__(self, user_agent: str):
        self._user_agent = user_agent
        self._parsers: Dict[str, Optional[urllib.robotparser.RobotFileParser]] = {}

    def allowed(self, url: str) -> bool:
        domain = urlparse(url).netloc
        if domain not in self._parsers:
            parsed = urlparse(url)
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{parsed.scheme}://{domain}/robots.txt")
            try:
                rp.read()
            except Exception:
                rp = None
            self._parsers[domain] = rp
        rp = self._parsers[domain]
        return rp is None or rp.can_fetch(self._user_agent, url)


def _discover_links(html: bytes, base_url: str) -> Tuple[List[str], List[str]]:
    """Returns (page_links, ics_feed_links) - ics_feed_links come from
    <link type="text/calendar"> tags (spec: also look for ICS feeds
    advertised on HTML pages, not just linked-to .ics files)."""
    soup = BeautifulSoup(html, "html.parser")
    page_links = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)]
    ics_links = [
        urljoin(base_url, link["href"])
        for link in soup.find_all("link", attrs={"type": "text/calendar"})
        if link.get("href")
    ]
    return page_links, ics_links


def crawl(
    source: CrawlSource,
    on_progress: Optional[Callable[[str], None]] = None,
    on_page: Optional[Callable[[str, str], None]] = None,
) -> List[CrawledDocument]:
    """on_progress, if given, is called with a short status string before
    each actual fetch (politeness-delay wait doesn't count - that's dead
    time, not progress) - the BFS loop can run long on a source with many
    in-scope pages, and a caller (crawl_runner.run() -> main.py's
    dashboard) wants to show something better than a static "Crawling..."
    for however long that takes.

    on_page, if given, is called with (url, status) as each in-scope URL
    moves through the loop. Every way a URL can end up NOT in the returned
    documents gets its own status, because they're otherwise indistinguishable
    from "never seen" downstream: the returned list only carries survivors, so
    a robots block, a fetch error and a format filter all looked identical
    (silently absent) to anything reading the crawl's output. Out-of-scope
    URLs are deliberately NOT reported - every external link on every page
    hits that branch, which would bury the real rows."""
    documents: List[CrawledDocument] = []
    visited: Set[str] = set()
    queue: List[Tuple[str, int]] = [(normalize_url(source.seed_url), 0)]
    robots = _RobotsCache(USER_AGENT)
    last_fetch_at: Dict[str, float] = {}
    config = Config()
    config.user_agent = USER_AGENT
    fetched = 0

    def report_page(url: str, status: str) -> None:
        if on_page:
            on_page(url, status)

    while queue:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        if not in_scope(url, source):
            # Only the seed is worth a row: every external link on every page
            # hits this branch too (see the docstring), but a seed outside its
            # own scope is a misconfiguration that otherwise reports nothing
            # at all - which is exactly how it stayed invisible before.
            if depth == 0:
                report_page(url, "seed is outside this source's own allowed_domains/path_prefix")
            continue
        if not robots.allowed(url):
            report_page(url, "robots-blocked")
            continue

        domain = urlparse(url).netloc
        wait = MIN_SECONDS_BETWEEN_REQUESTS_PER_DOMAIN - (time.monotonic() - last_fetch_at.get(domain, 0.0))
        if wait > 0:
            time.sleep(wait)
        last_fetch_at[domain] = time.monotonic()

        if on_progress:
            on_progress(f"Fetching page {fetched + 1} ({len(queue)} queued): {url}")
        report_page(url, "fetching")
        try:
            content, content_type = fetch_bytes(url, config)
        except Exception as e:
            report_page(url, f"fetch failed: {str(e)[:80]}")
            continue
        fetched += 1

        fmt = sniff_format(content, content_type)
        is_html = fmt == "html"
        if fmt in source.formats:
            documents.append(CrawledDocument(url, content_type, content))
            report_page(url, "crawled")
        else:
            report_page(url, f"skipped - format '{fmt}' not in {source.formats}")

        if depth >= source.max_depth:
            continue
        if not is_html:
            continue

        page_links, ics_links = _discover_links(content, url)
        for link in page_links + ics_links:
            normalized = normalize_url(link)
            if normalized not in visited and in_scope(normalized, source):
                queue.append((normalized, depth + 1))

    return documents
