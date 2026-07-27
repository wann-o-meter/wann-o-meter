"""URL normalization for the scoped crawler's dedup (core/crawler.py) - two
URLs that are really the same page (differing only by fragment, trailing
slash, tracking params, or query-param order) must collapse to one canonical
string, or the crawler queues/visits the same content under N different
URLs and never converges."""

from urllib.parse import parse_qsl, urldefrag, urlencode, urlparse, urlunparse

_TRACKING_PREFIXES = ("utm_",)


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    query_pairs = sorted(
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES)
    )

    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            urlencode(query_pairs),
            "",  # fragment already stripped
        )
    )
