"""Validates a data.yaml dict against the SAME Zod schema the Astro build
uses (pageDataSchema, lib/pages-schema.ts). No JSON-Schema export:
zod-to-json-schema was tried first (as suggested) and is empirically broken
under Zod v4 - even a trivial schema exports to `{}`, which would validate
anything and silently defeat the whole point. Shelling out to a tiny Bun
script that imports the real Zod object has zero drift risk instead, at the
cost of one subprocess call."""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VALIDATE_SCRIPT = REPO_ROOT / "lib" / "validate-cli.ts"


class ValidationError(Exception):
    pass


def pruefe_subjekt_datei(datei: Dict[str, Any]) -> None:
    """Raises ValidationError with the Zod issue list if `datei` doesn't
    match pageDataSchema. Call this BEFORE opening a PR, not after the
    Astro build fails on it."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(datei, f)
        temp_pfad = f.name

    try:
        result = subprocess.run(
            ["bun", "run", str(VALIDATE_SCRIPT), temp_pfad],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    finally:
        Path(temp_pfad).unlink(missing_ok=True)

    if result.returncode != 0:
        raise ValidationError(result.stderr.strip() or result.stdout.strip() or "Validierung fehlgeschlagen")
