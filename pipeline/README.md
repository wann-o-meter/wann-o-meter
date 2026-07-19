# Wann-Plattform Admin Dashboard

FastAPI + Jinja2 SSR Admin interface for the focused crawler + scraper.

## Features

- **Focused Crawler**: Only crawls domains you specify. Automatically avoids Wikipedia, Google, Facebook, Instagram, etc.
- **Smart Scoring**: Ranks pages by likelihood of containing seasonal/event data using keywords + date patterns + content length.
- **Manual Review Queue**: See every discovered page with title, preview, and relevance score. Accept or reject with one click.
- **Scraper Integration**: Accepted pages appear in a queue ready to be processed by the clean `scraper.py`.
- **Live Updates**: HTMX-powered dashboard (no full page reloads needed).

## Run the Admin Dashboard

```bash
cd pipeline
uv run main.py
```

Then open: **http://localhost:8000**

## Tests

```bash
cd pipeline
uv run pytest tests/ -v
```

Fixture-based per source (`fixtures/{source_id}/raw_sample... + erwartet.yaml`) - see
`tests/test_schulferien_kmk.py` for the pattern. LLM calls are mocked with the fixture's
expected output; everything deterministic around them (store merge, real Zod validation) is
genuinely exercised.

## How to use

1. Go to the dashboard
2. Enter seed domains (one per line), e.g.:
   ```
   tourismus-bayern.de
   schloesser.bayern.de
   stuttgart.de/veranstaltungen
   ```
3. Click **Start Crawler**
4. Watch pages appear in the table with relevance scores
5. Click **Accept** on useful pages → they move to the "Ready for Scraper" section
6. Click **Run Scraper** on accepted pages → output is saved to `pipeline/scraped/` and shown in the
   "Scraped" table
7. Fill in a title, optional comma-separated tags, and a license, then click **Create Page** →
   writes `data/seiten/{slug}/data.yaml` + `page.yaml`, picked up by the Astro build as a page under
   `/seiten/{slug}/`

## Generic pages (`/seiten/`)

Each accepted scrape picks its own category at creation time - `data/{category}/{slug}/` maps
directly to `/{category}/{slug}/`, the same way `data/saisonkalender/apfel/data.yaml` maps to
`/saisonkalender/apfel/`. There's no generic wrapper route: a page's URL reflects its actual topic
(e.g. `/astronomie/...`), not a meaningless catch-all like `/pages/...`. `RESERVED_CATEGORIES` in
both `lib/pages.ts` and `main.py` rejects a category name that would collide with an existing site
section (`urlaubsfenster`, `saisonkalender`, `feiertage`, etc.).

Title/description/tags live in `page.yaml`, right next to the facts in `data.yaml`
(`lib/pages.ts` renders both dynamically). This is a deliberate edge case against the platform's own
rule that every page must be a genuine data answer, not content-farm fodder (see PLAN.md section 2)
- noted here rather than silently ignored, but built anyway per direct instruction.

