# Structure and data flow

How a date gets from a website into the published calendar, and where every file involved
lives. Written to be read top to bottom once, then used as a reference.

Companion documents: [README.md](./README.md) (what the project is),
[AGENTS.md](./AGENTS.md) (the short rules), [pipeline/README.md](./pipeline/README.md)
(operating the pipeline), [CONTRIBUTING.md](./CONTRIBUTING.md) (adding data by hand).

---

## 1. The one rule

Every time window is either **decreed** or **derived**.

- **Decreed** — someone with authority published it. School holidays, a festival date, an
  eclipse. It cannot be computed, only looked up. → **data**, a YAML file under `data/`.
- **Derived** — it follows from a rule. Easter, a bridge day between a holiday and a
  weekend. → **code**, a `generator.ts` that runs at build time.

Both converge on `lib/materialization.ts`, and **nothing** else may read `data/` to render a
page. The calendar UI, the static pages, the JSON API and the ICS feeds all consume the
materialised layer. That is what keeps "where did this come from" answerable.

A third axis is *how* a decreed fact was obtained — crawled, parsed, hand-typed. That is a
**field** (`mode` in `meta.toml`, `extraction` in `data.yaml`), never a directory. Organising
by acquisition technique is what previously scattered the same concern across four folders.

---

## 2. Directory map

### `data/` — the published dataset

Single source of truth. CC BY 4.0 ([data/LICENSE](./data/LICENSE)). Committed.
**Written only by an approval or by a human.** Never by a scraper directly.

| Path | Contents |
| :--- | :--- |
| `data/_sources/*.yaml` | One file per upstream source. `_` keeps it out of the category walk, so it is never a route. |
| `data/{category}/{subject}/data.yaml` | The facts: `subject`, `source[]`, `windows[]` or `raw_data`. Zod-validated. |
| `data/{category}/{subject}/page.yaml` | Title, description, tags. Written once on first approval, never rewritten. |
| `data/{category}/{subject}/meta.toml` | What this subject is: `subject`, `category`, `mode`, optional `sources[]`. |
| `data/{category}/_category.yaml` | Display name for the category node (`name`, optional `description`). |
| `data/{category}/generator.ts` | Derived categories only (`feiertage`, `urlaubsfenster`). No subject folders at all. |
| `data/presets/*.yaml` | Curated calendar URLs (region + active layers). |
| `data/homepage-questions.yaml` | Templates for the homepage question rotator. |
| `data/community-sources.txt` | `@handle url` lines — suggested sources, not yet processed. |

Categories may nest up to `MAX_CATEGORY_DEPTH = 4` segments
(`data/events/feste/wiesnkini-de/` → `/events/feste/wiesnkini-de/`).

### `pipeline/` — one Python project, three folders

| Path | Contents | Committed |
| :--- | :--- | :--- |
| `pipeline/core/` | Shared machinery: fetch, crawl, sniff, extract, stage, diff, approve, validate. | yes |
| `pipeline/sources/` | One module per source that needs bespoke code (`dwd_klima`, `pollenflug`, `registry`). | yes |
| `pipeline/review/` | The review app: `app.py`, `service.py`, `routes/`, `templates/`, `static/`. | yes |
| `pipeline/cli.py` | The `wom` entry point. | yes |
| `pipeline/config/registries.yaml` | Wikidata SPARQL per entity class — seeds for *future* crawls. | yes |
| `pipeline/review-state/*.yaml` | Decision history per source. **Deliberately committed** — without it the next crawl re-surfaces everything ever rejected. | yes |
| `pipeline/staging/` | Fetched documents + candidates awaiting judgement. A work queue. | **gitignored** |
| `pipeline/data/registries/` | Fetched Wikidata dumps. A cache, regenerable in one command. | **gitignored** |
| `pipeline/.env` | Provider keys and `LLM_PROVIDER`. | **gitignored** |

**The import rule**, enforced by `pipeline/tests/test_invariants.py`:

```
sources/ ──> core/ <── review/
sources/  ✗✗  review/          (never see each other)
core/     ✗✗  sources/, review/ (never imports its callers)
```

This is the decoupling a repo split would have bought, without a repo split.

### `lib/` — platform-neutral TypeScript

`schema.ts` (Zod for `data.yaml`), `pages-schema.ts` (page/category shapes), `pages.ts` (the
directory walk and the one page model), `materialization.ts`, `holidays.ts`,
`vacation-windows.ts`, `ics.ts`, `validate-cli.ts`, plus date utilities.

