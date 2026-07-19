# Wann-O-Meter

„Wann ist der beste Zeitpunkt fuer X?" - ein Kalender, auf den man geprüfte Zeitschichten legt.
Siehe [PLAN.md](./PLAN.md) fuer die Produktverfassung.

V1 = der **Ebenen-Kalender** (`/kalender`): jede Ebene einzeln hinzufuegbar und entfernbar -
Feiertage pro Bundesland (alle 16) oder Land (>200, ueber date-holidays), Schulferien pro
Bundesland UND Ferientyp (Sommer/Herbst/Weihnachten/Ostern/Pfingsten/Winter je einzeln), plus
Gemüsesaison. Overlay-Modus: beliebig viele Ebenen gleichzeitig, jede Kombination eine URL, jede
Ebene einzeln als ICS abonnierbar. Presets sind kuratierte, vorbelegte Kalender-URLs als eigene
Landingpages.

## Architektur: Definition vs. Materialisierung (PLAN.md Abschnitt 5.1)

- **Definitionsschicht** (`/data/{kategorie}/{subjekt}.yaml`): handgepflegte/Pipeline-Fakten im
  Zod-validierten Format aus `lib/schema.ts`. Schulferien (dekretiert, KMK, ein `typ` pro
  Ferienart wie `schulferien-sommer`) und Saisonkalender (dekretiert/erfahrungsbasiert, BZfE).
- **Berechnungsregeln** (`/lib`): Feiertage (jedes Land/Bundesland) und daraus abgeleitete
  Bruecktage-Fenster (nur DE) sind Code, nicht Daten (`lib/feiertage.ts`, `lib/urlaubsfenster.ts`).
  Feiertage sind eine eigene, laenderuebergreifende Kategorie (`lib/feiertage-kategorie.ts`),
  losgeloest von Urlaubsfenster/Bruecktage.
- **Materialisierung** (`lib/materialisierung.ts`): fuehrt beides zu konkreten Zeitfenstern pro
  Jahr zusammen, rollierend fuer das aktuelle Jahr + 2. Kalender-UI, Seiten, JSON und ICS
  konsumieren ausschliesslich diese materialisierte Schicht (`lib/subjekte.ts`,
  `lib/saisonkalender.ts`, `lib/feiertage-kategorie.ts`).

## Struktur

```text
/lib                 Plattformneutrales TypeScript: Zod-Schema, ISO-8601-Teilangaben-Parser,
                      Feiertage/Bruecktage-Berechnung, Materialisierung, ICS-Generator
/data/urlaubsfenster  Ein YAML pro Bundesland (alle 16): Schulferien-Fakten + Quellen/Lizenzen
/data/saisonkalender  Ein Ordner (data.yaml) pro Obst-/Gemüsesorte: wiederkehrende Saisonfenster
/data/presets         Kuratierte Kalender-URLs (Region + aktive Ebenen)
/pipeline             Python: amtliche Quellen -> LLM-Extraktion -> YAML auf Branch -> PR
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

## Pipeline (neue Schulferien-Daten vorschlagen)

```sh
cd pipeline
uv run python -m core.runner schulferien_kmk --jahr 2028
```

Kreislauf: Fetch -> LLM-Extraktion -> Validierung gegen `lib/schema.ts` -> YAML-Aenderung auf
einem Branch -> Pull Request. GitHub ist die Freigabe-Queue - kein Auto-Merge, kein eigenes
Review-Tool. Siehe `pipeline/README.md` fuer die Pipeline-Struktur (core/sources/tools) und die
Extraktions-Strategie pro Quelle (PLAN.md Abschnitt 7).

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
