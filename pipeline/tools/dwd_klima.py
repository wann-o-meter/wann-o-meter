#!/usr/bin/env python3
"""
DWD Klimadaten: einmaliges, deterministisches Batch-Skript (Strategie 1,
siehe PLAN.md Abschnitt 7 / pipeline/README.md). Kein Crawler, kein LLM -
opendata.dwd.de liefert ein bekanntes, dokumentiertes Schema; das bei jedem
Abruf neu per Modell "erkennen" zu lassen waere teurer, langsamer und
unsicherer als dieses Skript.

Holt taegliche Klimawerte fuer eine Station, parst sie und aggregiert sie zu
historischen Wochen-Bins (min/mittel/max Temperatur, mittlerer Niederschlag) -
die Rohform fuer "vorberechnete historische Wochen-Bins pro Region" aus
PLAN.md Abschnitt 4.5, FALLS die Klimatologie-Ebene je gebaut wird.

Schreibt bewusst NICHT nach /data - das waere eine vierte Kalender-Ebene, und
die gewaehlte Fleiss-Ebene fuer V1 ist Gemuesesaison (PLAN.md Abschnitt 8).
Dieses Skript ist die getestete Grundlage, falls das spaeter doch gebaut wird
(PLAN.md Abschnitt 10, Ausbau-Vertikale 2).

Nutzung (von pipeline/ aus):
    python -m tools.dwd_klima <station_id> [--jahre-zurueck N] [--out output.json]

Beispiel:
    python -m tools.dwd_klima 00044
"""

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from scraper import decode_text, fetch_bytes, parse_directory_listing

BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/historical/"

# DWD-Feldnamen -> unser Vokabular (nur die Felder, die wir wirklich nutzen).
# Vollstaendige Spaltenbeschreibung: BESCHREIBUNG_obsgermany-climate-daily-kl_de.pdf
# im selben Verzeichnis wie die Stations-ZIPs.
FELD_TEMPERATUR_MITTEL = "TMK"  # Tagesmittel der Lufttemperatur 2m (°C)
FELD_NIEDERSCHLAG = "RSK"       # Tagesniederschlagshoehe (mm)
FEHLWERT = "-999"


def find_station_zip_url(station_id: str) -> Optional[str]:
    """Sucht in der historical/-Verzeichnisliste nach der ZIP-Datei einer Station."""
    content, _ = fetch_bytes(BASE_URL)
    html = decode_text(content) or ""
    pattern = re.compile(rf"tageswerte_KL_{station_id}_\d+_\d+_hist\.zip$")
    for entry in parse_directory_listing(html):
        if pattern.match(entry["href"]):
            return BASE_URL + entry["href"]
    return None


def parse_produkt_datei(text: str) -> List[Dict[str, str]]:
    """DWD-Spalten sind leerzeichen-gepolstert (z.B. '  TMK'), Werte auch -
    csv.DictReader trennt korrekt an ';', wir stripen selbst nach."""
    reader = csv.DictReader(text.splitlines(), delimiter=";")
    reader.fieldnames = [f.strip() for f in (reader.fieldnames or [])]
    return [{k: v.strip() for k, v in row.items() if k} for row in reader]


def parse_station_zip(content: bytes) -> List[Dict[str, str]]:
    """Extrahiert die produkt_klima_tag_*.txt (die eigentlichen Tageswerte,
    nicht die 30 Metadaten-Begleitdateien) aus der ZIP und parst sie."""
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        produkt_name = next((n for n in zf.namelist() if n.startswith("produkt_klima_tag")), None)
        if not produkt_name:
            raise ValueError("Keine produkt_klima_tag_*.txt in der ZIP gefunden")
        text = decode_text(zf.read(produkt_name))
        if text is None:
            raise ValueError(f"{produkt_name} nicht dekodierbar")
    return parse_produkt_datei(text)


def zu_float(wert: str) -> Optional[float]:
    try:
        f = float(wert)
    except ValueError:
        return None
    return None if wert == FEHLWERT else f


def iso_woche(datum_str: str) -> str:
    """MESS_DATUM ist YYYYMMDD -> ISO-Wochennummer '01'..'53', jahresunabhaengig
    (das ist der Sinn eines historischen Wochen-Bins: ueber alle Jahre gemittelt)."""
    d = date(int(datum_str[:4]), int(datum_str[4:6]), int(datum_str[6:8]))
    return f"{d.isocalendar().week:02d}"


def wochen_bins(rows: List[Dict[str, str]], jahre_zurueck: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """Aggregiert Tageswerte zu historischen Wochen-Bins."""
    grenzjahr = date.today().year - jahre_zurueck if jahre_zurueck else None
    temps_pro_woche: Dict[str, List[float]] = defaultdict(list)
    regen_pro_woche: Dict[str, List[float]] = defaultdict(list)

    for row in rows:
        datum_str = row.get("MESS_DATUM", "")
        if len(datum_str) != 8 or not datum_str.isdigit():
            continue
        if grenzjahr and int(datum_str[:4]) < grenzjahr:
            continue
        woche = iso_woche(datum_str)
        tmk = zu_float(row.get(FELD_TEMPERATUR_MITTEL, ""))
        if tmk is not None:
            temps_pro_woche[woche].append(tmk)
        rsk = zu_float(row.get(FELD_NIEDERSCHLAG, ""))
        if rsk is not None:
            regen_pro_woche[woche].append(rsk)

    bins = {}
    for woche in sorted(temps_pro_woche):
        temps = temps_pro_woche[woche]
        regen = regen_pro_woche.get(woche, [])
        bins[woche] = {
            "temperatur_min": round(min(temps), 1),
            "temperatur_mittel": round(sum(temps) / len(temps), 1),
            "temperatur_max": round(max(temps), 1),
            "niederschlag_mittel_mm": round(sum(regen) / len(regen), 1) if regen else None,
            "beobachtungsjahre": len(temps),
        }
    return bins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("station_id", help="DWD Stations-ID, z.B. 00044")
    parser.add_argument("--jahre-zurueck", type=int, default=30, help="Nur die letzten N Jahre beruecksichtigen (default: 30, WMO-Normalperiode)")
    parser.add_argument("--out", help="Ausgabedatei (JSON). Ohne Angabe: stdout")
    args = parser.parse_args()

    station_id = args.station_id.zfill(5)
    print(f"[dwd] Suche ZIP fuer Station {station_id} ...", file=sys.stderr)
    zip_url = find_station_zip_url(station_id)
    if not zip_url:
        print(f"[dwd] Keine Station {station_id} in {BASE_URL} gefunden.", file=sys.stderr)
        return 1

    print(f"[dwd] Lade {zip_url}", file=sys.stderr)
    content, _ = fetch_bytes(zip_url)
    rows = parse_station_zip(content)
    print(f"[dwd] {len(rows)} Tageswerte geparst, aggregiere zu Wochen-Bins ...", file=sys.stderr)

    bins = wochen_bins(rows, jahre_zurueck=args.jahre_zurueck)
    result = {
        "station_id": station_id,
        "quelle_url": zip_url,
        "jahre_zurueck": args.jahre_zurueck,
        "wochen_bins": bins,
    }

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[dwd] Geschrieben nach {args.out}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
