"""YAML data-file lifecycle: load-or-create, merge new zeitfenster in by
window_key, append the source's Quelle, save - matching the generic
data.yaml shape lib/pages-schema.ts's pageDataSchema validates (subject:
{slug, category}, source, windows). This is the part every source used to
reimplement slightly differently - now it's written once."""

from pathlib import Path
from typing import Any

import yaml

from core.content_hash import window_key


def load_or_create(path: Path, slug: str, category: str) -> dict[str, Any]:
    if path.exists():
        with path.open() as f:
            return yaml.safe_load(f)
    return {
        "subject": {"slug": slug, "category": category},
        "windows": [],
        "source": [],
    }


def merge_windows(file: dict[str, Any], neue_eintraege: list[dict[str, Any]]) -> None:
    """Merges neue_eintraege into file["windows"] by window_key: same key ->
    one entry with both citations, different key -> both kept.

    Two sources independently reporting the same window is the business model
    (many fragmented sources aggregated together), not a duplicate - so the
    citations union rather than one clobbering the other.

    There is no replace_key parameter anymore. It was strictly COARSER than
    the identity review already used, so "same window" and "already approved"
    could disagree - see core/content_hash.py's window_key for why that
    combination cannot terminate. its source config's per-source ("type", "year")
    override went with it: its stated job was keeping a --jahr 2029 run from
    overwriting 2026, and a key containing `from` cannot collide across years
    at all.

    ponytail: a source amending its own end date now lands a SECOND window
    instead of replacing the first - `to` is part of the key. That is only
    coherent because hand-editing data.yaml is a supported path now (see
    core/review_state.already_approved): delete the stale line and the next
    run leaves the correction alone. It is also what review always believed -
    the old content_hash included `to`, so an amended end date already came
    back as a fresh candidate."""
    by_key = {window_key(w): w for w in file["windows"]}
    for incoming in neue_eintraege:
        key = window_key(incoming)
        existing = by_key.get(key) or {}
        merged = dict(incoming)
        # Either side may lack source_urls entirely (windows predating the
        # field - see RawWindow.source_urls in lib/schema.ts).
        urls = list(dict.fromkeys((existing.get("source_urls") or []) + (incoming.get("source_urls") or [])))
        if urls:
            merged["source_urls"] = urls
        by_key[key] = merged
    file["windows"] = list(by_key.values())


def append_source(file: dict[str, Any], source: dict[str, Any]) -> None:
    """Appends source to the file's flat source list, deduped by URL - without
    this, re-running the same adapter against an unchanged URL grows the list
    with near-duplicate Source entries over time (same url, only retrieved_at
    ticking forward). A URL match replaces the prior entry instead of
    appending, so the freshest retrieved_at/license_note/confidence wins."""
    file["source"] = [s for s in file["source"] if s.get("url") != source.get("url")] + [source]


def speichere(path: Path, file: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(file, f, allow_unicode=True, sort_keys=False)


def schreibe_page_yaml_falls_neu(path: Path, title: str, tags: list[str] | None = None) -> None:
    """Same written-once convention as pipeline/review/service.py's POST /create-page:
    page.yaml carries title/description/tags and is left untouched by a later
    re-run, so a human's edits survive a re-scrape. Every data.yaml folder
    needs one (lib/pages.ts only recognizes a folder as a page when both
    page.yaml AND data.yaml are present)."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    page = {"title": title, "description": "", "tags": tags or []}
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(page, f, allow_unicode=True, sort_keys=False)
