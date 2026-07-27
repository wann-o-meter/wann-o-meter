# Wann-O-Meter

„Wann ist der beste Zeitpunkt fuer X?" - ein Kalender, auf den man geprüfte Zeitschichten legt,
mit Quellenangabe statt generiertem Text. Jede Seite und jede Ebene beantwortet eine Frage nach
einem Datum oder Zeitraum; keine zeitlosen Ratgeber-Artikel.

Der **Ebenen-Kalender** (`/kalender`): jede Ebene einzeln hinzufuegbar und entfernbar -
Feiertage pro Bundesland (alle 16) oder Land (>200, ueber date-holidays), Schulferien pro
Bundesland UND Ferientyp (Sommer/Herbst/Weihnachten/Ostern/Pfingsten/Winter je einzeln), plus
Gemüsesaison. Overlay-Modus: beliebig viele Ebenen gleichzeitig, jede Kombination eine URL, jede
Ebene einzeln als ICS abonnierbar. Presets sind kuratierte, vorbelegte Kalender-URLs als eigene
Landingpages.

## Architektur: Definition vs. Materialisierung

- **Definitionsschicht** (`/data/{kategorie}/{subjekt}/data.yaml`): handgepflegte/Pipeline-Fakten
  im Zod-validierten Format aus `lib/schema.ts`, je Subjekt begleitet von `page.yaml` (Titel) und
  `meta.toml` (Modus + Quellen). Schulferien (dekretiert, KMK, ein `typ` pro Ferienart wie
  `schulferien-sommer`) und Saisonkalender (dekretiert/erfahrungsbasiert, BZfE).
- **Herkunft** (`/data/_sources/{id}.yaml`): eine Datei pro Upstream. Nicht im Subjektordner,
  weil Quelle und Subjekt in beide Richtungen n:m sind - eine KMK-Seite speist 16 Subjekte, zwei
  NASA-Kataloge speisen eine Seite. Der Unterstrich haelt den Ordner aus dem Kategorie-Walk.
- **Berechnungsregeln** (`/lib` + `data/{kategorie}/generator.ts`): Feiertage (jedes
  Land/Bundesland) und daraus abgeleitete Bruecktage-Fenster (nur DE) sind Code, nicht Daten
  (`lib/holidays.ts`, `lib/vacation-windows.ts`, `data/feiertage/generator.ts`,
  `data/urlaubsfenster/generator.ts`).
- **Materialisierung** (`lib/materialization.ts`): fuehrt beides zu konkreten Zeitfenstern pro
  Jahr zusammen, rollierend fuer das aktuelle Jahr + 2. Kalender-UI, Seiten, JSON und ICS
  konsumieren ausschliesslich diese materialisierte Schicht (ueber `lib/pages.ts`, das ein
  einziges Seitenmodell fuer alle Kategorien liefert).

## Struktur

```text
/lib                 Plattformneutrales TypeScript: Zod-Schema, ISO-8601-Teilangaben-Parser,
                      Feiertage/Bruecktage-Berechnung, Materialisierung, ICS-Generator
/data/_sources        Eine YAML pro Upstream-Quelle (Crawler- und Batch-Quellen)
/data/schulferien     Ein Ordner pro Bundesland (alle 16): Schulferien-Fakten + Quellen/Lizenzen
/data/saisonkalender  Ein Ordner (data.yaml) pro Obst-/Gemüsesorte: wiederkehrende Saisonfenster
/data/urlaubsfenster  generator.ts: Bruecktage aus Feiertagen + Schulferien, kein YAML
/data/presets         Kuratierte Kalender-URLs (Region + aktive Ebenen)
/pipeline             Python: Quellen -> Extraktion -> staging/ -> lokales Review -> data/
/src/components        Kalender.vue - die eine Vue-Insel (Ebenen-Picker, URL-als-Zustand)
/src/pages            Astro-Seiten, /api/v1/-JSON-Endpunkte, /feeds/-ICS-Endpunkte
```

Feiertage brauchen kein YAML (reiner Code) - `/feiertage` deckt alle 16 Bundeslaender plus alle
von `date-holidays` unterstuetzten Laender (>200) ab, jedes einzeln als Kalender-Ebene waehlbar.

## Kommandos

| Command         | Aktion                                                              |
| :-------------- | :------------------------------------------------------------------- |
| `bun install`    | Dependencies installieren                                            |
| `bun run dev`    | Dev-Server auf `localhost:4321`                                      |
| `bun run build`  | Production-Build nach `./dist/` (inkl. Zod-Validierung der Zeitfenster) |
| `bun run test`   | Vitest-Suite fuer `/lib`                                              |

## Pipeline

```sh
cd pipeline
uv run wom sources                            # welche Quellen es gibt
uv run wom run schulferien_kmk --jahr 2028    # Quelle abrufen, Kandidaten stagen
uv run wom review                             # Review-UI auf http://localhost:8000
```

Kreislauf: Fetch -> Extraktion -> Validierung gegen `lib/schema.ts` -> `pipeline/staging/` ->
lokales Review -> `data/`.

**Das lokale Review ist die Freigabe, GitHub ist Merge-Gate und Audit-Log** - zwei verschiedene
Dinge. Ein LLM kann raten, deshalb sieht ein Mensch jeden Kandidaten, bevor er in `data/`
landet; bei 300 Kandidaten pro Lauf ist das eine eigene App (`pipeline/review/`) und keine
PR-Diskussion. Der Scraper schreibt **nie** direkt nach `data/`. Was freigegeben wurde, wird
anschliessend committet und gepusht wie jede andere Aenderung auch - der PR dokumentiert sie,
er entscheidet sie nicht.

Siehe `pipeline/README.md` fuer die Pipeline-Struktur (core/sources/review) und die
Extraktions-Strategie pro Quelle.

## Bekannte Datenluecke

Schulferien sind fuer alle 16 Bundeslaender fuer 2026 und 2027 hinterlegt, verifiziert gegen die
offiziellen KMK-.ics-Kalender. 2028 hat deshalb nur code-berechnete Bruecktage-/Feiertags-Fenster
ohne Schulferien-Abgleich - besser eine ehrliche Luecke als geratene Daten (siehe pipeline/).

## Mitmachen & Lizenz

Neue Quelle vorschlagen (per URL) oder Daten direkt als YAML beisteuern: siehe
[CONTRIBUTING.md](./CONTRIBUTING.md). Code steht unter MIT ([LICENSE](./LICENSE)), der
kuratierte Datensatz unter `/data` unter CC BY 4.0 ([data/LICENSE](./data/LICENSE)).

## Deploy

Domain: `wannometer.de` (siehe `astro.config.mjs`, `public/CNAME` fuer GitHub Pages). Weiterleitungen
von `wann-o-meter.de` und `wann-o-meter.github.io` sind vorgesehen, muessen aber auf DNS-/Hosting-Ebene
eingerichtet werden (Registrar-Redirect bzw. GitHub-Pages-Einstellungen) - liegt ausserhalb dieses Repos.
