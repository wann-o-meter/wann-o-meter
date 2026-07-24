"""Staging area between fetching and the reviewed data/ folder - shared by
BOTH the scoped crawler (core/crawler.py) and the automated batch pipeline
(core/runner.py), so the review UI (main.py) can render "candidate next to
its source snapshot" identically regardless of which subsystem produced it.

Layout (matches the spec, lives under pipeline/ alongside the other
pipeline-internal working directories - scraped/, crawler_state/ - rather
than repo-root data/, which is reserved for published, Astro-consumed
output):

    pipeline/staging/<source_id>/<run_ts>/documents/<doc_hash>.md|.pdf|...
    pipeline/staging/<source_id>/<run_ts>/documents/<doc_hash>.meta.yaml
    pipeline/staging/<source_id>/<run_ts>/candidates/<candidate_id>.yaml

doc_hash is content-addressed (sha256 of the raw fetched bytes, not the URL)
so a snapshot stays stable and re-referenceable by the review UI even if the
source page later changes or disappears entirely - re-fetching identical
content (e.g. two URLs serving the same PDF) also naturally dedupes to one
file within a run.
"""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.content_hash import content_hash as _content_hash_of
from core.content_hash import normalize_event
from core.fetch import decode_text
from scraper import html_to_markdown, sniff_image_mime

STAGING_ROOT = Path(__file__).resolve().parent.parent / "staging"

_IMAGE_EXTENSIONS = {"image/gif": ".gif", "image/png": ".png", "image/jpeg": ".jpg"}


def _looks_like_html(content: bytes, content_type: str) -> bool:
    return bool(re.match(rb"\s*<(!doctype html|html)", content, re.IGNORECASE)) or "html" in content_type.lower()


def _extension_and_bytes(content: bytes, content_type: str) -> tuple[str, bytes]:
    """Decides the stored representation: HTML is rendered to Markdown (a
    human-reviewable snapshot, not raw markup with its CSS/JS baggage) -
    pure format conversion via scraper.py's existing html_to_markdown, not
    "extraction" (finding events/dates), so this doesn't blur the crawler/
    extraction boundary the spec draws. Everything else is stored as its
    original bytes, already directly viewable (PDF/image) or small/textual
    enough not to need conversion (ICS)."""
    if content[:4] == b"%PDF":
        return ".pdf", content
    image_mime = sniff_image_mime(content)
    if image_mime:
        return _IMAGE_EXTENSIONS.get(image_mime, ".bin"), content
    if content_type.lower() == "text/calendar" or content.lstrip().startswith(b"BEGIN:VCALENDAR"):
        return ".ics", content
    if _looks_like_html(content, content_type):
        text = decode_text(content) or ""
        return ".md", html_to_markdown(text).encode("utf-8")
    return ".bin", content


def _run_dir(source_id: str, run_ts: str) -> Path:
    return STAGING_ROOT / source_id / run_ts


def write_document(source_id: str, run_ts: str, url: str, content_type: str, raw: bytes) -> str:
    """Writes one fetched document's snapshot + metadata, returns its
    doc_hash for a candidate to reference."""
    doc_hash = hashlib.sha256(raw).hexdigest()[:16]
    documents_dir = _run_dir(source_id, run_ts) / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)

    ext, stored_bytes = _extension_and_bytes(raw, content_type)
    (documents_dir / f"{doc_hash}{ext}").write_bytes(stored_bytes)

    meta = {
        "doc_hash": doc_hash,
        "url": url,
        "content_type": content_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stored_as": f"{doc_hash}{ext}",
    }
    with (documents_dir / f"{doc_hash}.meta.yaml").open("w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, sort_keys=False)

    return doc_hash


def build_candidate(
    source_id: str,
    subject_slug: str,
    window: Dict[str, Any],
    document: str,
    extracted_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds one candidate dict (spec shape: candidate_id, source_id,
    document, extracted_at, content_hash, event) for a single window - the
    unit of review is one event, not one subject/ExtractionResult, since a
    subject can carry several independently-sourced windows (see
    data/schulferien/bw/data.yaml's Osterferien + Sommerferien)."""
    hash_ = _content_hash_of(normalize_event(window, subject_slug))
    return {
        "candidate_id": f"{source_id}:{hash_}",
        "source_id": source_id,
        "subject_slug": subject_slug,
        "document": document,
        "extracted_at": extracted_at or datetime.now(timezone.utc).isoformat(),
        "content_hash": hash_,
        "event": window,
    }


def write_candidate(source_id: str, run_ts: str, candidate: Dict[str, Any]) -> Path:
    candidates_dir = _run_dir(source_id, run_ts) / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    path = candidates_dir / f"{candidate['candidate_id'].replace(':', '_')}.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(candidate, f, allow_unicode=True, sort_keys=False)
    return path


def read_document_meta(source_id: str, run_ts: str, doc_hash: str) -> Dict[str, Any]:
    meta_path = _run_dir(source_id, run_ts) / "documents" / f"{doc_hash}.meta.yaml"
    return yaml.safe_load(meta_path.read_text(encoding="utf-8"))


def list_documents(source_id: str, run_ts: str) -> List[Dict[str, Any]]:
    """Every document's metadata for one run, sorted by url - used by the
    Crawl Sources dashboard's page-tree view (main.py) to show what a crawl
    actually reached, hierarchically under the seed URL."""
    documents_dir = _run_dir(source_id, run_ts) / "documents"
    if not documents_dir.exists():
        return []
    metas = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in documents_dir.glob("*.meta.yaml")]
    return sorted(metas, key=lambda m: m["url"])
