"""Generic LLM-driven multi-subject extraction engine. core/runner.py falls
back to this whenever a sources.yaml entry has strategie: llm/llm_season and
no sources/<id>.py module exists - i.e. the common case needs zero
per-source Python, only a sources.yaml entry (url, extraction_hint,
replace_key).

Turns one fetched page into however many ExtraktionsErgebnis the LLM
discovers subjects for (see core/extraction.py's extract_subjects) - this is
what replaces e.g. schulferien_kmk.py's per-Bundesland Python adapter,
invoked once per Bundesland by an external caller, with one run that
discovers all Bundeslaender from the one page that already lists them.

extract_season() below is the same idea for strategie: llm_season sources -
where the actual information is color/highlighting on an image or PDF (e.g.
a Saisonkalender chart) rather than literal text, and the result is a
year-less recurring month window (extract_season_windows), not a concrete
dated range (extract_subjects)."""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from core.extraction import ExtractionError, extract_season_windows, extract_subjects, type_slug_from_label
from core.fetch import decode_text
from core.types import ExtractionResult
from scraper import extract_any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"


def extract(config: Dict[str, Any], raw: bytes, params: Dict[str, Any]) -> List[ExtractionResult]:
    """config is the source's sources.yaml entry (kategorie, url, lizenz,
    extraction_hint, optional replace_key/license_note). `url` and
    `extraction_hint` are both `.format(**params)`'d, same templating
    sources.yaml's `url` already used before this module existed."""
    text = decode_text(raw)
    if not text:
        raise ExtractionError("Could not decode fetched content as text")

    kategorie = config["kategorie"]
    url = config["url"].format(**params)
    hint = config["extraction_hint"].format(**params)
    replace_key = tuple(config.get("replace_key", ["type"]))
    jahr = int(params["jahr"]) if "jahr" in params else date.today().year

    subjects = extract_subjects(text, hint)

    quelle_basis = {
        "url": url,
        "license": config["lizenz"],
        "retrieved_at": date.today().isoformat(),
        "extraction": "llm",
    }
    if "license_note" in config:
        quelle_basis["license_note"] = config["license_note"].format(**params)

    ergebnisse = []
    for entry in subjects:
        slug = entry["subject"]["slug"]
        zeitfenster = [
            {
                "type": type_slug_from_label(r["label"]),
                "year": jahr,
                "from": r["start"],
                "to": r["end"],
                "precision": "exact",
                "ics": False,
                "name": r["label"],
            }
            for r in entry["ranges"]
        ]
        ergebnisse.append(ExtractionResult(
            subjekt={"slug": slug, "name": entry["subject"]["name"], "category": kategorie},
            datei_pfad=DATA_ROOT / kategorie / slug / "data.yaml",
            zeitfenster=zeitfenster,
            quelle=dict(quelle_basis),
            replace_key=replace_key,
        ))
    return ergebnisse


def extract_season(config: Dict[str, Any], raw: bytes, params: Dict[str, Any]) -> List[ExtractionResult]:
    """Like extract() above, but for sources whose actual information is
    encoded as color/highlighting on an image or PDF page (e.g. a
    Saisonkalender chart marking each fruit's harvest months in different
    colors) rather than as literal text - reads clean_markdown_full from
    scraper.py's kind-dispatching extract_any (whose vision prompt already
    describes that highlighting explicitly, see scraper.py's VISION_PROMPT)
    instead of plain decode_text(raw), which would only see garbled binary
    for a PDF/image and never reach the LLM with anything useful.

    Produces year-less recurring month windows ({"year": None, "from":
    "--MM", "to": "--MM"} - materializes every year, see lib/schema.ts's
    rawWindowSchema and lib/materialization.ts), not the concrete-dated
    windows extract() above produces - the right shape for "in season
    May-August every year", which was never tied to one specific year."""
    kategorie = config["kategorie"]
    url = config["url"].format(**params)
    hint = config["extraction_hint"].format(**params)
    replace_key = tuple(config.get("replace_key", ["type"]))

    scraped = extract_any(url, raw)
    text = scraped.get("clean_markdown_full") or scraped.get("clean_markdown_preview", "")
    if not text.strip():
        reason = scraped.get("reason")
        raise ExtractionError(
            f"Fetched content has no usable text (kind={scraped.get('kind')})"
            + (f": {reason}" if reason else "")
        )

    subjects = extract_season_windows(text, hint)

    quelle_basis = {
        "url": url,
        "license": config["lizenz"],
        "retrieved_at": date.today().isoformat(),
        "extraction": "llm",
    }
    if "license_note" in config:
        quelle_basis["license_note"] = config["license_note"].format(**params)

    ergebnisse = []
    for entry in subjects:
        slug = entry["subject"]["slug"]
        zeitfenster = [
            {
                "type": w["type"],
                "year": None,
                "from": w["from"],
                "to": w["to"],
                "precision": "approximate",
                "ics": False,
                "name": w["name"],
            }
            for w in entry["windows"]
        ]
        ergebnisse.append(ExtractionResult(
            subjekt={"slug": slug, "name": entry["subject"]["name"], "category": kategorie},
            datei_pfad=DATA_ROOT / kategorie / slug / "data.yaml",
            zeitfenster=zeitfenster,
            quelle=dict(quelle_basis),
            replace_key=replace_key,
        ))
    return ergebnisse