### `src/` — Astro + Vue

`src/pages/[...path].astro` renders every walked page. `src/components/Kalender.vue` is the
one Vue island. JSON at `src/pages/api/v1/`, ICS at `src/pages/feeds/[...path].ics.ts`.

---

## 3. The two kinds of source

`data/_sources/` holds **two different config shapes**, told apart by one field. This is the
single most confusing thing in the repo, so it is spelled out fully.

|  | **crawl source** | **batch source** |
| :--- | :--- | :--- |
| Marker | *no* `kind:` field | `kind: batch` |
| Example | `data/_sources/wiesnkini-de.yaml` | `data/_sources/schulferien_kmk.yaml` |
| Loaded by | `core/crawl_config.py` → `load_all_crawl_sources()` | `core/runner.py` → `lade_quellen_config()` |
| Run by | `core/crawl_runner.py` | `core/runner.py` |
| Shape | Walks many pages inside one domain/path scope | One fetch, one URL |
| Subjects produced | **one** (`subject_slug`) | **many** (a KMK page → 16 Bundesländer) |
| Created in the UI | **yes** — paste a seed URL at `/crawl-sources` | **no** — hand-written file |
| Edited / deleted in the UI | **yes** | **no** |
| Listed at `/crawl-sources` | **yes** | **no** |
| Run from the UI | **yes** (Run button) | **no** |
| Run from the CLI | `wom run <id>` | `wom run <id>` |

`create_crawl_source` (`review/routes/crawl_sources.py:93`) never writes a `kind:` field, so
everything the UI produces is by definition a crawl source. `edit`, `delete` and `run` all
resolve the id through `load_all_crawl_sources()`, which filters `kind`-bearing files out —
so those routes return **404** for `schulferien_kmk`.

**Yes, you hand-write `data/_sources/schulferien_kmk.yaml`.** There is exactly one batch
source. See §10.

### Crawl source fields

```yaml
id: wiesnkini-de                    # must equal the filename stem
seed_url: https://wiesnkini.de/haufige-fragen/wann-findet-das-oktoberfest-statt
category: events/feste              # "/"-joined, becomes data/{category}/
subject_slug: wiesnkini-de          # becomes data/{category}/{subject_slug}/; defaults to id
subject_name: ''                    # page.yaml title; blank = use the cleaned <title>
scope:
  allowed_domains: [wiesnkini.de]   # required, non-empty
  path_prefix: /haufige-fragen/...  # optional
max_depth: 0                        # 0..3
formats: [html]                     # html | pdf | ics | image
event_type_hint: ''                 # label the extractor gives each window
schedule: manual                    # metadata only — nothing runs it automatically
extraction_mode: llm                # auto | llm | static, see §4.3
auto_approve_ics: false
```

Setting the **same `category` + `subject_slug`** on several sources aggregates them onto one
page — that is deliberate, and the reason two NASA catalogs feed one
`astronomie/sonnenfinsternis`. Both halves must match; a shared slug under different
categories silently yields two pages.

> Changing `subject_slug` on a live source re-opens every candidate it ever had:
> `content_hash.normalize_event()` hashes the slug. Safe on a new source, disruptive on an
> established one. Changing `category` is safe — it is not hashed.

### Batch source fields

```yaml
kind: batch                         # the discriminator
id: schulferien_kmk
kategorie: schulferien              # target category
url: https://www.kmk.org/service/ferienregelung/ferienkalender.html
lizenz: official_par5               # must match licenseSchema in lib/schema.ts verbatim
rhythmus: jaehrlich                 # documentation only
strategie: llm                      # parser | llm | llm_season
extraction_hint: >                  # domain framing handed to the model
  This page lists German public school holiday date ranges ...
license_note: >
  Ferientermine der Kultusministerkonferenz (KMK) ...
```

`strategie` selects the extraction path:
- `parser` — a `sources/<id>.py` module with `extract(raw, params)`. The escape hatch.
- `llm` — `core/generic_source.py:extract`, driven entirely from this config. No Python.
- `llm_season` — `extract_season`, for sources whose information is encoded as *colour* on an
  image or PDF (a Saisonkalender) rather than as text.

`core/runner.py` prefers a `sources/<id>.py` adapter if one exists and falls back to
`generic_source`.

---

## 4. Data flow, stage by stage

