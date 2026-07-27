"""Fixture-Test fuer core/generic_source.py, ueber das schulferien_kmk jetzt
laeuft (siehe pipeline/README.md "Pipeline-Struktur") - kein bespoke
sources/schulferien_kmk.py-Adapter mehr, nur die data/_sources-Konfiguration.
raw_sample.html ist ein echter, einmalig gespeicherter Abruf der
KMK-Ferienuebersicht. erwartet.yaml steht fuer eine aufgezeichnete
Modell-Antwort (zwei Bundeslaender, um den Subjekt-Split-Mechanismus zu
testen) - in den meisten Tests hier per monkeypatch von
generic_source.extract_subjects direkt geliefert; das testet den generischen
Engine-Vertrag, den Store-Merge (window_key-Semantik) und die echte
Zod-Validierung, nicht die Extraktion selbst. Der echte LLM-Aufruf-Pfad
(core.extraction.call_llm -> JSON-Parsing -> Subjekt-/Typ-Mapping) wird
separat gemockt getestet, wie in tests/test_extraction.py."""

import sys
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import extraction, generic_source, store, validate  # noqa: E402
from core.runner import load_sources_config  # noqa: E402

FIXTURES = PIPELINE_ROOT / "tests" / "fixtures" / "schulferien_kmk"
PARAMS = {"jahr": "2028"}


@pytest.fixture
def config():
    return load_sources_config()["schulferien_kmk"]


@pytest.fixture
def erwartete_subjecte():
    return yaml.safe_load((FIXTURES / "erwartet.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def raw_sample():
    return (FIXTURES / "raw_sample.html").read_bytes()


def test_window_year_comes_from_the_date_not_the_parameter(monkeypatch, config, raw_sample, erwartete_subjecte):
    """A school year spans two calendar years, so the parameter cannot
    describe both ends. Stamping it produced windows reading year: 2028 beside
    from: 2026-11-02, and `year` is part of window_key."""
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjecte)

    results = generic_source.extract(config, raw_sample, {"jahr": "2099"})

    for result in results:
        for window in result.zeitfenster:
            assert window["year"] == int(window["from"][:4]) != 2099


def test_extract_runs_without_a_jahr_parameter(monkeypatch, config, raw_sample, erwartete_subjecte):
    """extraction_hint contains {jahr}; str.format raises KeyError on a missing
    placeholder, so omitting the flag crashed the run."""
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjecte)

    assert generic_source.extract(config, raw_sample, {})


def test_a_passed_parameter_still_reaches_the_hint(monkeypatch, config, raw_sample, erwartete_subjecte):
    seen = {}

    def _record(text, hint):
        seen["hint"] = hint
        return erwartete_subjecte

    monkeypatch.setattr(generic_source, "extract_subjects", _record)

    generic_source.extract(config, raw_sample, {"jahr": "2031"})

    assert "2031" in seen["hint"]


def test_extract_liefert_ein_ergebnis_pro_subject(monkeypatch, config, raw_sample, erwartete_subjecte):
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjecte)

    results = generic_source.extract(config, raw_sample, PARAMS)

    # Zwei Subjekte rein (bw, by) -> zwei ExtraktionsErgebnis raus, mit
    # unterschiedlichen Zielpathen - das ist der eigentliche Punkt des
    # generischen Engines: ein Fetch kann mehrere Seiten erzeugen.
    assert [e.subject["slug"] for e in results] == ["bw", "by"]
    assert len({e.file_path for e in results}) == 2
    for result in results:
        assert result.subject["category"] == "schulferien"
        assert result.source["extraction"] == "llm"
        assert result.source["url"] == config["url"]
        assert "2028" in result.source["license_note"]


def test_extract_stamps_source_urls_from_source(monkeypatch, config, raw_sample, erwartete_subjecte):
    """ExtraktionsErgebnis.__post_init__ (core/types.py) stamps each window
    with the run's Quelle-URL by default - the generic engine doesn't have
    to do this itself, same as the deleted schulferien_kmk.py adapter."""
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjecte)

    ergebnisse = generic_source.extract(config, raw_sample, PARAMS)

    assert sum(len(e.zeitfenster) for e in ergebnisse) > 0
    for ergebnis in ergebnisse:
        for window in ergebnis.zeitfenster:
            assert window["source_urls"] == [ergebnis.source["url"]]


def test_ohne_llm_anbindung_bricht_sauber_ab(monkeypatch, config, raw_sample):
    """Kein API-Key konfiguriert -> LlmError aus core/llm.py propagiert als
    ExtractionError, statt still leere or erfundene Daten zu liefern."""
    for env_var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    with pytest.raises(extraction.ExtractionError, match="ANTHROPIC_API_KEY"):
        generic_source.extract(config, raw_sample, PARAMS)


