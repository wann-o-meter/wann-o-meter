#!/usr/bin/env python3
"""One-time migration (Ziel 7 of the pipeline overhaul): backfills existing
data/*/*/data.yaml windows into review-state as already-approved, so the
first real run of a matching source after this overhaul doesn't re-queue
everything that was already hand-authored/previously accepted.

Usage (from within pipeline/):
    python -m tools.migrate_existing [--dry-run]

Source_id resolution (deliberately explicit, not guessed): a category maps
to a real source_id only via pipeline/config/migration_source_map.yaml (e.g.
schulferien -> schulferien_kmk, since data/schulferien/*/data.yaml's
source.url matches sources.yaml's schulferien_kmk entry exactly) - this
matters because content_hash is source_id-independent by design (see
core/content_hash.py), so migrated content is only recognized as "already
seen" by a FUTURE REAL run if it lives in that run's own
review-state/<source_id>.yaml file. Everything else (no confident mapping,
e.g. saisonkalender/urlaubsfenster/presets) gets a synthetic
legacy:<category>/<slug> review-state file per subject - honest about
provenance (never produced by any pipeline run) rather than guessing a
plausible-but-wrong source_id.

Caveat, not hidden: even with the correct mapping, a future real run
auto-recognizing a migrated window as already-approved requires the fresh
extraction to reproduce byte-identical normalized fields (same type slug,
same name string) as the hand-authored data - an LLM re-extraction that
phrases a window's name slightly differently will still requeue it as
"new" despite covering the same real-world dates. Expected, not a bug -
flag it to whoever reviews that first post-migration run, don't be
surprised by it."""

import argparse
import sys
from pathlib import Path
from typing import Dict, Iterator, Tuple

import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import content_hash as content_hash_module  # noqa: E402
from core import review_state  # noqa: E402

REPO_ROOT = PIPELINE_ROOT.parent
DATA_ROOT = REPO_ROOT / "data"
MIGRATION_SOURCE_MAP_PATH = PIPELINE_ROOT / "config" / "migration_source_map.yaml"

# Top-level data/ folders that are never a hand-authored page category -
# generator.ts-only categories (feiertage, urlaubsfenster) have no data.yaml
# at all, and presets/ uses a wholly different schema (presetSchema), not
# pageDataSchema - _iter_data_files() would simply find nothing under any of
# these anyway, this is just an explicit skip rather than relying on that.
_SKIP_TOP_LEVEL = {"presets", "feiertage", "urlaubsfenster"}


def load_source_map() -> Dict[str, str]:
    if not MIGRATION_SOURCE_MAP_PATH.exists():
        return {}
    return yaml.safe_load(MIGRATION_SOURCE_MAP_PATH.read_text(encoding="utf-8")) or {}


def iter_data_files(data_root: Path = DATA_ROOT) -> Iterator[Tuple[str, str, Path]]:
    """Yields (category, slug, data_yaml_path) for every
    data/{category}/{slug}/data.yaml - single-segment category only
    (existing hand-authored data has no nested categories)."""
    if not data_root.exists():
        return
    for category_dir in sorted(data_root.iterdir()):
        if not category_dir.is_dir() or category_dir.name in _SKIP_TOP_LEVEL:
            continue
        for slug_dir in sorted(category_dir.iterdir()):
            data_path = slug_dir / "data.yaml"
            if data_path.exists():
                yield category_dir.name, slug_dir.name, data_path


def migrate(data_root: Path = DATA_ROOT, dry_run: bool = False) -> Dict[str, int]:
    """Returns {source_id: count of newly-migrated windows} - callers (the
    CLI below, or tests) can inspect this without re-reading review-state."""
    source_map = load_source_map()
    states: Dict[str, dict] = {}
    counts: Dict[str, int] = {}

    for category, slug, data_path in iter_data_files(data_root):
        datei = yaml.safe_load(data_path.read_text(encoding="utf-8")) or {}
        windows = datei.get("windows") or []
        if not windows:
            continue

        source_id = source_map.get(category, f"legacy:{category}/{slug}")
        state = states.setdefault(source_id, review_state.load(source_id))

        # Repo-relative, not absolute - target_file gets committed inside
        # review-state/*.yaml, and an absolute path baked in at migration
        # time would be wrong (or just confusing) in any other checkout.
        relative_data_path = data_path.relative_to(data_root.parent)

        for window in windows:
            normalized = content_hash_module.normalize_event(window, slug)
            hash_ = content_hash_module.content_hash(normalized)
            if hash_ in state["decisions"]:
                continue  # already migrated (or already reviewed for real) - idempotent re-run
            review_state.record_decision(state, hash_, "approved", str(relative_data_path), window)
            counts[source_id] = counts.get(source_id, 0) + 1

    if not dry_run:
        for source_id, state in states.items():
            if counts.get(source_id):
                review_state.save(source_id, state)

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be migrated without writing anything.")
    args = parser.parse_args()

    counts = migrate(dry_run=args.dry_run)
    if not counts:
        print("[migrate] Nothing new to migrate.", file=sys.stderr)
        return 0
    for source_id, count in sorted(counts.items()):
        print(f"[migrate] {source_id}: {count} window(s) marked approved", file=sys.stderr)
    if args.dry_run:
        print("[migrate] --dry-run: nothing written", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
