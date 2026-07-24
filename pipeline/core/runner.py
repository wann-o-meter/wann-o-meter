"""Orchestrates one source end to end: fetch -> extract -> validate -> merge
-> publish. This is the ONLY place that lifecycle lives. Two ways a source
can implement extract(): a sources/<id>.py adapter module (escape hatch for
genuinely bespoke logic, e.g. a Strategie-1 parser), or - the common case for
strategie: llm sources, and the only path schulferien_kmk uses now - no
Python at all: core/generic_source.py drives extraction purely from the
source's sources.yaml config (url, extraction_hint). strategie: llm_season
is the same idea for sources whose actual info is color-coded on an image/
PDF (e.g. a Saisonkalender) instead of literal text - see generic_source.
extract_season(). Run from within pipeline/:

    python -m core.runner schulferien_kmk --jahr 2028
"""

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

from core import generic_source, publish, store, validate
from core.extraction import ExtractionError
from core.fetch import fetch_bytes

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_YAML = Path(__file__).resolve().parent.parent / "sources.yaml"


def lade_quellen_config() -> Dict[str, Any]:
    with SOURCES_YAML.open() as f:
        return yaml.safe_load(f)


def parse_params(argv: List[str]) -> Dict[str, str]:
    """--key wert --key2 wert2 -> {"key": "wert", "key2": "wert2"}. Kein
    argparse-Schema pro Quelle noetig - jeder Adapter liest aus params, was
    er braucht, und meldet selbst, wenn etwas fehlt."""
    params: Dict[str, str] = {}
    it = iter(argv)
    for token in it:
        if not token.startswith("--"):
            raise ValueError(f"Unerwartetes Argument: {token}")
        key = token[2:].replace("-", "_")
        value = next(it, None)
        if value is None:
            raise ValueError(f"Fehlender Wert fuer --{token}")
        params[key] = value
    return params


def run(source_id: str, params: Dict[str, str]) -> int:
    quellen_config = lade_quellen_config()
    if source_id not in quellen_config:
        print(f"[runner] Unbekannte Quelle '{source_id}'. Bekannt: {', '.join(quellen_config)}", file=sys.stderr)
        return 1
    config = quellen_config[source_id]

    try:
        adapter = importlib.import_module(f"sources.{source_id}")
    except ModuleNotFoundError as e:
        if e.name != f"sources.{source_id}":
            raise
        adapter = None

    url = config["url"].format(**params)
    print(f"[runner] Fetching {url}", file=sys.stderr)
    raw, _ = fetch_bytes(url)

    print(f"[runner] Extrahiere ({source_id}) ...", file=sys.stderr)
    try:
        if adapter is not None:
            ergebnisse = [adapter.extract(raw, params)]
        elif config.get("strategie") == "llm":
            ergebnisse = generic_source.extract(config, raw, params)
        elif config.get("strategie") == "llm_season":
            ergebnisse = generic_source.extract_season(config, raw, params)
        else:
            print(
                f"[runner] Kein sources/{source_id}.py gefunden und strategie nicht llm/llm_season - "
                "kein generischer Fallback moeglich.",
                file=sys.stderr,
            )
            return 1
    except (NotImplementedError, ExtractionError) as e:
        print(f"[runner] Extraktion nicht verfuegbar: {e}", file=sys.stderr)
        return 1

    if not ergebnisse:
        print("[runner] Keine Subjekte gefunden - nichts zu schreiben.", file=sys.stderr)
        return 1

    print(
        f"[runner] {len(ergebnisse)} Subjekt(e) gefunden: "
        f"{', '.join(e.subjekt['slug'] for e in ergebnisse)}",
        file=sys.stderr,
    )

    # Phase 1: merge + validate every subject in-memory before writing
    # anything. One fetch/LLM call is now shared across all of a source's
    # subjects (unlike the old one-Bundesland-per-invocation flow), so
    # re-running over one bad subject is cheap - an all-or-nothing PR is
    # worth it to avoid ever publishing a partially-written run.
    print("[runner] Validiere gegen lib/pages-schema.ts ...", file=sys.stderr)
    vorbereitet = []
    for ergebnis in ergebnisse:
        datei = store.lade_oder_erstelle(
            ergebnis.datei_pfad,
            ergebnis.subjekt["slug"],
            ergebnis.subjekt["category"],
        )
        store.merge_zeitfenster(datei, ergebnis.zeitfenster, ergebnis.replace_key)
        store.append_quelle(datei, ergebnis.quelle)
        try:
            validate.pruefe_subjekt_datei(datei)
        except validate.ValidationError as e:
            print(
                f"[runner] Validierung fehlgeschlagen fuer Subjekt '{ergebnis.subjekt['slug']}', "
                f"KEIN PR:\n{e}",
                file=sys.stderr,
            )
            return 1
        vorbereitet.append((ergebnis, datei))

    # Phase 2: everything validated - write and publish together.
    dateien: List[Path] = []
    for ergebnis, datei in vorbereitet:
        store.speichere(ergebnis.datei_pfad, datei)
        page_pfad = ergebnis.datei_pfad.parent / "page.yaml"
        store.schreibe_page_yaml_falls_neu(page_pfad, ergebnis.subjekt["name"])
        print(f"[runner] Geschrieben: {ergebnis.datei_pfad}", file=sys.stderr)
        dateien += [ergebnis.datei_pfad, page_pfad]

    param_suffix = "-".join(params.values()).lower().replace(" ", "-")
    relativ = [d.relative_to(REPO_ROOT) for d in dateien]
    subjekte = ", ".join(ergebnis.subjekt["slug"] for ergebnis, _ in vorbereitet)
    publish.oeffne_pr(
        branch=f"pipeline/{source_id}-{param_suffix}",
        dateien=dateien,
        commit_message=f"pipeline: {source_id} ({', '.join(f'{k}={v}' for k, v in params.items())})",
        pr_titel=f"{source_id}: {', '.join(params.values())} ({len(vorbereitet)} Subjekt(e))",
        pr_body=(
            f"Automatisch vorgeschlagen von pipeline/core/runner.py (Quelle: {source_id}).\n"
            f"{len(vorbereitet)} Subjekt(e) gefunden: {subjekte}\n"
            "Geaenderte Dateien:\n" + "\n".join(f"- {r}" for r in relativ) + "\n\n"
            "Vor dem Merge pruefen: Daten plausibel, Quelle korrekt zitiert, Anzahl Subjekte "
            "wie erwartet (ein abgeschnittener LLM-Antwort kann Subjekte stillschweigend weglassen)?"
        ),
    )
    print("[runner] PR erstellt.", file=sys.stderr)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Nutzung: python -m core.runner <source_id> [--key wert ...]", file=sys.stderr)
        return 2
    source_id = sys.argv[1]
    try:
        params = parse_params(sys.argv[2:])
    except ValueError as e:
        print(f"[runner] {e}", file=sys.stderr)
        return 2
    return run(source_id, params)


if __name__ == "__main__":
    raise SystemExit(main())
