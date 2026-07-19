"""HTTP fetch with timeout/retry, shared by everything in /pipeline that
talks to the network: the admin dashboard's scraper.py, one-time tools/
scripts, and source adapters via the runner."""

import ssl
import time
from typing import Optional, Tuple
import urllib.request

import certifi

# Bundled CA list (certifi) instead of urlopen's default context, which
# relies on the OS/Python installation's own trust store - on macOS this is
# commonly empty/stale (python.org builds don't auto-populate it, uv-managed
# interpreters don't either), causing "unable to get local issuer
# certificate" on otherwise-valid HTTPS sites. certifi is already an
# installed dependency (pulled in by httpx), no new package needed.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class Config:
    user_agent: str = "Mozilla/5.0 (compatible; Wann-Plattform-Scraper/1.0)"
    timeout: int = 30
    max_retries: int = 3
    delay_between_requests: float = 0.5


def fetch_bytes(url: str, config: Optional[Config] = None) -> Tuple[bytes, str]:
    """Fetch a URL and return (raw_bytes, content_type_header). Raw bytes,
    not text - a ZIP or PDF force-decoded as UTF-8 becomes useless before
    we even get a chance to look at it."""
    if config is None:
        config = Config()
    headers = {"User-Agent": config.user_agent}
    for attempt in range(config.max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=config.timeout, context=_SSL_CONTEXT) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except Exception as e:
            if attempt == config.max_retries - 1:
                raise RuntimeError(f"Failed to fetch {url}: {e}") from e
            time.sleep(config.delay_between_requests * (attempt + 1))
    return b"", ""


def fetch(url: str, config: Optional[Config] = None) -> str:
    """Text convenience wrapper over fetch_bytes, for HTML/prose callers."""
    content, _ = fetch_bytes(url, config)
    return content.decode("utf-8", errors="replace")


def decode_text(content: bytes) -> Optional[str]:
    """Try UTF-8, then Latin-1 (common in older German government exports,
    e.g. DWD's station list). Returns None if it's genuinely binary."""
    for encoding in ("utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None
