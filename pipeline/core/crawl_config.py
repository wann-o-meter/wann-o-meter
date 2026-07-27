"""Loads data/_sources/*.yaml - one file per scoped-crawler source.

Source config lives under data/ (not pipeline/) because it describes where
a published fact came from, which is the dataset's business, not the
scraper's. It cannot live inside the subject folder it feeds: source and
subject are many-to-many in both directions - two NASA catalog sources feed
one astronomie/sonnenfinsternis page (see CrawlSource.subject_slug below),
one KMK page feeds sixteen schulferien subjects, and a source config exists
before its subject folder does. The leading underscore keeps _sources/ out
of the Astro category walk (lib/pages.ts), which treats every other
directory under data/ as a page category.

Still YAML rather than the TOML the redesign sketched: these files are
machine-written by the review UI's create/edit routes, and Python has no
TOML writer in the stdlib. Hand-authored, read-only files (a subject's
meta.toml) can be TOML; this one would have cost a dependency to keep a
format promise nothing depends on."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

CRAWL_SOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "_sources"

DEFAULT_MAX_DEPTH = 2
MAX_ALLOWED_DEPTH = 3

# How a source's HTML/PDF/image documents get turned into windows:
#   auto   - a deterministic date scrape for HTML pages that are plainly date
#            TABLES (see crawl_runner.STATIC_DATE_THRESHOLD), the model for
#            everything else. PDFs and images always go to the model here:
#            their text comes from OCR/vision, where the model's reading of
#            what a date MEANS is the whole value.
#   llm    - always the model, whatever the page looks like. The right choice
#            when every date needs its own real label.
#   static - never the model. Cheap and exhaustive on a machine-generated
#            table, at the cost of one shared label for every date.
EXTRACTION_MODES = ("auto", "llm", "static")
DEFAULT_EXTRACTION_MODE = "auto"


class CrawlConfigError(Exception):
    pass


# A subject_slug becomes a real directory name under data/{category}/, so
# it is validated here rather than trusted: config files are hand-edited,
# and "../../.." would write outside data/ entirely. Same shape review/service.py's
# _slugify produces for a single segment.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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
    # Which page this source's events land in: data/{category}/{subject_slug}/.
    # Defaults to `id`, which is what every source did before this existed.
    #
    # Set the SAME category + subject_slug on several sources to aggregate
    # them into one page - the point of the whole pipeline (see
    # store.merge_zeitfenster: same window from two sources keeps one entry
    # and unions the citations). BOTH fields have to match; a shared
    # subject_slug under different categories silently yields two pages
    # again, since the file path is what identifies the subject.
    #
    # Changing this on a source that already has approved candidates
    # re-opens all of them: content_hash.normalize_event() hashes the
    # subject_slug, so every window gets a new hash - review_state.diff()
    # then sees them as brand-new candidates AND flags the old hashes as
    # disappeared. Safe to set on a new source, disruptive on a live one.
    subject_slug: str = ""
    # Optional explicit page title. With several sources feeding one page,
    # store.schreibe_page_yaml_falls_neu writes page.yaml from whichever
    # source approved FIRST, using that source's own <title> - so leaving
    # this blank makes a shared page's heading depend on crawl order. Set it
    # to pin the title; blank falls back to crawl_runner._subject_name's
    # LLM-cleaned <title>, the previous behavior.
    subject_name: str = ""
    extraction_mode: str = DEFAULT_EXTRACTION_MODE
    auto_approve_ics: bool = False
    config_path: Path = field(default=None, repr=False)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """A blank subject_slug means "its own page". Defaulted here rather
        than only in _parse() so a CrawlSource built directly in code gets
        the same fallback a config file does."""
        if not self.subject_slug:
            self.subject_slug = self.id


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

    extraction_mode = raw.get("extraction_mode", DEFAULT_EXTRACTION_MODE)
    if extraction_mode not in EXTRACTION_MODES:
        raise CrawlConfigError(f"{path}: extraction_mode must be one of {', '.join(EXTRACTION_MODES)}")

    subject_slug = str(raw.get("subject_slug") or raw["id"])
    if not _SLUG_RE.match(subject_slug):
        raise CrawlConfigError(
            f"{path}: subject_slug '{subject_slug}' must be a lowercase slug "
            "(a-z, 0-9, single dashes) - it becomes a directory name under data/"
        )

    return CrawlSource(
        id=raw["id"],
        seed_url=raw["seed_url"],
        category=raw["category"],
        subject_slug=subject_slug,
        subject_name=str(raw.get("subject_name", "") or "").strip(),
        allowed_domains=list(scope["allowed_domains"]),
        path_prefix=scope.get("path_prefix"),
        max_depth=max_depth,
        formats=list(raw.get("formats", ["html"])),
        event_type_hint=raw.get("event_type_hint", ""),
        schedule=raw.get("schedule", "manual"),
        extraction_mode=extraction_mode,
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


def load_all_crawl_sources(directory: Optional[Path] = None) -> Dict[str, CrawlSource]:
    # directory=CRAWL_SOURCES_DIR as the default would bind that Path at
    # *function definition* time - a test monkeypatching the module-level
    # CRAWL_SOURCES_DIR afterward (the same pattern staging.STAGING_ROOT/
    # review_state.REVIEW_STATE_ROOT rely on) would then silently keep
    # reading the real directory. Resolving it inside the body instead
    # reads whatever CRAWL_SOURCES_DIR currently is at call time.
    if directory is None:
        directory = CRAWL_SOURCES_DIR
    if not directory.exists():
        return {}
    return {p.stem: load_crawl_source(p) for p in sorted(directory.glob("*.yaml")) if _is_crawl_source(p)}


def _is_crawl_source(path: Path) -> bool:
    """data/_sources/ holds every source config, and core/runner.py's
    single-fetch batch sources sit in the same directory (they answer the
    same "where did this come from" question). They mark themselves with an
    explicit `kind`; a file with no `kind` is a crawler source, so a typo in
    a real crawl config still raises through _parse() instead of being
    silently skipped."""
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return not isinstance(raw, dict) or "kind" not in raw
