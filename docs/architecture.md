# Architecture and data flow

High-level map of how a date gets from a website into the published calendar. For exact
function signatures, line numbers, and call paths, use CodeGraph (`codegraph explore
"<question or symbol>"`, or the `codegraph_explore` MCP tool) instead of grepping. This
document only covers the shape, not the details.

Companion documents: [README.md](../README.md) (what the project is),
[AGENTS.md](../AGENTS.md) (the short rules), [pipeline/README.md](../pipeline/README.md)
(operating the pipeline), [contributing.md](./contributing.md) (adding data by hand).

## The one rule

Every time window is either decreed or derived.

- Decreed: someone with authority published it (school holidays, a festival date, an
  eclipse). It cannot be computed, only looked up. Lives as data, a YAML file under `data/`.
- Derived: it follows from a rule (Easter, a bridge day between a holiday and a weekend).
  Lives as code, a `generator.ts` that runs at build time.

Both converge on `lib/materialization.ts`. Nothing else may read `data/` to render a page.
The calendar UI, static pages, JSON API, and ICS feeds all consume that materialized layer.

A third axis, how a decreed fact was obtained (crawled, parsed, hand-typed), is a field
(`mode` in `meta.toml`), never a directory.

## Directory map

- `data/` is the published dataset. Decreed facts, one folder per subject, plus
  `data/_sources/` for upstream source configs. Written only by an approval or a human,
  never by a scraper directly.
- `pipeline/` is the Python project that fetches, extracts, and stages candidates for
  review. `core/` holds shared machinery, `sources/` holds source-specific code,
  `review/` is the review app. `core/` never imports its callers.
- `lib/` is platform-neutral TypeScript: schema validation, holiday and bridge-day rules,
  materialization, ICS generation.
- `src/` is the Astro and Vue frontend that reads the materialized layer.

## Data flow

Fetch (crawl or single request) → sniff the content type → extract dates (deterministic
where possible, model-driven otherwise) → stage as candidates → diff against past review
decisions → a human approves or rejects → approved facts land in `data/` → the Astro build
turns `data/` into pages, JSON, and ICS feeds.

## Write direction

Only one direction, no exceptions:

- Fetching a source writes to `pipeline/staging/`, never to `data/`, except to re-stamp
  windows a human already approved.
- Approving a candidate writes to `data/` and to `pipeline/review-state/`.
- The Astro build reads `data/` and writes to `dist/`. It never writes back.

The local review is the approval. GitHub is the merge gate and audit log, not the review.

## Invariants

- Every subject folder has exactly one `meta.toml`, agreeing with the `data.yaml` beside it.
- Every source named in a `meta.toml` resolves to a real `data/_sources/` file.
- No source config lives outside `data/`.
- `pipeline/core/` imports neither `pipeline/sources/` nor `pipeline/review/`.

## Finding things

Use CodeGraph to locate and understand code instead of reading directory listings by hand:

- `codegraph explore "<symbol or question>"` from the shell.
- The `codegraph_explore` MCP tool from an agent, which returns verbatim source plus call
  paths and blast radius.

Reach for it before grep, find, or opening files speculatively.
