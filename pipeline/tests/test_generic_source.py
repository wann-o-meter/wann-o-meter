"""Fixture-Test fuer core/generic_source.py, ueber das schulferien_kmk jetzt
laeuft (siehe pipeline/README.md "Pipeline-Struktur") - kein bespoke
sources/schulferien_kmk.py-Adapter mehr, nur die sources.yaml-Konfiguration.
raw_sample.html ist ein echter, einmalig gespeicherter Abruf von
kmk.org/service/ferien.html. erwartet.yaml steht fuer eine aufgezeichnete
Modell-Antwort (zwei Bundeslaender, um den Subjekt-Split-Mechanismus zu
testen) - in den meisten Tests hier per monkeypatch von
generic_source.extract_subjects direkt geliefert; das testet den generischen
Engine-Vertrag, den Store-Merge (inkl. replace_key-Semantik) und die echte
Zod-Validierung, nicht die Extraktion selbst. Der echte LLM-Aufruf-Pfad
(core.extraction.call_llm -> JSON-Parsing -> Subjekt-/Typ-Mapping) wird
separat gemockt getestet, wie in tests/test_extraction.py."""

import sys
from pathlib import Path

import pytest
import yaml

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import extraction, generic_source, store, validate  # noqa: E402
from core.runner import lade_quellen_config  # noqa: E402

FIXTURES = PIPELINE_ROOT / "fixtures" / "schulferien_kmk"
PARAMS = {"jahr": "2028"}


@pytest.fixture
def config():
    return lade_quellen_config()["schulferien_kmk"]


@pytest.fixture
def erwartete_subjekte():
    return yaml.safe_load((FIXTURES / "erwartet.yaml").read_text(encoding="utf-8"))


@pytest.fixture
def raw_sample():
    return (FIXTURES / "raw_sample.html").read_bytes()


def test_extract_liefert_ein_ergebnis_pro_subjekt(monkeypatch, config, raw_sample, erwartete_subjekte):
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjekte)

    results = generic_source.extract(config, raw_sample, PARAMS)

    # Zwei Subjekte rein (bw, by) -> zwei ExtraktionsErgebnis raus, mit
    # unterschiedlichen Zielpfaden - das ist der eigentliche Punkt des
    # generischen Engines: ein Fetch kann mehrere Seiten erzeugen.
    assert [e.subjekt["slug"] for e in results] == ["bw", "by"]
    assert len({e.datei_pfad for e in results}) == 2
    for result in results:
        assert result.subjekt["category"] == "schulferien"
        assert result.replace_key == ("type", "year")
        assert result.quelle["extraction"] == "llm"
        assert result.quelle["url"] == "https://www.kmk.org/service/ferien.html"
        assert "2028" in result.quelle["license_note"]


def test_extract_stamps_source_urls_from_quelle(monkeypatch, config, raw_sample, erwartete_subjekte):
    """ExtraktionsErgebnis.__post_init__ (core/types.py) stamps each window
    with the run's Quelle-URL by default - the generic engine doesn't have
    to do this itself, same as the deleted schulferien_kmk.py adapter."""
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjekte)

    ergebnisse = generic_source.extract(config, raw_sample, PARAMS)

    assert sum(len(e.zeitfenster) for e in ergebnisse) > 0
    for ergebnis in ergebnisse:
        for window in ergebnis.zeitfenster:
            assert window["source_urls"] == [ergebnis.quelle["url"]]


def test_ohne_llm_anbindung_bricht_sauber_ab(monkeypatch, config, raw_sample):
    """Kein API-Key konfiguriert -> LlmError aus core/llm.py propagiert als
    ExtractionError, statt still leere oder erfundene Daten zu liefern."""
    for env_var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")

    with pytest.raises(extraction.ExtractionError, match="ANTHROPIC_API_KEY"):
        generic_source.extract(config, raw_sample, PARAMS)