```
      ┌── crawl source ──> core/crawler.py ──┐
 (1)  │                                      ├─> (2) sniff ─> (3) extract ─> (4) stage
      └── batch source ──> core/fetch.py ────┘                                   │
                                                                                 v
                                                          (5) diff vs review-state
                                                                    │
                                             already decided ───────┤─────── new
                                                    │                        │
                                                    v                        v
                                          (6) approval.write_event    pipeline/staging/
                                                    │                        │
                                                    v                 human reviews ──> (6)
                                                  data/
                                                    │
                                                    v
                                             (7) Astro build ──> dist/
```

### 4.1 Fetch

**Batch:** `core/fetch.py:fetch_bytes(url)` — one request, returns `(bytes, content_type)`.
Timeout and retry; the only module in the project that opens a socket for source data.

**Crawl:** `core/crawler.py:crawl(source)` — breadth-first within scope.
- `in_scope()` enforces `allowed_domains` + `path_prefix`.
- `robots.txt` is honoured (`_RobotsCache`).
- `MIN_SECONDS_BETWEEN_REQUESTS_PER_DOMAIN = 1.0`.
- `USER_AGENT = "wann-crawler/1.0 (+github.com/am9zZWY/wann; contact: ...)"`.
- `_discover_links()` returns page links *and* `<link type="text/calendar">` ICS feeds.
- Yields `CrawledDocument(url, content_type, content)`.

### 4.2 Sniff

`core/sniff.py:extract_any(name, content, content_type)` takes **bytes, never a URL** — which
is why the crawler, the batch runner and the staging snapshot can all share it. It dispatches
on magic bytes, content type and file extension, returning a dict tagged with one `kind`:

| `kind` | Meaning |
| :--- | :--- |
| `ics_feed` | RFC 5545 calendar → windows directly, no model |
| `html_page` | markdown text + preview |
| `pdf_document` | rendered per page, read by vision |
| `image_page` | read by vision |
| `directory_listing` | Apache `mod_autoindex` rows |
| `tabular_text` | delimited or fixed-width |
| `plain_text` | fallback |
| `zip_archive` | recurses into members |
| `unsupported_binary` | undecodable, oversized, or a failed vision call |

A tenth value, `error`, exists but is never returned by `extract_any` itself — it tags an
individual member inside a `zip_archive`'s `entries[]` that failed to extract.

### 4.3 Extract

**Deterministic, no model:**
- `core/ics.py:map_calendar` — RRULE preserved verbatim, all-day `DTEND` converted from
  RFC 5545 exclusive to inclusive, UTC normalised to Europe/Berlin wall-clock.
- `_static_dates()` — regex for ISO (`2026-09-19`) and catalog form (`2001 Jun 21`) **only**.
  A German date ("19. September") yields nothing.

**Model-driven** (`core/extraction.py`): `extract_dated_events`, `extract_subjects`,
`extract_season_windows`, plus `suggest_tags` / `suggest_title` / `suggest_category` for the
review UI. Long pages are chunked with overlap.

`extraction_mode` on a crawl source decides which runs:
- `auto` — if an HTML page yields ≥ `STATIC_DATE_THRESHOLD` (**15**) machine-readable dates,
  it is treated as a date *table* and read deterministically; everything else goes to the
  model. PDFs and images always go to the model.
- `llm` — always the model. Right when every date needs its own real label.
- `static` — never the model. Cheap and exhaustive on a generated table, at the cost of one
  shared label for every date.

### 4.4 Stage

`core/staging.py`. Layout:

```
pipeline/staging/<source_id>/<run_ts>/documents/<doc_hash>.md|.pdf|.ics|...
pipeline/staging/<source_id>/<run_ts>/documents/<doc_hash>.meta.yaml
pipeline/staging/<source_id>/<run_ts>/candidates/<candidate_id>.yaml
```

`run_ts` is `YYYYmmdd-HHMMSS` UTC. `doc_hash` is the **sha256 of the raw bytes**, not of the
URL — so a snapshot stays referenceable after the page changes or disappears, and two URLs
serving identical content dedupe to one file within a run.

The unit of review is **one window**, not one page or one subject: a Bundesland carries
Osterferien *and* Sommerferien, independently judged.

### 4.5 Diff

`core/review_state.py:diff(candidates, state, category, subject_slug)` splits this run into
`(auto_waved_through, needs_review)`. Precedence, in order:

1. **Already in the page file** → wave through (re-stamp `last_verified`).
2. **Previously rejected** → drop silently.
3. **Otherwise** → queue for a human.

