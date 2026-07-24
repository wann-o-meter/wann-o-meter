# Wann-Plattform Admin Dashboard

FastAPI + Jinja2 SSR admin interface for the scoped crawler + review workflow.

## Features

- **Scoped Crawler**: each source is a config file (`config/crawl_sources/<id>.yaml` -
  seed URL, allowed domains, path prefix, max depth, formats, category). Add one from the
  dashboard by pasting just the seed URL - ID/domain/category are derived from it, with an
  Advanced section to override any of them - or hand-write the YAML file directly. Delete
  removes only the config file - review-state history and anything already written to
  `data/` are kept, so re-adding the same source later picks its history back up. Respects
  robots.txt and a per-domain rate limit.
- **Staging + diff-based re-crawling**: every crawl's fetched documents and extracted
  candidates land in `staging/`, diffed against `review-state/` - already-approved/modified
  candidates auto-wave-through on a later run (with `last_verified` re-stamped), rejected ones
  stay silently dropped, only genuinely new/changed candidates reach a human.
- **Review workflow**: approve/modify/reject a candidate next to its source document snapshot.
  Approved/modified candidates write straight to `data/` - no PR-per-run; you commit/push
  yourself, like any other local change.
- **ICS as a deterministic path**: an `.ics` feed is parsed directly into windows (RRULE
  preserved verbatim, no LLM call) - the same staging/review/diff flow as everything else.
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

1. Go to **Crawl Sources**
2. Paste a seed URL and click **Add Source** (or open **Advanced options** to override the
   derived ID, category, allowed domains, path prefix, depth, formats, or schedule) - this
   writes `config/crawl_sources/<id>.yaml`
3. Click **Run** on that source - it crawls within its configured scope, extracts events from
   every fetched document, and stages one candidate per event under `pipeline/staging/`
4. Go to **Review** - candidates with no prior decision for their content are waiting there,
   shown next to a snapshot of the document they came from. Approve, modify, or reject each one
   - approve/modify write straight to `data/{category}/{slug}/data.yaml` (+ `page.yaml` the first
   time); reject just records the decision so it isn't requeued
5. Re-running a source later only surfaces genuinely new or changed candidates - anything
   matching a prior decision (by content, not by document) auto-waves-through (re-stamping
   `last_verified`) or stays silently dropped if previously rejected
6. Commit and push `data/**/*.yaml` + `pipeline/review-state/**/*.yaml` yourself, like any other
   local change - there's no more per-run PR

## Generic pages (`/seiten/` and beyond)

Every approved/modified candidate picks its own category on review - `data/{category}/{slug}/`
maps directly to `/{category}/{slug}/`, the same way `data/saisonkalender/apfel/data.yaml` maps to
`/saisonkalender/apfel/`. There's no generic wrapper route: a page's URL reflects its actual topic
(e.g. `/veranstaltungen/...`), not a meaningless catch-all like `/pages/...`. `RESERVED_CATEGORIES`
in both `lib/pages.ts` and `main.py` rejects a category name that would collide with an existing
site section (`urlaubsfenster`, `saisonkalender`, `feiertage`, etc.).

Title/description/tags live in `page.yaml`, right next to the facts in `data.yaml`
(`lib/pages.ts` renders both dynamically). This is a deliberate edge case against the platform's own
rule that every page must be a genuine data answer, not content-farm fodder (see PLAN.md section 2)
- noted here rather than silently ignored, but built anyway per direct instruction.

