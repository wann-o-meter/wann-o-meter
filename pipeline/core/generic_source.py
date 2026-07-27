"""Generic LLM-driven multi-subject extraction engine. core/runner.py falls
back to this whenever a data/_sources/ entry has strategy: llm/llm_season and
no sources/<id>.py module exists - i.e. the common case needs zero
per-source Python, only a data/_sources/ entry (url, extraction_hint,
window_key).

Turns one fetched page into however many ExtraktionsErgebnis the LLM
discovers subjects for (see core/extraction.py's extract_subjects) - this is
what replaces e.g. schulferien_kmk.py's per-Bundesland Python adapter,
invoked once per Bundesland by an external caller, with one run that
discovers all Bundeslaender from the one page that already lists them.

extract_season() below is the same idea for strategy: llm_season sources -
where the actual information is color/highlighting on an image or PDF (e.g.
a Saisonkalender chart) rather than literal text, and the result is a
year-less recurring month window (extract_season_windows), not a concrete
dated range (extract_subjects)."""

from datetime import date
from pathlib import Path
from typing import Any

from core.extraction import ExtractionError, extract_season_windows, extract_subjects, type_slug_from_label
from core.fetch import decode_text
from core.sniff import extract_any
from core.types import ExtractionResult

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"


def template_params(params: dict[str, Any]) -> dict[str, Any]:
    """`jahr` defaults to the current year: a config template referencing it
    must not make the parameter mandatory, and .format() raises KeyError on a
    missing placeholder rather than leaving it blank."""
    return {"jahr": date.today().year, **params}


def extract(config: dict[str, Any], raw: bytes, params: dict[str, Any]) -> list[ExtractionResult]:
    """config is the source's data/_sources/ entry (category, url, license,
    extraction_hint, optional license_note). `url` and
    `extraction_hint` are both `.format(**params)`'d, same templating
    its source config's `url` already used before this module existed."""
    text = decode_text(raw)
    if not text:
        raise ExtractionError("Could not decode fetched content as text")

    category = config["category"]
    url = config["url"].format(**template_params(params))
    hint = config["extraction_hint"].format(**template_params(params))

    subjects = extract_subjects(text, hint)

    source_basis = {
        "url": url,
        "license": config["license"],
        "retrieved_at": date.today().isoformat(),
        "extraction": "llm",
    }
    if "license_note" in config:
        source_basis["license_note"] = config["license_note"].format(**template_params(params))

    ergebnisse = []
    for entry in subjects:
        slug = entry["subject"]["slug"]
        zeitfenster = [
            {
                "type": type_slug_from_label(r["label"]),
                # From the date, not from --jahr: a school year spans two
                # calendar years, so the parameter cannot describe both ends
                # and stamping it produced windows reading year: 2028 next to
                # from: 2026-11-02. _validate_ranges guarantees YYYY-MM-DD.
                "year": int(r["start"][:4]),
                "from": r["start"],
                "to": r["end"],
                "precision": "exact",
                "ics": False,
                "name": r["label"],
            }
            for r in entry["ranges"]
        ]
        ergebnisse.append(
            ExtractionResult(
                subject={"slug": slug, "name": entry["subject"]["name"], "category": category},
                file_path=DATA_ROOT / category / slug / "data.yaml",
                zeitfenster=zeitfenster,
                source=dict(source_basis),
            )
        )
    return ergebnisse


def extract_season(config: dict[str, Any], raw: bytes, params: dict[str, Any]) -> list[ExtractionResult]:
    """Like extract() above, but for sources whose actual information is
    encoded as color/highlighting on an image or PDF page (e.g. a
    Saisonkalender chart marking each fruit's harvest months in different
    colors) rather than as literal text - reads clean_markdown_full from
    core/sniff.py's kind-dispatching extract_any (whose vision prompt already
    describes that highlighting explicitly, see core/sniff.py's VISION_PROMPT)
    instead of plain decode_text(raw), which would only see garbled binary
    for a PDF/image and never reach the LLM with anything useful.

    Produces year-less recurring month windows ({"year": None, "from":
    "--MM", "to": "--MM"} - materializes every year, see lib/schema.ts's
    rawWindowSchema and lib/materialization.ts), not the concrete-dated
    windows extract() above produces - the right shape for "in season
    May-August every year", which was never tied to one specific year."""
    category = config["category"]
    url = config["url"].format(**template_params(params))
    hint = config["extraction_hint"].format(**template_params(params))

    scraped = extract_any(url, raw)
    text = scraped.get("clean_markdown_full") or scraped.get("clean_markdown_preview", "")
    if not text.strip():
        reason = scraped.get("reason")
        raise ExtractionError(
            f"Fetched content has no usable text (kind={scraped.get('kind')})" + (f": {reason}" if reason else "")
        )

    subjects = extract_season_windows(text, hint)

    source_basis = {
        "url": url,
        "license": config["license"],
        "retrieved_at": date.today().isoformat(),
        "extraction": "llm",
    }
    if "license_note" in config:
        source_basis["license_note"] = config["license_note"].format(**template_params(params))

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
        ergebnisse.append(
            ExtractionResult(
                subject={"slug": slug, "name": entry["subject"]["name"], "category": category},
                file_path=DATA_ROOT / category / slug / "data.yaml",
                zeitfenster=zeitfenster,
                source=dict(source_basis),
            )
        )
    return ergebnisse