The file wins over the rejected set, so hand-adding a previously-rejected window keeps it —
that is intended.

Review is per **page**, not per source: a second source reporting an already-approved window
is waved through and merely adds its citation. Two sources reporting the same *unreviewed*
window collapse to one queue row.

Identity is `core/content_hash.py:window_key` over exactly:

```
type, year, from, to, name, value, unit, rrule
```

Deliberately **excluded**: `last_verified` (a freshness stamp — including it would change the
hash on every re-verification), `source_urls` (who reported it, not what it is), `ics` and
`precision` (display choices). `rrule` **is** included: a changed recurrence is a real change.

### 4.6 Approve

`core/approval.py:write_event(category, subject_slug, subject_name, event, quelle)` — the
**only** function that writes a fact into `data/`:

1. `store.lade_oder_erstelle` — load or create `data/{category}/{subject_slug}/data.yaml`.
2. `store.merge_zeitfenster` — merge by `window_key`; same key → one entry with **both**
   citations unioned, different key → both kept. Two sources reporting the same window is the
   business model, not a duplicate.
3. `store.append_quelle` — dedupe the file's `source[]` by URL, freshest entry wins.
4. `validate.pruefe_subjekt_datei` — shells out to `bun run lib/validate-cli.ts`, which
   imports the **same Zod object** the Astro build uses. Zero drift risk, at the cost of one
   subprocess (30 s timeout). Raises before anything is written.
5. `store.speichere` — only now is the file written.
6. `store.schreibe_page_yaml_falls_neu` — `page.yaml` on first creation only, so hand-edited
   titles survive re-runs.

If validation fails, `ApprovalError` is raised and **nothing is written**.

### 4.7 Build

`lib/pages.ts` walks `data/`:

- A directory containing **both** `page.yaml` and `data.yaml` is a **page**.
- Any other directory is a further **category node** (up to depth 4, then a hard error).
- Directories starting with `_` are skipped entirely — this is what keeps `data/_sources/`
  from becoming a route.
- `RESERVED_CATEGORIES` blocks top-level names that collide with existing routes
  (`kalender`, `presets`, `api`, `feeds`, …). `tag` is reserved at any depth.
- `GENERATORS` produces `feiertage` and `urlaubsfenster` in code; both are excluded from the
  walk so their pages are not double-counted.

`materializeRawWindow(raw, subjectId, sources, years)` then resolves each raw window into
concrete years — rolling over the current year + 2 when `year` is `null` — and attaches only
the sources that actually reported it (`source_urls`), falling back to the file's full source
list for legacy windows without that field.

Output: `src/pages/[...path].astro` (pages), `src/pages/api/v1/**` (JSON),
`src/pages/feeds/[...path].ics.ts` (ICS), sitemap, `llms.txt`.

---

## 5. File formats

### `data.yaml`

```yaml
subject:
  slug: wiesnkini-de
  category: events/feste
windows:
  - type: event                     # free string; the category's vocabulary
    year: 2026                      # int, or null for a recurring template
    from: '2026-09-19'              # "YYYY-MM-DD", "YYYY-MM-DDTHH:MM" or "--MM"
    to: '2026-10-04'
    precision: exact                # exact | approximate
    ics: true                       # include in ICS feeds
    name: Oktoberfest               # optional label
    source_urls:                    # optional; must exist in source[] below
      - https://wiesnkini.de/...
    # also optional: value + unit (set together or not at all),
    # last_verified, rrule, notes
source:
  - url: https://wiesnkini.de/...
    license: tos_checked            # the licenseSchema enum, never guessed
    license_note: null
    retrieved_at: '2026-07-25'
    extraction: llm                 # manual | llm | parser
    # optional: confidence (0..1), contributed_by
```

A window's `source_urls` **must** reference a URL present in `source[]` — enforced by a Zod
`superRefine`, so a typo fails the build instead of silently re-attaching the whole list.

### `page.yaml`

```yaml
title: Oktoberfest
description: ''
tags: []
```

### `meta.toml`

```toml
subject  = "bw"
category = "schulferien"
mode     = "scraper"                # generator | transform | scraper | manual
sources  = ["schulferien_kmk"]      # ids in data/_sources/; omit when none
```

`mode` records which pipeline owns the folder — the one fact not derivable from anything else
in it:

| `mode` | Runs | Reviewed | Example |
| :--- | :--- | :--- | :--- |
| `generator` | TypeScript, build time | no | `feiertage`, `urlaubsfenster` |
| `transform` | Python, deterministic | no | DWD climate data |
| `scraper` | Python, model-driven | **yes** | `schulferien`, `astronomie` |
| `manual` | nobody — hand-authored | n/a | `saisonkalender` |

