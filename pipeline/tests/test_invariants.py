"""The structural rules the data/pipeline split rests on. They are cheap to
check and expensive to notice by eye - every one of them held at some point
and then quietly stopped holding, which is how source config ended up spread
over four directories in the first place.

Kept as tests rather than prose in a README because a README cannot fail.
"""

import ast
import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_ROOT.parent
DATA_ROOT = REPO_ROOT / "data"
SOURCES_DIR = DATA_ROOT / "_sources"

sys.path.insert(0, str(PIPELINE_ROOT))

try:  # tomllib is stdlib from 3.11; the pipeline pins 3.10
    import tomllib  # ty: ignore[unresolved-import]
except ModuleNotFoundError:  # pragma: no cover - depends on interpreter
    import tomli as tomllib


def _subject_folders():
    """A subject folder is one holding a data.yaml - the same structural test
    lib/pages.ts's walk applies (page.yaml + data.yaml means "page", not
    "category node")."""
    return sorted(p.parent for p in DATA_ROOT.glob("**/data.yaml"))


# --- Invariant 1: every subject folder describes itself -------------------

def test_every_subject_folder_has_exactly_one_meta_toml():
    missing = [
        str(folder.relative_to(REPO_ROOT))
        for folder in _subject_folders()
        if not (folder / "meta.toml").is_file()
    ]
    assert missing == [], f"subject folders without a meta.toml: {missing}"


@pytest.mark.parametrize("folder", _subject_folders(), ids=lambda p: str(p.relative_to(DATA_ROOT)))
def test_a_meta_toml_agrees_with_the_data_yaml_beside_it(folder):
    """meta.toml restating the subject/category is only useful if it cannot
    disagree with the data.yaml one directory listing away."""
    meta = tomllib.loads((folder / "meta.toml").read_text(encoding="utf-8"))
    subject = yaml.safe_load((folder / "data.yaml").read_text(encoding="utf-8"))["subject"]

    assert meta["subject"] == subject["slug"]
    assert meta["category"] == subject["category"]
    assert meta["mode"] in {"generator", "transform", "scraper", "manual"}


@pytest.mark.parametrize("folder", _subject_folders(), ids=lambda p: str(p.relative_to(DATA_ROOT)))
def test_every_source_a_meta_toml_names_exists(folder):
    """Invariant 6, applied to the one registry that exists today: a name in
    a meta.toml must resolve to a real file, checked on load rather than when
    a run three weeks from now cannot find its config."""
    meta = tomllib.loads((folder / "meta.toml").read_text(encoding="utf-8"))
    known = {p.stem for p in SOURCES_DIR.glob("*.yaml")}

    unknown = [s for s in meta.get("sources", []) if s not in known]
    assert unknown == [], f"{folder.name}: no such source config in data/_sources/: {unknown}"


# --- Invariant 2: source config lives under data/ -------------------------

def test_no_source_config_lives_outside_data():
    """The rule that stops the four-directory sprawl coming back. Scoped to
    config that describes the provenance of a PUBLISHED fact: pipeline/config/
    registries.yaml is exempt by name because it lists Wikidata queries for
    seeding future crawls and explains nothing currently under data/."""
    exempt = {PIPELINE_ROOT / "config" / "registries.yaml"}
    suspects = [
        path
        for path in PIPELINE_ROOT.rglob("*.yaml")
        if path not in exempt
        and ".venv" not in path.parts
        and "tests" not in path.parts
        and "staging" not in path.parts
        and "review-state" not in path.parts
        and _looks_like_source_config(path)
    ]
    assert suspects == [], f"source config outside data/_sources/: {[str(p) for p in suspects]}"


def _looks_like_source_config(path: Path) -> bool:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError):
        return False
    if not isinstance(raw, dict):
        return False
    # A seed_url means a crawler source; a url + lizenz means a batch source.
    return "seed_url" in raw or ("url" in raw and "lizenz" in raw)


# --- Invariant 3: core/ does not import its callers -----------------------

def test_core_imports_neither_sources_nor_review():
    """The decoupling a repo split would have bought, without a repo split.
    sources/ and review/ may both import core/; core/ importing back would
    make the three a single tangled unit again - and it is exactly what
    core/crawl_runner.py used to do to the old top-level scraper.py.
    """
    offenders = []
    for module in sorted((PIPELINE_ROOT / "core").glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                if root in {"sources", "review"}:
                    offenders.append(f"core/{module.name}:{node.lineno} imports {name}")
    assert offenders == [], "core/ must not import sources/ or review/: " + "; ".join(offenders)