def test_echte_llm_extraktion_liefert_subjecte_und_zeitfenster_form(monkeypatch, config, raw_sample):
    """Mockt core.extraction.call_llm (wie tests/test_extraction.py) statt
    generic_source.extract_subjects direkt - deckt damit den tatsaechlichen
    LLM-Aufruf-Pfad ab: Decodierung, Prompt/Hint, JSON-Parsing,
    Subjekt-Split, Typ-Mapping ueber den Ferien-Namen."""
    monkeypatch.setattr(
        extraction,
        "call_llm",
        lambda prompt, system=None: (
            '[{"subject": {"slug": "bw", "name": "Schulferien Baden-Württemberg"}, '
            '"ranges": [{"start": "2028-03-27", "end": "2028-04-08", "label": "Osterferien"}]}, '
            '{"subject": {"slug": "by", "name": "Schulferien Bayern"}, '
            '"ranges": [{"start": "2028-08-01", "end": "2028-09-12", "label": "Sommerferien"}]}]'
        ),
    )

    ergebnisse = generic_source.extract(config, raw_sample, PARAMS)

    assert len(ergebnisse) == 2
    bw, by = ergebnisse
    assert bw.subject == {"slug": "bw", "name": "Schulferien Baden-Württemberg", "category": "schulferien"}
    assert bw.zeitfenster == [
        {
            "type": "school_holidays-easter",
            "year": 2028,
            "from": "2028-03-27",
            "to": "2028-04-08",
            "precision": "exact",
            "ics": False,
            "name": "Osterferien",
            "source_urls": [bw.source["url"]],
        }
    ]
    assert by.zeitfenster[0]["type"] == "school_holidays-summer"


def test_leere_llm_antwort_liefert_leere_liste_statt_fehler(monkeypatch, config, raw_sample):
    monkeypatch.setattr(extraction, "call_llm", lambda prompt, system=None: "[]")

    ergebnisse = generic_source.extract(config, raw_sample, PARAMS)

    assert ergebnisse == []


def test_unparsebare_llm_antwort_wirft_extraction_error(monkeypatch, config, raw_sample):
    monkeypatch.setattr(extraction, "call_llm", lambda prompt, system=None: "kein JSON")

    with pytest.raises(extraction.ExtractionError, match="not valid JSON"):
        generic_source.extract(config, raw_sample, PARAMS)


def test_store_merge_und_echte_zod_validierung(monkeypatch, tmp_path, config, raw_sample, erwartete_subjecte):
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjecte)
    monkeypatch.setattr(generic_source, "DATA_ROOT", tmp_path)

    ergebnisse = generic_source.extract(config, raw_sample, PARAMS)
    assert len(ergebnisse) == 2

    for ergebnis, erwartet in zip(ergebnisse, erwartete_subjecte, strict=True):
        file = store.load_or_create(
            ergebnis.file_path,
            ergebnis.subject["slug"],
            ergebnis.subject["category"],
        )
        store.merge_windows(file, ergebnis.zeitfenster)
        store.append_source(file, ergebnis.source)

        validate.pruefe_subject_file(file)  # wirft ValidationError bei ungueltiger Form

        store.speichere(ergebnis.file_path, file)
        assert ergebnis.file_path.exists()
        gespeichert = yaml.safe_load(ergebnis.file_path.read_text(encoding="utf-8"))
        assert len(gespeichert["windows"]) == len(erwartet["ranges"])
        assert len(gespeichert["source"]) == 1
        for window in gespeichert["windows"]:
            assert window["source_urls"] == [ergebnis.source["url"]]

    # Zwei Subjekte landen in zwei getrennten Ordnern, nicht demselben.
    assert (tmp_path / "schulferien" / "bw" / "data.yaml").exists()
    assert (tmp_path / "schulferien" / "by" / "data.yaml").exists()


def test_ein_zweiter_lauf_erzeugt_keine_duplikate(monkeypatch, tmp_path, config, raw_sample, erwartete_subjecte):
    """Zweiter Lauf fuer dasselbe Jahr darf keine Duplikate erzeugen - jedes
    Fenster hat denselben window_key wie beim ersten Lauf. Also covers
    append_source's URL dedup: re-running the same source must not grow
    "sources"."""
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjecte)
    monkeypatch.setattr(generic_source, "DATA_ROOT", tmp_path)

    for _ in range(2):
        ergebnisse = generic_source.extract(config, raw_sample, PARAMS)
        for ergebnis in ergebnisse:
            file = store.load_or_create(
                ergebnis.file_path,
                ergebnis.subject["slug"],
                ergebnis.subject["category"],
            )
            store.merge_windows(file, ergebnis.zeitfenster)
            store.append_source(file, ergebnis.source)
            store.speichere(ergebnis.file_path, file)

    for erwartet in erwartete_subjecte:
        path = tmp_path / "schulferien" / erwartet["subject"]["slug"] / "data.yaml"
        gespeichert = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert len(gespeichert["windows"]) == len(erwartet["ranges"])
        assert len(gespeichert["source"]) == 1
        for window in gespeichert["windows"]:
            assert window["source_urls"] == [gespeichert["source"][0]["url"]]


def test_pruefe_subject_file_lehnt_ungueltige_form_ab():
    with pytest.raises(validate.ValidationError):
        validate.pruefe_subject_file({"subject": {"slug": "bw"}, "windows": []})


