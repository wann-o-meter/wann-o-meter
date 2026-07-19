"""YAML data-file lifecycle: load-or-create, merge new zeitfenster in by
replace_key, append the source's Quelle, save - matching the generic
data.yaml shape lib/pages-schema.ts's pageDataSchema validates (subject:
{slug, category}, source, windows). This is the part every source used to
reimplement slightly differently - now it's written once."""

from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


def lade_oder_erstelle(pfad: Path, slug: str, kategorie: str) -> Dict[str, Any]:
    if pfad.exists():
        with pfad.open() as f:
            return yaml.safe_load(f)
    return {
        "subject": {"slug": slug, "category": kategorie},
        "windows": [],
        "source": [],
    }


def _date_range(window: Dict[str, Any]) -> Tuple[Any, Any]:
    return (window.get("from"), window.get("to"))


def _merged_source_urls(existing: Dict[str, Any], incoming: Dict[str, Any]) -> List[str]:
    """Union of both windows' source_urls, deduped, order preserved (existing
    citations first). Either side may be missing source_urls entirely (legacy
    windows predating the field, see RawWindow.source_urls in lib/schema.ts)."""
    combined = (existing.get("source_urls") or []) + (incoming.get("source_urls") or [])
    return list(dict.fromkeys(combined))


def merge_zeitfenster(
    datei: Dict[str, Any],
    neue_eintraege: List[Dict[str, Any]],
    replace_key: Tuple[str, ...],
) -> None:
    """Merges neue_eintraege into datei["windows"] by replace_key, distinguishing
    two cases that used to be conflated (this is the crux of per-window source
    citation - see PLAN.md section 7: many fragmented sources aggregated
    together is the actual business model, one source clobbering another's
    citation on every re-run works against that):

    - Same replace_key AND the same effective date range (from/to) as an
      existing window: two runs describing the SAME real-world window - e.g.
      a second source independently reporting BW's 2028 summer holidays as
      the same 2028-07-27..2028-09-09 range. MERGE: keep one window entry,
      union source_urls (deduped) so both citations survive on it.
    - Same replace_key but a DIFFERENT date range: a correction or updated
      information (e.g. a re-run with revised dates, or a source amending
      its own earlier estimate). REPLACE as before - the previous entry is
      no longer accurate, keeping it around would be misleading, and its
      citation doesn't belong on a date range it didn't actually support.

    Only replace_key matching, without the date-range check, could not tell
    "two sources agree" apart from "a source corrected itself" - every
    re-run silently discarded the previous entry (and its citation), so a
    second source citing the same window could never merge into it.
    """

    def key_of(window: Dict[str, Any]) -> Tuple[Any, ...]:
        return tuple(window.get(k) for k in replace_key)

    existing_windows = datei["windows"]
    existing_by_key: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for w in existing_windows:
        existing_by_key.setdefault(key_of(w), []).append(w)

    result: List[Dict[str, Any]] = []

    for incoming in neue_eintraege:
        candidates = existing_by_key.get(key_of(incoming), [])
        exact_match = next(
            (w for w in candidates if _date_range(w) == _date_range(incoming)), None
        )
        if exact_match is not None:
            # Same window, (likely) a different source: merge citations.
            urls = _merged_source_urls(exact_match, incoming)
            merged = dict(incoming)
            if urls:
                merged["source_urls"] = urls
            result.append(merged)
        else:
            # No exact match for this replace_key (or the date range
            # differs, i.e. a correction): the new entry replaces whatever
            # shared its replace_key, same as the old behavior.
            result.append(incoming)

    handled_keys = {key_of(w) for w in neue_eintraege}
    untouched = [w for w in existing_windows if key_of(w) not in handled_keys]

    datei["windows"] = untouched + result


def append_quelle(datei: Dict[str, Any], quelle: Dict[str, Any]) -> None:
    """Appends quelle to the file's flat source list, deduped by URL - without
    this, re-running the same adapter against an unchanged URL grows the list
    with near-duplicate Source entries over time (same url, only retrieved_at
    ticking forward). A URL match replaces the prior entry instead of
    appending, so the freshest retrieved_at/license_note/confidence wins."""
    datei["source"] = [
        s for s in datei["source"] if s.get("url") != quelle.get("url")
    ] + [quelle]


def speichere(pfad: Path, datei: Dict[str, Any]) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("w", encoding="utf-8") as f:
        yaml.dump(datei, f, allow_unicode=True, sort_keys=False)


def schreibe_page_yaml_falls_neu(pfad: Path, title: str, tags: List[str] | None = None) -> None:
    """Same written-once convention as pipeline/main.py's POST /create-page:
    page.yaml carries title/description/tags and is left untouched by a later
    re-run, so a human's edits survive a re-scrape. Every data.yaml folder
    needs one (lib/pages.ts only recognizes a folder as a page when both
    page.yaml AND data.yaml are present)."""
    if pfad.exists():
        return
    pfad.parent.mkdir(parents=True, exist_ok=True)
    page = {"title": title, "description": "", "tags": tags or []}
    with pfad.open("w", encoding="utf-8") as f:
        yaml.dump(page, f, allow_unicode=True, sort_keys=False)