Review exists because a model can guess. Where nothing is guessed, review is theatre and the
git diff is the check.

`meta.toml` deliberately does **not** repeat licence or source URL — those live in the
`source:` block of the `data.yaml` beside it, where Zod validates them and
`structured-data.ts` renders them as citations. A second unvalidated copy would drift.

Generator-backed categories carry a category-level `meta.toml` instead, since they have no
subject folders: `category`, `mode = "generator"`, `generator = "generator.ts"`.

### `_category.yaml`

```yaml
name: Astronomie
description: ''
```

### Staged candidate

```yaml
candidate_id: schulferien_kmk:fdf161f18ad9...
source_id: schulferien_kmk
subject_slug: by
subject_name: by                    # see §10 — should be the readable name
category: by                        # see §10 — should be "schulferien"
document: b9c1e2b2fa304a72          # the doc_hash of the snapshot it came from
extracted_at: '2026-07-27T19:32:54.757885+00:00'
content_hash: fdf161f18ad9...       # window_key hash; the id for review decisions
event:                              # one RawWindow
  type: allerheiligenferien
  year: 2028
  from: '2026-11-02'
  to: '2026-11-06'
  precision: exact
  ics: false
  name: Allerheiligenferien
  source_urls: [https://www.kmk.org/...]
```

### Document snapshot metadata

```yaml
doc_hash: b9c1e2b2fa304a72
url: https://www.kmk.org/service/ferienregelung/ferienkalender.html
content_type: text/html; charset=utf-8
fetched_at: '2026-07-27T19:32:34.514712+00:00'
stored_as: b9c1e2b2fa304a72.md
```

### `review-state/<source_id>.yaml`

```yaml
rejected:
  - subject_slug: wiesnkini-de
    type: event
    year: 2026
    from: '2026-09-19'
    to: '2026-10-04'
    name: oktoberfest               # lower-cased, whitespace-stripped
    value: null
    unit: null
    rrule: null
    decided_at: '2026-07-25T22:40:55.880447+00:00'
```

Only **rejections** are stored. Approvals are not recorded here — the presence of the window
in `data/{category}/{subject}/data.yaml` *is* the record. That is what makes hand-editing a
supported operation: delete a line from `data.yaml` and the next run re-offers it; keep it and
the next run waves it through.

---

## 6. Write directions

There is exactly one direction, and it has no exceptions.

| Step | Reads | Writes |
| :--- | :--- | :--- |
| `wom run <source>` | `data/_sources/` | `pipeline/staging/`, and `data/` **only** for windows already approved |
| `wom review` (approve) | `pipeline/staging/` | `data/`, `pipeline/review-state/` |
| `wom review` (reject) | `pipeline/staging/` | `pipeline/review-state/` |
| `wom registry` | `pipeline/config/registries.yaml` | `pipeline/data/registries/` (gitignored) |
| Astro build | `data/` | `dist/` |

**The scraper never writes an unreviewed candidate to `data/`.** This is the most important
rule in the design — it is what guarantees nothing unreviewed reaches the published dataset.

The Astro build never writes back. A `generator.ts` is not a write: `lib/pages.ts` calls it at
build time, the result lives in memory and goes to `dist/`.

**The local review is the approval. GitHub is the merge gate and the audit log.** Two
different jobs — an LLM can guess, so a human sees each candidate before it reaches `data/`;
at 300 candidates a run that is an app, not a PR discussion. What was approved is then
committed and pushed like any other change: the PR documents the decision, it does not make
it.

---

## 7. Entry points

### `wom`

| Command | Does |
| :--- | :--- |
| `wom sources` | Lists every source and which runner owns it |
| `wom run <id> [--key value ...]` | Fetches one source and stages its candidates. Dispatches on `kind`. Params are accepted by batch sources only (`--jahr 2028`) and **rejected** on a crawl source, whose scope is its config file. |
| `wom review [--host --port]` | Serves the review app (default `127.0.0.1:8000`) |
| `wom registry <entity_class>` | Fetches a Wikidata entity registry |

Exit codes: `0` success, `1` unknown source, `2` bad arguments. Works from any directory —
every path resolves from `__file__`, not the cwd. Subcommands import lazily, so `wom --help`
does not pay for loading PyMuPDF and FastAPI.

