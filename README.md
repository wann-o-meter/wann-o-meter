# Wann-O-Meter

Simple web-based platform that allows you to visualize time windows as layers in a calendar.

## Architecture

- Time windows live in `data/`.
- Each one is either a plain YAML file or a `generator.ts` that computes it.
- Full data flow, file formats, and invariants: [docs/architecture.md](./docs/architecture.md).

```text
/lib                  Zod schema, holiday/bridge-day rules, materialization, ICS generator
/data/_sources        One YAML per upstream source
/data/{category}/...  Decreed facts: data.yaml + page.yaml + meta.toml per subject
/data/{category}/generator.ts  Derived categories (feiertage, urlaubsfenster) — no YAML
/pipeline             Python: source -> extraction -> staging -> review -> data/
/src/components       Kalender.vue — the one Vue island
/src/pages            Astro pages, /api/v1/ JSON, /feeds/ ICS
```

## Frontend Commands

| Command | Does |
| :------ | :--- |
| `bun install`   | Install dependencies |
| `bun run dev`   | Dev server on `localhost:4321` |
| `bun run build` | Production build to `./dist/` |
| `bun run test`  | Vitest suite for `/lib` |

## Pipeline Commands

```sh
cd pipeline
uv run wom sources                            # list available sources
uv run wom run schulferien_kmk --jahr 2028    # fetch a source, stage candidates
uv run wom review                             # review UI on http://localhost:8000
```

- A source is fetched, extracted, and validated against `lib/schema.ts` before landing in `pipeline/staging/`.
- A human reviews every candidate there. The scraper never writes to `data/` directly.
- Details: [pipeline/README.md](./pipeline/README.md).

## Known data gap

- School holidays are filled in for all 16 states for 2026 and 2027, verified against the official KMK ICS calendars.
- 2028 has only code-computed holiday/bridge-day windows. An honest gap beats a guessed one.

## Contributing & license

- Suggest a source (by URL) or contribute data directly as YAML: see [docs/contributing.md](./docs/contributing.md).
- Code is MIT ([LICENSE](./LICENSE)).
- The curated dataset under `/data` is CC BY 4.0 ([data/LICENSE](./data/LICENSE)).

## Deploy

URLs:
- <https://wannometer.de>
- <https://wann-o-meter.github.io> which redirects to <https://wannometer.de>
- <https://wann-o-meter> which redirects to <https://wannometer.de>
