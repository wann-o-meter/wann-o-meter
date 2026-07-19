"""Generic LLM-driven multi-subject extraction engine. core/runner.py falls
back to this whenever a sources.yaml entry has strategie: llm and no
sources/<id>.py module exists - i.e. the common case needs zero per-source
Python, only a sources.yaml entry (url, extraction_hint, replace_key).

Turns one fetched page into however many ExtraktionsErgebnis the LLM
discovers subjects for (see core/extraction.py's extract_subjects) - this is
what replaces e.g. schulferien_kmk.py's per-Bundesland Python adapter,
invoked once per Bundesland by an external caller, with one run that
discovers all Bundeslaender from the one page that already lists them."""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from core.extraction import ExtractionError, extract_subjects, type_slug_from_label
from core.fetch import decode_text
from core.types import ExtractionResult

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
