import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

import pytest  # noqa: E402
import yaml  # noqa: E402

from harvest import registry  # noqa: E402
from harvest.registry import _entities_from_bindings, _normalized_domain, _slugify  # noqa: E402

FETCHED_AT = "2026-07-14T00:00:00+00:00"

EXISTING_CONFIG = (
    "university_de:\n"
    "  method: wikidata_sparql\n"
    "  sparql: |\n"
    "    SELECT ?x\n"
    "  target_kinds: [semestertermine]\n"
)


def _binding(item, label, website, region=None):
    row = {
        "item": {"value": f"http://www.wikidata.org/entity/{item}"},
        "itemLabel": {"value": label},
        "website": {"value": website},
    }
    if region:
        row["regionISO"] = {"value": region}
    return row


def test_dedupes_multivalued_region_rows_from_the_same_item():
    # P131* recursion produces one row per admin-level match for the same
    # item/website - only the first region hit should survive.
    bindings = [
        _binding("Q1", "Uni Beispiel", "https://www.uni-beispiel.de", "DE-BW"),
        _binding("Q1", "Uni Beispiel", "https://www.uni-beispiel.de", "DE"),
    ]

    entities = _entities_from_bindings("university_de", bindings, FETCHED_AT)

    assert len(entities) == 1
    assert entities[0].region == "DE-BW"
    assert entities[0].domain == "uni-beispiel.de"
    assert entities[0].wikidata_id == "Q1"


def test_slugifies_duplicate_names_with_a_numeric_suffix():
    bindings = [
        _binding("Q1", "Universität Beispiel", "https://uni-a.de"),
        _binding("Q2", "Universität Beispiel", "https://uni-b.de"),
    ]

    entities = _entities_from_bindings("university_de", bindings, FETCHED_AT)

    assert sorted(e.entity_id for e in entities) == [
        "universitaet-beispiel",
        "universitaet-beispiel-2",
    ]


def test_skips_rows_missing_website_or_label():
    bindings = [
        {"item": {"value": "http://www.wikidata.org/entity/Q1"}, "itemLabel": {"value": "No Website"}},
        {"item": {"value": "http://www.wikidata.org/entity/Q2"}, "website": {"value": "https://x.de"}},
    ]

    assert _entities_from_bindings("university_de", bindings, FETCHED_AT) == []


def test_normalized_domain_strips_www():
    assert _normalized_domain("https://www.uni-tuebingen.de/foo") == "uni-tuebingen.de"
    assert _normalized_domain("https://uni-tuebingen.de") == "uni-tuebingen.de"


def test_slugify_folds_umlauts():
    assert _slugify("Eberhard Karls Universität Tübingen") == "eberhard-karls-universitaet-tuebingen"


def test_add_registry_config_writes_block_style_sparql(tmp_path, monkeypatch):
    config_path = tmp_path / "registries.yaml"
    config_path.write_text(EXISTING_CONFIG, encoding="utf-8")
    monkeypatch.setattr(registry, "REGISTRIES_CONFIG", config_path)

    registry.add_registry_config(
        "museum_de", "SELECT ?item WHERE {\n  ?item wdt:P31 wd:Q1 .\n}", ["oeffnungszeiten"]
    )

    written = config_path.read_text(encoding="utf-8")
    assert written.count("sparql: |") == 2  # both the existing and new entry stay block-style

    reloaded = yaml.safe_load(written)
    assert reloaded["museum_de"]["method"] == "wikidata_sparql"
    assert reloaded["museum_de"]["target_kinds"] == ["oeffnungszeiten"]
    assert reloaded["university_de"]["target_kinds"] == ["semestertermine"]  # untouched


def test_add_registry_config_rejects_duplicate_entity_class(tmp_path, monkeypatch):
    config_path = tmp_path / "registries.yaml"
    config_path.write_text(EXISTING_CONFIG, encoding="utf-8")
    monkeypatch.setattr(registry, "REGISTRIES_CONFIG", config_path)

    with pytest.raises(ValueError):
        registry.add_registry_config("university_de", "SELECT ?x", ["semestertermine"])


def test_delete_registry_config_removes_entry_and_data(tmp_path, monkeypatch):
    config_path = tmp_path / "registries.yaml"
    config_path.write_text(
        EXISTING_CONFIG + "museum_de:\n  method: wikidata_sparql\n  sparql: |\n    SELECT ?x\n  target_kinds: [oeffnungszeiten]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "REGISTRIES_CONFIG", config_path)
    output_dir = tmp_path / "registries"
    output_dir.mkdir()
    monkeypatch.setattr(registry, "OUTPUT_DIR", output_dir)
    (output_dir / "museum_de.json").write_text("[]", encoding="utf-8")

    registry.delete_registry_config("museum_de")

    reloaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "museum_de" not in reloaded
    assert reloaded["university_de"]["target_kinds"] == ["semestertermine"]  # untouched
    assert not (output_dir / "museum_de.json").exists()


def test_delete_registry_config_rejects_unknown_entity_class(tmp_path, monkeypatch):
    config_path = tmp_path / "registries.yaml"
    config_path.write_text(EXISTING_CONFIG, encoding="utf-8")
    monkeypatch.setattr(registry, "REGISTRIES_CONFIG", config_path)

    with pytest.raises(ValueError):
        registry.delete_registry_config("does_not_exist")


def test_search_wikidata_classes_parses_id_label_description(monkeypatch):
    import json as json_module

    fake_response = json_module.dumps({
        "search": [
            {"id": "Q33506", "label": "museum", "description": "institution that holds artifacts"},
            {"id": "Q123", "label": "no description here"},  # description missing entirely
        ]
    }).encode("utf-8")
    monkeypatch.setattr(registry, "fetch_bytes", lambda url, config=None: (fake_response, ""))

    results = registry.search_wikidata_classes("museum")

    assert results == [
        {"id": "Q33506", "label": "museum", "description": "institution that holds artifacts"},
        {"id": "Q123", "label": "no description here", "description": ""},
    ]
