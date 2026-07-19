"""Entity-first harvest pipeline data models. Stage 1 (registry) fills in
Entity; later stages (Seed, Event) get added here once those stages exist -
see the harvest-pipeline spec for the full model."""

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Entity:
    entity_id: str
    entity_class: str
    name: str
    domain: str
    wikidata_id: Optional[str]
    region: Optional[str]
    registry_source: str
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)