The two-file split lets "Create Page" be re-run safely: `data.yaml` is always rewritten from the
latest scrape, `page.yaml` is only written the first time, so any title/description/tags edits you
make by hand survive a later re-scrape of the same URL. Re-running "Create Page" for a URL that
already has a page updates that same folder instead of creating a duplicate (matched by
`data.yaml`'s `source.url`, not by title or category - so an accidental category typo on a re-run
won't fork the page into a second location).

All pages across all categories are searchable by title/tag at `/themen/` (client-side substring
filter, no framework - Pagefind per PLAN.md section 7 is explicitly deferred until >50 pages).

This system is scoped to newly-accepted sources only, for now - Feiertage/Urlaubsfenster/
Saisonkalender keep their own bespoke code (Feiertage in particular has no YAML backing at all, it's
computed entirely from a library call) and aren't migrated onto this generic system yet.

## Focused Crawler Logic

- Only stays within the domains you seeded
- Blacklists major generic platforms
- Scores pages higher when they contain German seasonality keywords (`Saison`, `Veranstaltung`, `Öffnungszeiten`, dates, etc.)
- Politeness delay built in

## Pipeline-Struktur

```text
pipeline/
  core/            gemeinsame Maschinerie, einmal geschrieben, nie kopiert
    fetch.py       HTTP mit Timeout/Retry (auch von scraper.py genutzt)
    types.py       ExtraktionsErgebnis + SourceAdapter - der ganze Adapter-Vertrag
    extraction.py  LLM-Extraktion, u.a. extract_subjects() - eine Quelle kann
                   mehrere Subjekte (z.B. je Bundesland) in einem Abruf enthalten;
                   das Modell entdeckt den Split aus dem echten Seiteninhalt
    generic_source.py  fetch -> extract_subjects -> ExtraktionsErgebnis[] rein aus
                   sources.yaml-Konfiguration - der Normalfall fuer strategie: llm,
                   ohne jedes sources/<id>.py
    store.py       YAML laden/anlegen, Merge nach replace_key, Quelle anhaengen
    validate.py    prueft gegen lib/schema.ts (siehe unten) - VOR dem PR, nicht danach
    publish.py     Branch + Commit + PR
    runner.py      orchestriert: fetch -> extract (adapter ODER generic_source)
                   -> validate -> merge -> publish, ein PR fuer alle Subjekte
  sources/         Escape Hatch: nur fuer eine Quelle, die wirklich bespoke Code
                   braucht (z.B. Strategie 1/Parser). Fuer strategie: llm reicht
                   ein sources.yaml-Eintrag, siehe unten - aktuell leer.
  tools/           einmalige Batch-Skripte - nutzen core/, aber laufen
    dwd_klima.py   ausserhalb des Source-Lebenszyklus (kein PR, kein sources.yaml-Eintrag)
  sources.yaml     Registry: URL, Kategorie, Lizenz, Rhythmus, Strategie, und fuer
                   strategie: llm ein extraction_hint (Subjekt-Vokabular/-Format)
                   pro Quelle
  fixtures/        ein echtes Roh-Sample + erwartetes Ergebnis pro Quelle
  main.py          Crawler-Dashboard (Discovery fuer Strategie 2/3, siehe unten)
  scraper.py       Content-sniffing Dispatcher, den main.py und tools/ teilen
```

Eine Quelle hinzufuegen (strategie: llm, der Normalfall): `sources.yaml` einen
Eintrag geben (`kategorie`, `url`, `lizenz`, `rhythmus`, `strategie: llm`,
`extraction_hint` - was die Seite behandelt, ob/wie sie in mehrere Subjekte
zerfaellt, welches Slug-Vokabular gilt), fertig. Kein Python noetig -
`core/generic_source.py` uebernimmt fetch/extract, `core/runner.py`
Merge/Validierung/PR. Nur wenn eine Quelle wirklich bespoke Logik braucht
(Strategie 1/Parser), kommt ein `sources/<id>.py` mit `id`, `kategorie`,
`extract(raw, params) -> ExtraktionsErgebnis` dazu - `core/runner.py`
bevorzugt ein vorhandenes Adapter-Modul, faellt sonst auf `generic_source.py`
zurueck.

```bash
cd pipeline
uv run python -m core.runner schulferien_kmk --jahr 2028
```

Ein Lauf deckt jetzt alle 16 Bundeslaender ab (das Modell erkennt den Split
aus der einen KMK-Seite, die sie ohnehin alle auflistet) statt 16 einzelner
Aufrufe mit `--bundesland`/`--bundesland-name` - ein PR fuer alle Subjekte,
mit der gefundenen Subjekt-Anzahl im PR-Text zum Gegenchecken.

**Schema-Drift vermeiden:** `core/validate.py` validiert NICHT gegen ein exportiertes
JSON-Schema (`zod-to-json-schema` wurde probiert, ist unter Zod v4 aber leer/kaputt -
selbst ein triviales Schema exportiert `{}`). Stattdessen ruft es `lib/validate-cli.ts`
auf, das direkt `subjektDateiSchema` aus `lib/schema.ts` importiert - dieselbe
Zod-Instanz, die der Astro-Build nutzt. Null Drift-Risiko, ein Subprocess-Call.

## Welche Quellen laufen wo?

Entschieden pro Quelle, nicht per Pipeline-weiter Philosophie (siehe PLAN.md
Abschnitt 7 fuer die volle Entscheidungsregel Homogenitaet × Volumen):

- **`sources.yaml` + `core/runner.py`** (dieser Ordner): wiederkehrende Quellen mit
  bekannter URL, die den vollen fetch → extract → validate → PR-Lebenszyklus
  durchlaufen. Aktuell: Schulferien (LLM-Extraktion aus der KMK-Ferienuebersicht,
  Strategie 2, ueber `core/generic_source.py` - kein `sources/schulferien_kmk.py`
  mehr). `sources/` bleibt als Escape Hatch fuer eine Quelle, die wirklich
  bespoke Code braucht.
- **Dieses Dashboard (`main.py`) + `scraper.py`s Content-Sniffing** (Directory
  Listings, delimited Text, ZIP, HTML): zum *Entdecken* von Seiten, deren Form
  man noch nicht kennt - ein Portal mit vielen gleichfoermigen Seiten
  (Gemüsesaison-Verbandsseiten). Accept-Queue → LLM-Extraktion → PR-Review.
- **`tools/`**: einmalige, deterministische Batch-Skripte fuer bekannte, hoch
  strukturierte Quellen (DWD-Klimadaten). Kein LLM, kein Accept-Flow, kein
  `sources.yaml`-Eintrag - das Skript fetcht die bekannte URL-Struktur korrekt
  oder es tut es nicht. `extraktion: parser` in der resultierenden YAML.
- **`harvest/` + `config/registries.yaml`**: entity-first for a large, known
  set of entities (e.g. all German universities) instead of one curated
  source - see below.

## Harvest pipeline (entity-first)

For a finite entity set (currently: `university_de`), find each entity's
target page, extract dates, and publish. Only Stage 1 (`registry`) is
implemented so far:

```bash
cd pipeline
uv run python -m harvest.cli registry university_de
```

Writes `pipeline/data/registries/university_de.json` (one row per university:
`entity_id`, `domain`, `wikidata_id`, `region`, ...), deduplicated by domain,
sorted by `entity_id`. Deliberately under `pipeline/data/`, not repo-root
`data/` - every folder there is read by `lib/pages.ts` as a page category, a
`registries/` folder would collide with that.

Later stages (discover/probe/extract/validate/publish/maintain, see
`config/registries.yaml`'s `target_kinds`) don't exist yet.

## Next Steps / Integration

- The accepted URLs can be fed directly into `scraper.py`
- You can extend `calculate_content_score()` with more sophisticated rules or even call an LLM for better filtering.
- Add persistent storage (SQLite) if you want to keep history across restarts.