### Review app routes

| Resource | Routes | Module |
| :--- | :--- | :--- |
| Pages | `GET /`, `GET /page-data/*`, `GET /page-meta/*`, `POST /pages/*/delete`, `/edit`, `/suggest-tags`, `/add-tag` | `review/routes/pages.py` |
| Crawl sources | `GET /crawl-sources`, `/crawl-sources-table`, `POST /crawl-sources/new`, `/{id}/edit`, `/{id}/delete`, `/{id}/run`, `GET /{id}/status` | `review/routes/crawl_sources.py` |
| Review | `GET /review`, `/review/{source}/{candidate}`, `/review/{source}/document/{hash}`, `/staging-document/...`, `POST .../approve`, `/modify`, `/reject`, `/review/bulk-edit` | `review/routes/review.py` |
| Harvest | `GET /harvest`, `POST /harvest/registry`, `/harvest/registries/config`, … | `review/routes/harvest.py` |
| Status | `GET /status`, `/status-fragment` | `review/routes/status.py` |

`review/app.py` is assembly only. `review/service.py` holds every non-HTTP function plus
`DATA_ROOT`, which is what lets a test repoint the whole app at a `tmp_path` by patching one
attribute.

---

## 8. Configuration

`pipeline/.env`, read by `core/llm.py` at import so **every** entry point sees it — CLI, web
app, a bare `python -c`:

```sh
LLM_PROVIDER=mistral      # anthropic | openai | google | mistral | openrouter
MISTRAL_API_KEY=...       # whichever provider's key matches
LLM_MODEL=                # optional; each provider has a small/cheap default
OPENROUTER_MODEL=         # required for openrouter — "cheap default" is meaningless there
```

Providers are called over plain REST with `httpx`; no provider SDKs, since the requirement is
one capability (send a prompt, get text) and four SDKs would be heavy for that.

> **Trap:** `LLM_PROVIDER` defaults to `anthropic` when unset, so an unread `.env` surfaces as
> `ANTHROPIC_API_KEY is not set` no matter which key you actually hold. If you see that on a
> machine configured for another provider, the variable is not reaching the process.

---

## 9. Invariants

Enforced by `pipeline/tests/test_invariants.py`. Each held once, quietly stopped holding, and
that is how source config ended up spread across four directories.

| # | Rule | Breaks when |
| :-- | :--- | :--- |
| 1 | Every subject folder has exactly one `meta.toml`, agreeing with the `data.yaml` beside it | A new page is created without one, or the two disagree |
| 2 | Every source named in a `meta.toml` resolves to a real `data/_sources/` file | A source is renamed or deleted without updating its subjects |
| 3 | No source config outside `data/` | Config is added back under `pipeline/` |
| 4 | `core/` imports neither `sources/` nor `review/` | A core module reaches back into its callers |

`pipeline/config/registries.yaml` is the one named exemption from #3: it lists Wikidata
queries for seeding future crawls and explains no fact currently published.

---

## 10. Known rough edges

Recorded so this document describes what is, not what was intended.

`core/runner.py` used to omit `subject_name=` and `category=` when building a candidate, so
both defaulted to `subject_slug`: a `schulferien_kmk` candidate read `category: by` instead of
`schulferien`. Auto-approval was unaffected (it uses the `ExtractionResult`'s category), but
approving such a candidate in the UI writes `data/by/by/data.yaml` — a top-level category
created silently, since `by` is not in `RESERVED_CATEGORIES`.

Fixed, and covered by `tests/test_runner.py`. **Candidates already in `staging/` still carry
the old values** — re-run the source to re-stage them rather than approving what is there.

**Batch sources are invisible in the UI.** `/crawl-sources` lists only crawl sources; the
edit, delete and run routes 404 for a `kind: batch` id. `schulferien_kmk` appears only as a
string in the review queue's Source column, because `_known_source_ids()` unions crawl configs
with staging directory names.

**Two templates name a directory that no longer exists.**
`review/templates/crawl_sources.html:14` and `_crawl_sources_table.html:123` tell the operator
that configs live in `pipeline/config/crawl_sources/`. They live in `data/_sources/`.

**`schedule:` does nothing.** It is metadata on a crawl source; no scheduler reads it. A cron
job calling `wom run <id>` is the intended mechanism.

**`ruff format` is not enforced.** It wants ~1700 lines across 35 files and some of the result
reads worse than what it replaces. `uvx ruff check .` and `uvx ty check` are enforced, in CI.
