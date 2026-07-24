"""Loads pipeline/config/crawl_sources/*.yaml - one file per scoped-crawler
source (Ziel 1 of the pipeline overhaul). Lives under pipeline/config/
(alongside the existing registries.yaml) rather than pipeline/sources/
(already a Python adapter package) or pipeline/sources.yaml (already the
automated batch pipeline's single config file) - three genuinely different
things that would collide under any shared name."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CRAWL_SOURCES_DIR = Path(__file__).resolve().parent.parent / "config" / "crawl_sources"

DEFAULT_MAX_DEPTH = 2
MAX_ALLOWED_DEPTH = 3


class CrawlConfigError(Exception):
    pass


@dataclass
class CrawlSource:
    id: str
    seed_url: str
    category: str
    allowed_domains: List[str]
    path_prefix: Optional[str]
    max_depth: int
    formats: List[str]
    event_type_hint: str
    schedule: str
    auto_approve_ics: bool = False
    config_path: Path = field(default=None, repr=False)  # type: ignore[assignment]


def _parse(raw: Dict[str, Any], path: Path) -> CrawlSource:
    for required in ("id", "seed_url", "category", "scope"):
        if required not in raw:
            raise CrawlConfigError(f"{path}: missing required field '{required}'")
    scope = raw["scope"]
    if "allowed_domains" not in scope or not scope["allowed_domains"]:
        raise CrawlConfigError(f"{path}: scope.allowed_domains must be a non-empty list")

    max_depth = raw.get("max_depth", DEFAULT_MAX_DEPTH)
    if not isinstance(max_depth, int) or not (0 <= max_depth <= MAX_ALLOWED_DEPTH):
        raise CrawlConfigError(f"{path}: max_depth must be an integer between 0 and {MAX_ALLOWED_DEPTH}")

    return CrawlSource(
        id=raw["id"],
        seed_url=raw["seed_url"],
        category=raw["category"],
        allowed_domains=list(scope["allowed_domains"]),
        path_prefix=scope.get("path_prefix"),
        max_depth=max_depth,
        formats=list(raw.get("formats", ["html"])),
        event_type_hint=raw.get("event_type_hint", ""),
        schedule=raw.get("schedule", "manual"),
        auto_approve_ics=bool(raw.get("auto_approve_ics", False)),
        config_path=path,
    )


def load_crawl_source(path: Path) -> CrawlSource:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    source = _parse(raw, path)
    if source.id != path.stem:
        raise CrawlConfigError(f"{path}: id '{source.id}' does not match filename '{path.stem}.yaml'")
    return source


def load_all_crawl_sources(directory: Path = CRAWL_SOURCES_DIR) -> Dict[str, CrawlSource]:
    if not directory.exists():
        return {}
    return {p.stem: load_crawl_source(p) for p in sorted(directory.glob("*.yaml"))}
