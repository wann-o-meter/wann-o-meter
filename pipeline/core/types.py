"""The adapter contract. Deliberately tiny: a Protocol, not an inheritance
tower - extract() is a source's only job, everything else (fetch, merge,
validate, publish) is core/'s job, never a source's."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Protocol, Tuple


@dataclass
class ExtractionResult:
    subjekt: Dict[str, Any]            # slug, name, category - name is only used
    # for the page.yaml title (written once on first creation), the data.yaml
    # subject block itself is just {slug, category} (pageDataSchema, lib/pages-schema.ts)
    datei_pfad: Path                   # e.g. data/urlaubsfenster/bw.yaml - often
    # depends on params (Schulferien: one file PER Bundesland), so it's set
    # by the adapter instead of guessed by the runner.
    zeitfenster: List[Dict[str, Any]]  # RawWindow shape, see lib/schema.ts
    quelle: Dict[str, Any]             # Source shape: url, license, extraction, ...
    replace_key: Tuple[str, ...] = ("type",)  # which fields define a match
    # that the merge replaces instead of appending - Schulferien e.g. ("type", "year")

    def __post_init__(self) -> None:
        """Stamps each window with its originating source URL by default -
        this is core's job, not each source adapter's (see module docstring):
        an adapter already builds quelle["url"] once per run, so requiring
        every adapter to also copy it onto each of its zeitfenster entries
        would just be the same boilerplate repeated per source. Only fills
        in "source_urls" when the adapter hasn't already set one itself
        (e.g. a future adapter that draws one window from more than one
        URL in a single run). See RawWindow.source_urls in lib/schema.ts."""
        url = self.quelle.get("url")
        if not url:
            return
        for window in self.zeitfenster:
            window.setdefault("source_urls", [url])


class SourceAdapter(Protocol):
    id: str
    kategorie: str

    def extract(self, raw: bytes, params: Dict[str, Any]) -> ExtractionResult: ...