def test_echte_llm_extraktion_liefert_subjekte_und_zeitfenster_form(monkeypatch, config, raw_sample):
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
    assert bw.subjekt == {"slug": "bw", "name": "Schulferien Baden-Württemberg", "category": "schulferien"}
    assert bw.zeitfenster == [
        {
            "type": "school_holidays-easter",
            "year": 2028,
            "from": "2028-03-27",
            "to": "2028-04-08",
            "precision": "exact",
            "ics": False,
            "name": "Osterferien",
            "source_urls": [bw.quelle["url"]],
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


def test_store_merge_und_echte_zod_validierung(monkeypatch, tmp_path, config, raw_sample, erwartete_subjekte):
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjekte)
    monkeypatch.setattr(generic_source, "DATA_ROOT", tmp_path)

    ergebnisse = generic_source.extract(config, raw_sample, PARAMS)
    assert len(ergebnisse) == 2

    for ergebnis, erwartet in zip(ergebnisse, erwartete_subjekte):
        datei = store.lade_oder_erstelle(
            ergebnis.datei_pfad,
            ergebnis.subjekt["slug"],
            ergebnis.subjekt["category"],
        )
        store.merge_zeitfenster(datei, ergebnis.zeitfenster, ergebnis.replace_key)
        store.append_quelle(datei, ergebnis.quelle)

        validate.pruefe_subjekt_datei(datei)  # wirft ValidationError bei ungueltiger Form

        store.speichere(ergebnis.datei_pfad, datei)
        assert ergebnis.datei_pfad.exists()
        gespeichert = yaml.safe_load(ergebnis.datei_pfad.read_text(encoding="utf-8"))
        assert len(gespeichert["windows"]) == len(erwartet["ranges"])
        assert len(gespeichert["source"]) == 1
        for window in gespeichert["windows"]:
            assert window["source_urls"] == [ergebnis.quelle["url"]]

    # Zwei Subjekte landen in zwei getrennten Ordnern, nicht demselben.
    assert (tmp_path / "schulferien" / "bw" / "data.yaml").exists()
    assert (tmp_path / "schulferien" / "by" / "data.yaml").exists()


def test_replace_key_ersetzt_statt_zu_duplizieren(monkeypatch, tmp_path, config, raw_sample, erwartete_subjekte):
    """Zweiter Lauf fuer dasselbe Jahr darf keine Duplikate erzeugen - das ist
    der ganze Sinn von replace_key=("type", "year"). Also covers append_quelle's
    URL dedup: re-running the same source must not grow "sources"."""
    monkeypatch.setattr(generic_source, "extract_subjects", lambda text, hint: erwartete_subjekte)
    monkeypatch.setattr(generic_source, "DATA_ROOT", tmp_path)

    for _ in range(2):
        ergebnisse = generic_source.extract(config, raw_sample, PARAMS)
        for ergebnis in ergebnisse:
            datei = store.lade_oder_erstelle(
                ergebnis.datei_pfad,
                ergebnis.subjekt["slug"],
                ergebnis.subjekt["category"],
            )
            store.merge_zeitfenster(datei, ergebnis.zeitfenster, ergebnis.replace_key)
            store.append_quelle(datei, ergebnis.quelle)
            store.speichere(ergebnis.datei_pfad, datei)

    for erwartet in erwartete_subjekte:
        pfad = tmp_path / "schulferien" / erwartet["subject"]["slug"] / "data.yaml"
        gespeichert = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        assert len(gespeichert["windows"]) == len(erwartet["ranges"])
        assert len(gespeichert["source"]) == 1
        for window in gespeichert["windows"]:
            assert window["source_urls"] == [gespeichert["source"][0]["url"]]


def test_pruefe_subjekt_datei_lehnt_ungueltige_form_ab():
    with pytest.raises(validate.ValidationError):
        validate.pruefe_subjekt_datei({"subject": {"slug": "bw"}, "windows": []})
