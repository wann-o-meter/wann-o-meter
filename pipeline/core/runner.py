"""Orchestrates one source end to end: fetch -> extract -> stage -> diff
against review-state -> write auto-approved/modified candidates to data/,
queue the rest for human review. This is the ONLY place that lifecycle
lives. Two ways a source can implement extract(): a sources/<id>.py adapter
module (escape hatch for genuinely bespoke logic, e.g. a Strategie-1
parser), or - the common case for strategie: llm sources, and the only path
schulferien_kmk uses now - no Python at all: core/generic_source.py drives
extraction purely from the source's data/_sources/ config (url,
extraction_hint). strategie: llm_season is the same idea for sources whose
actual info is color-coded on an image/PDF (e.g. a Saisonkalender) instead
of literal text - see generic_source.extract_season(). Run from within
pipeline/:

    python -m core.runner schulferien_kmk --jahr 2028

No PR is opened anymore (core/publish.py is retired) - approved/modified
candidates are written straight to data/ via core/approval.py, same as any
other locally-produced change; a human commits/pushes/opens a PR themselves.
Everything not already reviewed lands in pipeline/staging/ for the review
UI (main.py's /review routes) instead.
"""

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from core import approval, generic_source, review_state, staging
from core.extraction import ExtractionError
from core.fetch import fetch_bytes

SOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "_sources"


def lade_quellen_config() -> Dict[str, Any]:
    """Every `kind: batch` file in data/_sources/, keyed by source id. Was a
    single pipeline/sources.yaml registry; one file per source instead means
    a new source is a new file rather than an edit to a shared one, and puts
    it in the same directory as the crawler's sources, which answer the same
    question. Files with no `kind` are crawler sources (core/crawl_config.py)
    and are skipped here."""
    sources: Dict[str, Any] = {}
    if not SOURCES_DIR.exists():
        return sources
    for path in sorted(SOURCES_DIR.glob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if raw.get("kind") != "batch":
            continue
        sources[raw.get("id", path.stem)] = raw
    return sources


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
    raw, content_type = fetch_bytes(url)

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    doc_hash = staging.write_document(source_id, run_ts, url, content_type, raw)

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

    # Flatten each subject's zeitfenster (possibly several independently-
    # reviewable windows, e.g. Osterferien + Sommerferien) into one staged
    # candidate per window - review is per-event, not per-subject/run.
    extracted_at = datetime.now(timezone.utc).isoformat()
    candidates_by_subject: Dict[str, List[Dict[str, Any]]] = {}
    subjects_by_slug = {}
    for ergebnis in ergebnisse:
        slug = ergebnis.subjekt["slug"]
        subjects_by_slug[slug] = ergebnis
        for window in ergebnis.zeitfenster:
            candidate = staging.build_candidate(source_id, slug, window, doc_hash, extracted_at)
            staging.write_candidate(source_id, run_ts, candidate)
            candidates_by_subject.setdefault(slug, []).append(candidate)

    state = review_state.load(source_id)
    # One run emits many subjects (Schulferien: one per Bundesland), and each
    # is its own page - so the already-approved lookup runs per subject.
    auto_waved_through, needs_review = [], []
    for slug, candidates in candidates_by_subject.items():
        ergebnis = subjects_by_slug[slug]
        waved, pending = review_state.diff(
            candidates, state, ergebnis.subjekt["category"], slug
        )
        auto_waved_through.extend(waved)
        needs_review.extend(pending)

    for candidate in auto_waved_through:
        ergebnis = subjects_by_slug[candidate["subject_slug"]]
        try:
            approval.write_event(
                ergebnis.subjekt["category"],
                ergebnis.subjekt["slug"],
                ergebnis.subjekt["name"],
                candidate["event"],
                ergebnis.quelle,
            )
        except approval.ApprovalError as e:
            print(f"[runner] Re-Verifikation fehlgeschlagen fuer {candidate['candidate_id']}: {e}", file=sys.stderr)
            continue

    review_state.save(source_id, state)

    print(
        f"[runner] {len(auto_waved_through)} bereits reviewt (durchgewunken), "
        f"{len(needs_review)} neu zur Review.",
        file=sys.stderr,
    )
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
