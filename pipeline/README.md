# Wann-Plattform Admin Dashboard

FastAPI + Jinja2 SSR admin interface for the scoped crawler + review workflow.

## Features

- **Scoped Crawler**: each source is a config file (`data/_sources/<id>.yaml` -
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

## `wom` - the CLI

```bash
cd pipeline
uv run wom sources                      # every source, and which runner owns it
uv run wom run wiesnkini-de             # crawl a source, stage its candidates
uv run wom run schulferien_kmk --jahr 2028   # batch sources take --key value params
uv run wom review                       # serve the review app on :8000
uv run wom registry university_de       # fetch a Wikidata entity registry
```

`wom run` dispatches on the source's `kind` (see `data/_sources/`): a `kind: batch`
file goes to `core/runner.py`, one without to `core/crawl_runner.py`. Crawl sources
had no CLI at all before this - they could only be started from the dashboard's
**Run** button.

Both paths end the same way, and it is the rule the whole design rests on: candidates
that were already reviewed are written to `data/`, everything else waits in
`staging/` for `wom review`. **Nothing here writes an unreviewed candidate to
`data/`.**

The subcommands are thin wrappers - each calls the same function the dashboard
calls, so the CLI and the UI cannot drift apart. `uv run wom` works from any
directory; every path is resolved from `__file__`, not the cwd.

`wom review` then serves **http://localhost:8000**.

### LLM configuration

Anything that extracts with a model reads `pipeline/.env` (loaded by
`core/llm.py`, so every entry point sees the same config - CLI and web app
alike):

```sh
LLM_PROVIDER=mistral        # anthropic | openai | google | mistral | openrouter
MISTRAL_API_KEY=...         # whichever provider's key matches
LLM_MODEL=                  # optional; each provider has a small/cheap default
```

`LLM_PROVIDER` defaults to `anthropic` when unset, so a missing or unread
`.env` surfaces as "ANTHROPIC_API_KEY is not set" regardless of which key you
actually hold. If you see that on a machine configured for another provider,
the variable is not reaching the process.

## Lint, types, tests

```bash
cd pipeline
uvx ruff check .        # lint  (--fix applies the safe fixes)
uvx ty check            # types
uv run pytest -q        # tests
```

All three run on every push (`.github/workflows/deploy.yml`). No install step and
no lockfile entry - `uvx` fetches both tools on demand; their config lives in
`pyproject.toml` under `[tool.ruff]`.

The ruff ruleset is pinned explicitly rather than left to the tool's default,
which has broadened between releases and would otherwise turn CI red on an
upgrade that changed nothing here. `ruff format` is available but not enforced:
it wants ~1700 lines across 35 files, and some of that reads worse than what it
replaces.

A `# noqa` / `# ty: ignore` here is expected to say WHY beside it. There are
five, each a tool limitation rather than a concession:

| where | why |
| :---- | :-- |
| `review/service.py` F401 | a re-export reached only as `service.suggest_tags`, which pyflakes cannot see |
| `review/service.py` no-matching-overload | jinja2 infers `env.globals`' value type from its own builtins, so any app global looks wrong |
| `core/sniff.py` RUF001 | the EN DASH is deliberate - German date ranges are written "1.5. – 3.5." |
| `core/crawl_config.py` invalid-assignment | `field(default=None)` on a `Path`, already carrying a mypy ignore |
| `tests/test_invariants.py` unresolved-import | `tomllib` is 3.11+, imported behind a `try`/`except` |

Plus `# noqa: E402` on the tests' imports, which follow a deliberate
`sys.path.insert` preamble.

Fixture-based per source (`tests/fixtures/{source_id}/raw_sample... + erwartet.yaml`) - see
`tests/test_schulferien_kmk.py` for the pattern. LLM calls are mocked with the fixture's
expected output; everything deterministic around them (store merge, real Zod validation) is
genuinely exercised.

## How to use

1. Go to **Crawl Sources**
2. Paste a seed URL and click **Add Source** (or open **Advanced options** to override the
   derived ID, category, allowed domains, path prefix, depth, formats, or schedule) - this
   writes `data/_sources/<id>.yaml`
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
in both `lib/pages.ts` and `review/service.py` rejects a category name that would collide with an existing
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

Ein Python-Projekt, drei Ordner, und eine Import-Regel, die sie entkoppelt: `sources/`
und `review/` duerfen `core/` importieren, `core/` keinen von beiden, und `sources/` und
`review/` sehen einander nie. Das ist die Entkopplung, die ein Repo-Split gebracht
haette, ohne dessen Kosten - festgenagelt in `tests/test_invariants.py`.

```text
pipeline/
  core/                gemeinsame Maschinerie, einmal geschrieben, nie kopiert
    fetch.py           HTTP mit Timeout/Retry - der einzige Ort, der ins Netz greift
    sniff.py           Content-sniffing Dispatcher (HTML/PDF/Bild/ICS/CSV/ZIP). Nimmt
                       Bytes, nie eine URL - deshalb teilen crawl_runner, generic_source
                       und staging ihn gegen bereits geholte Bytes
    types.py           ExtraktionsErgebnis + SourceAdapter - der ganze Adapter-Vertrag
    extraction.py      LLM-Extraktion, u.a. extract_subjects()/extract_season() - eine
                       Quelle kann mehrere Subjekte in einem Abruf enthalten; das Modell
                       entdeckt den Split aus dem echten Seiteninhalt
    generic_source.py  fetch -> extract_subjects/extract_season -> ExtraktionsErgebnis[]
                       rein aus der data/_sources-Konfiguration - fuer strategie: llm
    ics.py             deterministische ICS-Extraktion (RRULE, all-day, Zeitzonen) - kein LLM
    crawl_config.py    laedt data/_sources/*.yaml -> CrawlSource
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
    runner.py          orchestriert eine data/_sources-Batch-Quelle: fetch -> extract
                       -> stage -> diff -> approval.write_event fuer reviewte Kandidaten
  sources/             ein Modul pro Quelle, gleiches Interface. WIE eine Quelle ihre
    dwd_klima.py       Daten beschafft (crawlen, harvesten, parsen), ist Implementierungs-
    pollenflug.py      detail INNERHALB des Moduls und kein eigener Ordner - genau die
    registry.py        Achse, an der die alten tools/ und harvest/ auseinanderfielen
  review/              die Review-App - die Freigabe, nicht bloss eine Ansicht
    app.py             FastAPI-Zusammenbau, sonst nichts
    service.py         die ganze Logik ohne HTTP - direkt testbar, ohne TestClient
    routes/            eine Datei pro Ressource: pages, crawl_sources, review, harvest, status
    templates/ static/ Jinja2-SSR + HTMX
  config/
    registries.yaml    Wikidata-SPARQL pro entity_class (siehe Harvest unten)
  staging/             (gitignored) Rohdokumente + extrahierte, noch nicht
                       entschiedene Kandidaten - Arbeitszustand, kein Quelltext
  review-state/        (NICHT gitignored) Entscheidungshistorie pro Quelle - bewusst
                       committet, damit ein spaeterer Lauf approved/rejected kennt
  tests/fixtures/      ein echtes Roh-Sample + erwartetes Ergebnis pro Quelle
```

Die Quellkonfiguration liegt NICHT hier, sondern in `data/_sources/*.yaml` - eine Datei
pro Upstream, neben den Fakten, die sie erklaert. Sie kann nicht in den Subjektordner:
Quelle und Subjekt sind in beide Richtungen n:m (eine KMK-Seite -> 16 Bundeslaender,
zwei NASA-Kataloge -> eine Sonnenfinsternis-Seite), und eine Quelle existiert, bevor ihr
Subjekt existiert. Beide Sorten teilen sich das Verzeichnis und unterscheiden sich am
Feld `kind`: `kind: batch` gehoert `core/runner.py`, ohne `kind` dem Crawler.

Eine Quelle hinzufuegen: entweder ueber das Dashboard (**Crawl Sources** -> Seed-URL
einfuegen, siehe "How to use" oben) - oder fuer eine wiederkehrende, bereits bekannte
Quelle einen `data/_sources/<id>.yaml` mit `kind: batch` (`kategorie`, `url`, `lizenz`, `rhythmus`,
`strategie: llm`, `extraction_hint`), dann:

```bash
cd pipeline
uv run wom run schulferien_kmk --jahr 2028
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

- **`data/_sources/*.yaml` mit `kind: batch` + `core/runner.py`**: wiederkehrende Quellen
  mit bekannter URL und einem einzigen Abruf pro Lauf, die dabei aber MEHRERE Subjekte
  liefern koennen. Aktuell: Schulferien (ein KMK-Abruf -> 16 Bundeslaender, LLM-Extraktion
  ueber `core/generic_source.py` - kein `sources/schulferien_kmk.py` mehr). Ein Modul in
  `sources/` bleibt der Escape Hatch fuer eine Quelle, die wirklich bespoke Code braucht.
- **`data/_sources/*.yaml` (ohne kind) + `core/crawl_runner.py`** (Dashboard "Crawl
  Sources"): Quellen, deren Inhalt ueber mehrere Seiten/Dokumente verteilt ist und die
  innerhalb eines Domain-/Pfad-Scopes abgelaufen werden muessen (Veranstaltungsportale,
  Saisonkalender-PDFs, ICS-Feeds). Crawl -> Extract (LLM oder deterministisch fuer ICS)
  -> Review.
- **`sources/` (Batch-Skripte)**: einmalige, deterministische Batch-Skripte fuer bekannte, hoch
  strukturierte Quellen (DWD-Klimadaten). Kein LLM, kein data/_sources-Eintrag - das
  Skript fetcht die bekannte URL-Struktur korrekt oder es tut es nicht.
  `extraktion: parser` in der resultierenden YAML.
- **`sources/registry.py` + `config/registries.yaml`**: entity-first for a large, known
  set of entities (e.g. all German universities) instead of one curated
  source - see below.

## Harvest pipeline (entity-first)

For a finite entity set (currently: `university_de`), find each entity's
target page, extract dates, and publish. Only Stage 1 (`registry`) is
implemented so far:

```bash
cd pipeline
uv run wom registry university_de
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
- Later registry stages (discover/probe/extract/validate/publish/maintain) don't exist yet