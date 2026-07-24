"""Rewrites a source's data.yaml windows from its review-state decisions.

review-state IS the review history (see core/review_state.py) - every
approved/modified window is stored there with its target_file, so a data.yaml
that drifted out of sync with it (windows lost to a bad replace_key, a file
deleted by hand) can be rebuilt without re-crawling or re-reviewing anything.

    uv run --project pipeline python \
        pipeline/tools/rebuild_from_review_state.py eclipse-gsfc-nasa-gov

ponytail: the `source` list of each target file is left exactly as it is -
decisions don't record the Quelle, and the existing citations are already
right. A target file that doesn't exist yet is skipped rather than invented.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import approval, review_state, store, validate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def rebuild(source_id: str) -> None:
    decisions = review_state.load(source_id)["decisions"].values()
    by_file = defaultdict(list)
    for d in decisions:
        if d["status"] in ("approved", "modified") and d["target_file"]:
            by_file[d["target_file"]].append(d.get("corrected_event", d["event"]))

    if not by_file:
        sys.exit(f"No approved decisions in review-state/{source_id}.yaml")

    for target_file, events in sorted(by_file.items()):
        path = REPO_ROOT / target_file
        if not path.exists():
            print(f"skipped {target_file} (does not exist - approve once to create it)")
            continue
        datei = store.lade_oder_erstelle(path, path.parent.name, path.parent.parent.name)
        datei["windows"] = []
        store.merge_zeitfenster(datei, events, approval.DEFAULT_REPLACE_KEY)
        try:
            validate.pruefe_subjekt_datei(datei)
        except validate.ValidationError as e:
            sys.exit(f"{target_file} would be invalid, nothing written:\n{e}")
        store.speichere(path, datei)
        print(f"{target_file}: {len(events)} decisions -> {len(datei['windows'])} windows")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: rebuild_from_review_state.py <source_id>")
    rebuild(sys.argv[1])
