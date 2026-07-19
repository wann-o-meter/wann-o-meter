"""Stage 1: fetch a fixed entity_class's registry (e.g. all German
universities) into pipeline/data/registries/<entity_class>.json - kept under
pipeline/ rather than the repo-root data/ since the Astro site treats every
top-level folder under repo-root data/ as a page category (lib/pages.ts).

Only one acquisition method is implemented so far (wikidata_sparql, see
config/registries.yaml). Add a new method by adding a branch in
fetch_registry() - a Protocol/plugin system is unwarranted for two methods.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote, urlencode, urlparse

import yaml

from core.fetch import Config, fetch_bytes
from harvest.types import Entity

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_ROOT.parent
REGISTRIES_CONFIG = PIPELINE_ROOT / "config" / "registries.yaml"
OUTPUT_DIR = PIPELINE_ROOT / "data" / "registries"

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"
# Wikidata's SPARQL/API access policy requires an identifiable UA with
# contact info: https://meta.wikimedia.org/wiki/User-Agent_policy
USER_AGENT = "wann-harvester/1.0 (+https://github.com/am9zZWY/wann; contact: am9zzwy@gmail.com)"


def search_wikidata_classes(term: str, limit: int = 8) -> List[Dict[str, str]]:
    """Looks up candidate Wikidata item IDs for a free-text term (e.g.
    "museum" -> Q33506) via Wikidata's entity search API - backs the Add
    Registry form's class search, so an operator doesn't have to leave the
    dashboard to find the right wd:Q... for a new entity_class's SPARQL
    query."""
    query = urlencode({
        "action": "wbsearchentities",
        "search": term,
        "language": "de",
        "format": "json",
        "limit": limit,
    })
    config = Config()
    config.user_agent = USER_AGENT
    raw, _ = fetch_bytes(f"{WIKIDATA_SEARCH_ENDPOINT}?{query}", config)
    results = json.loads(raw).get("search", [])
    return [
        {"id": r["id"], "label": r.get("label", r["id"]), "description": r.get("description", "")}
        for r in results
    ]


def load_registries_config() -> Dict[str, Any]:
    with REGISTRIES_CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


class _BlockStringDumper(yaml.SafeDumper):
    """Forces multi-line strings (the sparql field) into YAML's literal "|"
    block style instead of PyYAML's default single-line \\n-escaped
    double-quoted string - keeps operator-added entries readable/diffable,
    matching the hand-written entries already in this file."""


def _block_str_representer(dumper: yaml.Dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_BlockStringDumper.add_representer(str, _block_str_representer)


def add_registry_config(entity_class: str, sparql: str, target_kinds: List[str]) -> None:
    """Appends a new wikidata_sparql entity_class to config/registries.yaml -
    the only method the Admin UI's Add Registry form supports; csv_import (or
    any future method) still has to be added by hand, see fetch_registry()."""
    config = load_registries_config()
    if entity_class in config:
        raise ValueError(f"entity_class '{entity_class}' already exists")

    config[entity_class] = {
        "method": "wikidata_sparql",
        "sparql": sparql if sparql.endswith("\n") else sparql + "\n",
        "target_kinds": target_kinds,
    }
    with REGISTRIES_CONFIG.open("w", encoding="utf-8") as f:
        yaml.dump(
            config, f,
            allow_unicode=True, sort_keys=False, default_flow_style=False,
            Dumper=_BlockStringDumper,
        )


def delete_registry_config(entity_class: str) -> None:
    """Removes an entity_class from config/registries.yaml and deletes its
    fetched data/registries/<entity_class>.json, if any - the Admin UI's
    Delete Registry action."""
    config = load_registries_config()
    if entity_class not in config:
        raise ValueError(f"entity_class '{entity_class}' does not exist")
    del config[entity_class]
    with REGISTRIES_CONFIG.open("w", encoding="utf-8") as f:
        yaml.dump(
            config, f,
            allow_unicode=True, sort_keys=False, default_flow_style=False,
            Dumper=_BlockStringDumper,
        )
    (OUTPUT_DIR / f"{entity_class}.json").unlink(missing_ok=True)


def _slugify(text: str) -> str:
    text = text.lower().strip()
    for umlaut, ascii_form in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}.items():
        text = text.replace(umlaut, ascii_form)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "entity"


def _normalized_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _query_wikidata(sparql: str) -> List[Dict[str, Any]]:
    url = f"{WIKIDATA_ENDPOINT}?query={quote(sparql)}&format=json"
    config = Config()
    config.user_agent = USER_AGENT
    raw, _ = fetch_bytes(url, config)
    return json.loads(raw)["results"]["bindings"]


def _entities_from_bindings(
    entity_class: str, bindings: List[Dict[str, Any]], fetched_at: str
) -> List[Entity]:
    """Pure transform, split out from _entities_from_wikidata so tests can
    feed it a fixed bindings list instead of hitting the network."""
    by_domain: Dict[str, Entity] = {}
    slugs_used: Dict[str, int] = {}

    for row in bindings:
        website = row.get("website", {}).get("value")
        name = row.get("itemLabel", {}).get("value")
        if not website or not name:
            continue

        domain = _normalized_domain(website)
        if not domain or domain in by_domain:
            # Recursive P131* region traversal produces one row per admin
            # level match for the same item/website - first hit wins.
            continue

        base_slug = _slugify(name)
        slugs_used[base_slug] = slugs_used.get(base_slug, 0) + 1
        n = slugs_used[base_slug]
        slug = base_slug if n == 1 else f"{base_slug}-{n}"

        item_uri = row.get("item", {}).get("value", "")
        by_domain[domain] = Entity(
            entity_id=slug,
            entity_class=entity_class,
            name=name,
            domain=domain,
            wikidata_id=item_uri.rsplit("/", 1)[-1] or None,
            region=row.get("regionISO", {}).get("value"),
            registry_source="wikidata",
            fetched_at=fetched_at,
        )

    return list(by_domain.values())


def _entities_from_wikidata(entity_class: str, sparql: str) -> List[Entity]:
    bindings = _query_wikidata(sparql)
    fetched_at = datetime.now(timezone.utc).isoformat()
    return _entities_from_bindings(entity_class, bindings, fetched_at)


def fetch_registry(entity_class: str) -> List[Entity]:
    config = load_registries_config()
    if entity_class not in config:
        raise ValueError(f"Unknown entity_class '{entity_class}'. Known: {', '.join(config)}")

    method = config[entity_class]["method"]
    if method == "wikidata_sparql":
        entities = _entities_from_wikidata(entity_class, config[entity_class]["sparql"])
    else:
        raise ValueError(f"Unsupported registry method '{method}' for '{entity_class}'")

    return sorted(entities, key=lambda e: e.entity_id)


def load_registry_domains(entity_class: str) -> List[str]:
    """Domains from an already-fetched registry (pipeline/data/registries/
    <entity_class>.json) - lets the crawler bulk-seed itself from harvest
    data instead of an operator typing hundreds of domains by hand (see
    main.py's /start)."""
    path = (OUTPUT_DIR / f"{entity_class}.json").resolve()
    if path.parent != OUTPUT_DIR.resolve() or not path.exists():
        return []
    entities = json.loads(path.read_text(encoding="utf-8"))
    return [e["domain"] for e in entities if e.get("domain")]


def write_registry(entity_class: str, entities: List[Entity]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{entity_class}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump([e.to_dict() for e in entities], f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


def run(entity_class: str) -> int:
    print(f"[harvest.registry] Fetching registry for '{entity_class}' ...", file=sys.stderr)
    entities = fetch_registry(entity_class)
    out_path = write_registry(entity_class, entities)
    print(
        f"[harvest.registry] Wrote {len(entities)} entities -> {out_path.relative_to(REPO_ROOT)}",
        file=sys.stderr,
    )
    return 0