class TestExtractSeason:
    """Coverage for generic_source.extract_season (strategy: llm_season) -
    the color-highlighting-aware counterpart to extract() above, for sources
    like a Saisonkalender PDF/image where the actual information is which
    months are highlighted, not literal text. Uses a synthetic PDF (fitz, no
    real vision call - extract_any is mocked at the point where it would
    otherwise call the vision LLM) since there's no recorded real-world
    fixture for this yet."""

    CONFIG: ClassVar[dict] = {
        "category": "saisonkalender",
        "url": "https://example.invalid/saisonkalender.pdf",
        "license": "cc_by",
        "extraction_hint": "Saisonkalender fuer Obst/Gemuese (Testsource)",
    }
    ERWARTETE_SUBJEKTE: ClassVar[list] = [
        {
            "subject": {"slug": "apfel", "name": "Apfel"},
            "windows": [
                {"type": "main_season", "name": "Hauptsaison", "from": "--05", "to": "--08"},
            ],
        },
        {
            "subject": {"slug": "aprikosen", "name": "Aprikosen"},
            "windows": [
                {"type": "peak_season", "name": "Spitzensaison", "from": "--06", "to": "--08"},
            ],
        },
    ]

    def test_liefert_ein_ergebnis_pro_subject_mit_jahrlosen_monatsfenstern(self, monkeypatch):
        monkeypatch.setattr(
            generic_source,
            "extract_any",
            lambda name, raw: {"kind": "pdf_document", "clean_markdown_full": "Aepfel: 5-8 orange, Rest gruen"},
        )
        monkeypatch.setattr(
            generic_source,
            "extract_season_windows",
            lambda text, hint: self.ERWARTETE_SUBJEKTE,
        )

        results = generic_source.extract_season(self.CONFIG, b"%PDF-fake", {})

        assert [e.subject["slug"] for e in results] == ["apfel", "aprikosen"]
        assert len({e.file_path for e in results}) == 2
        for result in results:
            assert result.subject["category"] == "saisonkalender"
            assert result.source["extraction"] == "llm"
            assert result.source["url"] == "https://example.invalid/saisonkalender.pdf"

    def test_windows_are_year_less_and_approximate(self, monkeypatch):
        monkeypatch.setattr(
            generic_source,
            "extract_any",
            lambda name, raw: {"kind": "pdf_document", "clean_markdown_full": "Aepfel: 5-8 orange, Rest gruen"},
        )
        monkeypatch.setattr(
            generic_source,
            "extract_season_windows",
            lambda text, hint: self.ERWARTETE_SUBJEKTE,
        )

        results = generic_source.extract_season(self.CONFIG, b"%PDF-fake", {})

        apfel = results[0]
        assert apfel.zeitfenster == [
            {
                "type": "main_season",
                "year": None,
                "from": "--05",
                "to": "--08",
                "precision": "approximate",
                "ics": False,
                "name": "Hauptsaison",
                "source_urls": [apfel.source["url"]],
            }
        ]

    def test_raises_extraction_error_when_the_scrape_produced_no_usable_text(self, monkeypatch):
        # e.g. the vision call failed (no API key) - core/sniff.py's extract_any
        # returns unsupported_binary with no clean_markdown_full at all, so
        # there is nothing to feed the LLM. Must surface WHY, not silently
        # return an empty result indistinguishable from "no season data here".
        monkeypatch.setattr(
            generic_source,
            "extract_any",
            lambda name, raw: {
                "kind": "unsupported_binary",
                "reason": "vision extraction failed: ANTHROPIC_API_KEY is not set",
            },
        )

        with pytest.raises(extraction.ExtractionError, match="ANTHROPIC_API_KEY"):
            generic_source.extract_season(self.CONFIG, b"%PDF-fake", {})

    def test_store_merge_und_echte_zod_validierung(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            generic_source,
            "extract_any",
            lambda name, raw: {"kind": "pdf_document", "clean_markdown_full": "Aepfel: 5-8 orange, Rest gruen"},
        )
        monkeypatch.setattr(
            generic_source,
            "extract_season_windows",
            lambda text, hint: self.ERWARTETE_SUBJEKTE,
        )
        monkeypatch.setattr(generic_source, "DATA_ROOT", tmp_path)

        results = generic_source.extract_season(self.CONFIG, b"%PDF-fake", {})
        assert len(results) == 2

        for ergebnis in results:
            file = store.load_or_create(
                ergebnis.file_path,
                ergebnis.subject["slug"],
                ergebnis.subject["category"],
            )
            store.merge_windows(file, ergebnis.zeitfenster)
            store.append_source(file, ergebnis.source)

            validate.pruefe_subject_file(file)  # wirft ValidationError bei ungueltiger Form

            store.speichere(ergebnis.file_path, file)
            gespeichert = yaml.safe_load(ergebnis.file_path.read_text(encoding="utf-8"))
            assert gespeichert["windows"][0]["year"] is None
            assert gespeichert["windows"][0]["from"].startswith("--")

        assert (tmp_path / "saisonkalender" / "apfel" / "data.yaml").exists()
        assert (tmp_path / "saisonkalender" / "aprikosen" / "data.yaml").exists()