The two-file split lets a source be re-run safely: `data.yaml` is merged from the latest
extraction (`core/store.py`'s replace_key + date-range dedup), `page.yaml` is only written the
first time, so any title/description/tags edits you make by hand survive a later re-run.

All pages across all categories are searchable by title/tag at `/themen/` (client-side substring
filter, no framework - Pagefind per PLAN.md section 7 is explicitly deferred until >50 pages).

This system is scoped to crawled/harvested sources only, for now - Feiertage/Urlaubsfenster/
Saisonkalender keep their own bespoke code (Feiertage in particular has no YAML backing at all, it's
computed entirely from a library call) and aren't migrated onto this generic system yet.

## Pipeline-Struktur

```text
pipeline/
  core/                gemeinsame Maschinerie, einmal geschrieben, nie kopiert
    fetch.py           HTTP mit Timeout/Retry (auch von scraper.py genutzt)
    types.py           ExtraktionsErgebnis + SourceAdapter - der ganze Adapter-Vertrag
    extraction.py      LLM-Extraktion, u.a. extract_subjects()/extract_season() - eine
                       Quelle kann mehrere Subjekte in einem Abruf enthalten; das Modell
                       entdeckt den Split aus dem echten Seiteninhalt
    generic_source.py  fetch -> extract_subjects/extract_season -> ExtraktionsErgebnis[]
                       rein aus sources.yaml-Konfiguration - fuer strategie: llm/llm_season
    ics.py             deterministische ICS-Extraktion (RRULE, all-day, Zeitzonen) - kein LLM
    crawl_config.py    laedt config/crawl_sources/*.yaml -> CrawlSource
    crawler.py         BFS innerhalb Domain/Pfad-Scope, robots.txt, Rate-Limit
    crawl_runner.py    Pendant zu runner.py fuer Scoped-Crawler-Quellen: crawl -> extract
                       -> stage -> diff -> write/queue
    staging.py         legt jeden Roh-Fund (Dokument + extrahierte Kandidaten) unter
                       pipeline/staging/ ab - die einzige Quelle fuer die Review-UI
    content_hash.py    Fingerabdruck eines Zeitfensters, quellen-unabhaengig - dieselbe
                       Aussage bleibt "gesehen", auch wenn Formulierung/Quelle wechselt
    review_state.py    review-state/<source_id>.yaml: Entscheidung pro content_hash
                       (approved/modified/rejected), diff() gegen neue Kandidaten
    approval.py        Merge/Validierung/Schreiben nach data/ - der einzige Aufrufer von
                       store.merge_zeitfenster/validate.pruefe_subjekt_datei
    store.py           YAML laden/anlegen, Merge nach replace_key, Quelle anhaengen
    validate.py        prueft gegen lib/schema.ts (siehe unten)
    runner.py          orchestriert eine sources.yaml-Quelle: fetch -> extract -> stage
                       -> diff -> approval.write_event fuer bereits reviewte Kandidaten
  sources/             Escape Hatch: nur fuer eine Quelle, die wirklich bespoke Code
                       braucht (z.B. Strategie 1/Parser). Fuer strategie: llm reicht
                       ein sources.yaml-Eintrag, siehe unten - aktuell leer.
  tools/               einmalige Batch-Skripte - nutzen core/, aber laufen
    dwd_klima.py       ausserhalb des Source-Lebenszyklus (kein sources.yaml-Eintrag)
    migrate_existing.py  einmalige Migration: bestehende data/*.yaml als "approved" in
                       review-state uebernehmen (siehe dessen eigenes Docstring)
  config/
    crawl_sources/*.yaml  ein Scoped-Crawler-Quelle pro Datei (siehe "How to use" oben)
    migration_source_map.yaml  Kategorie -> source_id-Zuordnung fuer migrate_existing.py
  staging/             (gitignored) Rohdokumente + extrahierte, noch nicht
                       entschiedene Kandidaten - Arbeitszustand, kein Quelltext
  review-state/        (NICHT gitignored) Entscheidungshistorie pro Quelle - bewusst
                       committet, damit ein spaeterer Lauf approved/rejected kennt
  sources.yaml         Registry: URL, Kategorie, Lizenz, Rhythmus, Strategie, und fuer
                       strategie: llm/llm_season ein extraction_hint pro Quelle
  fixtures/            ein echtes Roh-Sample + erwartetes Ergebnis pro Quelle
  main.py              Dashboard: Crawl Sources + Review + Pages + Harvest
  scraper.py           Content-sniffing Dispatcher (HTML/PDF/Bild/ICS), den main.py,
                       core/crawl_runner.py und tools/ teilen
```

Eine Quelle hinzufuegen: entweder ueber das Dashboard (**Crawl Sources** -> Seed-URL
einfuegen, siehe "How to use" oben) - oder fuer eine wiederkehrende, bereits bekannte
Quelle einen `sources.yaml`-Eintrag (`kategorie`, `url`, `lizenz`, `rhythmus`,
`strategie: llm`, `extraction_hint`), dann:

```bash
cd pipeline
uv run python -m core.runner schulferien_kmk --jahr 2028
```

Kein Python noetig in beiden Faellen - `core/generic_source.py`/`core/crawler.py`
uebernimmt fetch/extract, `core/approval.py` das Schreiben nach `data/`. Nur wenn eine
Quelle wirklich bespoke Logik braucht (Strategie 1/Parser), kommt ein `sources/<id>.py`
mit `id`, `kategorie`, `extract(raw, params) -> ExtraktionsErgebnis` dazu - `core/runner.py`
bevorzugt ein vorhandenes Adapter-Modul, faellt sonst auf `generic_source.py` zurueck.

Kein PR mehr pro Lauf: alles, was noch nicht reviewt wurde, landet in
`pipeline/staging/` fuer die **Review**-Seite; bereits reviewte, unveraenderte
Kandidaten schreiben direkt nach `data/` (mit neu gestempeltem `last_verified`). Ein
Mensch committet/pusht/oeffnet einen PR fuer die angesammelten Aenderungen selbst,
wie bei jeder anderen lokalen Aenderung an diesem Repo.

**Schema-Drift vermeiden:** `core/validate.py` validiert NICHT gegen ein exportiertes
JSON-Schema (`zod-to-json-schema` wurde probiert, ist unter Zod v4 aber leer/kaputt -
selbst ein triviales Schema exportiert `{}`). Stattdessen ruft es `lib/validate-cli.ts`
auf, das direkt `subjektDateiSchema` aus `lib/schema.ts` importiert - dieselbe
Zod-Instanz, die der Astro-Build nutzt. Null Drift-Risiko, ein Subprocess-Call.

## Welche Quellen laufen wo?

Entschieden pro Quelle, nicht per Pipeline-weiter Philosophie (siehe PLAN.md
Abschnitt 7 fuer die volle Entscheidungsregel Homogenitaet × Volumen):

- **`sources.yaml` + `core/runner.py`** (dieser Ordner): wiederkehrende Quellen mit
  bekannter URL und einem einzigen Abruf pro Lauf. Aktuell: Schulferien (LLM-Extraktion
  aus der KMK-Ferienuebersicht, ueber `core/generic_source.py` - kein
  `sources/schulferien_kmk.py` mehr). `sources/` bleibt als Escape Hatch fuer eine
  Quelle, die wirklich bespoke Code braucht.
- **`config/crawl_sources/*.yaml` + `core/crawl_runner.py`** (Dashboard "Crawl
  Sources"): Quellen, deren Inhalt ueber mehrere Seiten/Dokumente verteilt ist und die
  innerhalb eines Domain-/Pfad-Scopes abgelaufen werden muessen (Veranstaltungsportale,
  Saisonkalender-PDFs, ICS-Feeds). Crawl -> Extract (LLM oder deterministisch fuer ICS)
  -> Review.
- **`tools/`**: einmalige, deterministische Batch-Skripte fuer bekannte, hoch
  strukturierte Quellen (DWD-Klimadaten). Kein LLM, kein `sources.yaml`-Eintrag - das
  Skript fetcht die bekannte URL-Struktur korrekt oder es tut es nicht.
  `extraktion: parser` in der resultierenden YAML.
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

- `schedule` on a crawl source is metadata only for now - nothing runs it automatically yet
  (a cron job calling `POST /crawl-sources/{id}/run` would be the natural next step)
- Later `harvest/` stages (discover/probe/extract/validate/publish/maintain) don't exist yet