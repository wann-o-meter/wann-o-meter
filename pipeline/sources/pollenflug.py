#!/usr/bin/env python3
"""
Pollenflugkalender (apotheken-umschau.de, Daten von wetter.com): einmaliges,
deterministisches Batch-Skript - wie tools/dwd_klima.py, kein Crawler, kein
LLM. Die Seite nennt selbst "Durchschnittswerte aus vergangenen Jahren", es
gibt also nichts periodisch neu abzuholen (deshalb kein sources.yaml-Eintrag,
siehe deren Kopfkommentar).

Warum ueberhaupt ein Parser: die eigentliche Information steckt NICHT im Text,
sondern in der CSS-Klasse jeder Monatszelle -

    <span class="c1">Mai</span><span class="c3">Juni</span>...<span class="c2">Sep.</span>

c1/c2/c3 sind die drei Legendenstufen, c0 ist ein nicht hervorgehobener Monat.
Jeder LLM-Weg (extract_dated_events, extract_season ueber clean_markdown)
wirft die Klassen weg und sieht nur noch "Beifuss Mai Juni Juli Aug. Sep.
Okt." - keine Daten, keine Stufen. Kein Prompt repariert das.

Schreibt data/pollenflug/<pflanze>/{data.yaml,page.yaml}, ein Subjekt pro
Pflanze (39 Stueck). Nutzung (von pipeline/ aus):

    python -m tools.pollenflug [--dry-run]
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from bs4 import BeautifulSoup

from core.fetch import decode_text, fetch_bytes

URL = "https://www.apotheken-umschau.de/krankheiten-symptome/allergien/pollenflugkalender-vorhersage-pollenflug-942541.html"
KATEGORIE = "pollenflug"
DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / KATEGORIE

# Woertlich aus dem "tabelle-legend"-Block der Seite. c0 fehlt hier bewusst -
# ein nicht hervorgehobener Monat gehoert zu KEINEM Fenster.
LEVELS = {
    "c1": ("pollen_possible", "Vorkommen möglich"),
    "c2": ("pollen_pre_post_bloom", "Vor- / Nachblütezeit"),
    "c3": ("pollen_main_bloom", "Hauptblütezeit"),
}

# Tippfehler der Quelle. "Elbe" ist ein Fluss, gemeint ist die Eibe - sonst
# entsteht eine oeffentliche Seite "Elbepollen".
CORRECTIONS = {"Elbe": "Eibe"}

SOURCE = {
    "url": URL,
    # ponytail: tos_checked ist die ehrlichste Enum-Option (kommerzieller
    # Verlag, Daten von wetter.com) - vor dem Commit einmal gegen deren
    # Nutzungsbedingungen pruefen.
    "license": "tos_checked",
    "license_note": (
        "Pollenflugkalender der Apotheken Umschau, Datenbasis wetter.com. "
        "Durchschnittswerte aus vergangenen Jahren, keine Vorhersage für ein "
        "konkretes Jahr."
    ),
    "retrieved_at": date.today().isoformat(),
    "extraction": "parser",
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    for umlaut, ascii_form in {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}.items():
        text = text.replace(umlaut, ascii_form)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def level_of(span: Any) -> Optional[str]:
    for cls in span.get("class") or []:
        if cls in LEVELS:
            return cls
    return None


def windows(levels: List[Optional[str]]) -> List[Dict[str, Any]]:
    """Ein Fenster pro ZUSAMMENHAENGENDEM Lauf gleicher Stufe, nicht eines pro
    Stufe: die Stufen einer Pflanze sind nicht je ein einziger Block (Beifuss
    ist c1 im Mai UND nochmal im Oktober, dazwischen c3/c2). Ein min/max pro
    Stufe wuerde "Vorkommen möglich" ueber die ganze Saison schmieren.

    ponytail: ein Lauf ueber den Jahreswechsel bleibt zwei Fenster - keine
    Pflanze auf dieser Seite wickelt sich ums Jahr, und rawWindowSchema
    erlaubt --12..--02, falls das je eine tut.
    """
    result = []
    start = 0
    for month in range(1, 13):
        current = levels[month - 1]
        if month < 12 and levels[month] == current:
            continue
        if current:
            type_, name = LEVELS[current]
            result.append({
                "type": type_,
                "name": name,
                "year": None,
                "from": f"--{start + 1:02d}",
                "to": f"--{month:02d}",
                "precision": "approximate",
                "ics": False,
            })
        start = month
    return result


def parse(html: str) -> List[Dict[str, Any]]:
    rows = BeautifulSoup(html, "html.parser").select("div.pollenflug-tabellenzeile")
    if not rows:
        raise SystemExit("Keine div.pollenflug-tabellenzeile gefunden - Seitenlayout geaendert?")

    plants = []
    for row in rows:
        cells = row.find_all("span", recursive=False)
        # Erste Zelle ist der Pflanzenname, dann genau eine Zelle pro Monat.
        # Die Kopfzeile der Tabelle (Monatsnamen, keine Pflanze) hat eine leere
        # erste Zelle und faellt allein dadurch raus.
        if len(cells) != 13:
            continue
        name = cells[0].get_text(strip=True)
        if not name:
            continue
        name = CORRECTIONS.get(name, name)
        plants.append({"name": name, "windows": windows([level_of(c) for c in cells[1:]])})
    return plants


def write(plants: List[Dict[str, Any]]) -> None:
    for plant in plants:
        slug = slugify(plant["name"])
        directory = DATA_ROOT / slug
        directory.mkdir(parents=True, exist_ok=True)
        dump(directory / "data.yaml", {
            "subject": {"slug": slug, "name": f"{plant['name']}pollen", "category": KATEGORIE},
            "windows": plant["windows"],
            "source": SOURCE,
        })
        dump(directory / "page.yaml", {
            "title": f"{plant['name']}pollen",
            "description": f"Pollenflugkalender für {plant['name']} - wann die Hauptblütezeit ist "
                           "und ab wann mit Pollen zu rechnen ist.",
        })
    # Nur beim ersten Lauf - sonst wuerde ein Re-Run einen von Hand
    # ueberarbeiteten Kategorietext ueberschreiben.
    category = DATA_ROOT / "_category.yaml"
    if not category.exists():
        dump(category, {
            "name": "Pollenflugkalender",
            "description": "Wann welche Pollen fliegen - Vor-, Haupt- und Nachblütezeit je Pflanze.",
        })


def dump(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def demo() -> None:
    """Der eine Check, der faellt, wenn die Lauf-Logik bricht."""
    beifuss = ["c0"] * 4 + ["c1", "c3", "c3", "c3", "c2", "c1"] + [None, None]
    got = [(w["type"], w["from"], w["to"]) for w in windows([lv if lv != "c0" else None for lv in beifuss])]
    assert got == [
        ("pollen_possible", "--05", "--05"),
        ("pollen_main_bloom", "--06", "--08"),
        ("pollen_pre_post_bloom", "--09", "--09"),
        ("pollen_possible", "--10", "--10"),
    ], got
    assert slugify("Gänsefuss") == "gaensefuss"
    print("ok")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="nur ausgeben, nichts schreiben")
    parser.add_argument("--demo", action="store_true", help="Selbsttest der Lauf-Logik")
    args = parser.parse_args()

    if args.demo:
        demo()
        return 0

    print(f"[pollenflug] Fetching {URL}", file=sys.stderr)
    raw, _ = fetch_bytes(URL)
    html = decode_text(raw)
    if not html:
        raise SystemExit("Antwort liess sich nicht als Text dekodieren")

    plants = parse(html)
    print(f"[pollenflug] {len(plants)} Pflanzen, "
          f"{sum(len(p['windows']) for p in plants)} Fenster", file=sys.stderr)
    if args.dry_run:
        for plant in plants:
            spans = ", ".join(f"{w['from']}..{w['to']} {w['type']}" for w in plant["windows"])
            print(f"{slugify(plant['name']):>15}  {spans}")
        return 0

    write(plants)
    print(f"[pollenflug] geschrieben nach {DATA_ROOT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
