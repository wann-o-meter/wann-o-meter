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
/src/components       Kalender.vue — the one Vue island
/src/pages            Astro pages, /api/v1/ JSON, /feeds/ ICS
```

## Frontend Commands

| Command         | Does                           |
| :-------------- | :----------------------------- |
| `bun install`   | Install dependencies           |
| `bun run dev`   | Dev server on `localhost:4321` |
| `bun run build` | Production build to `./dist/`  |
| `bun run test`  | Vitest suite for `/lib`        |

## Deploy

URLs:

- <https://wannometer.de>
- <https://wann-o-meter.github.io> which redirects to <https://wannometer.de>
- <https://wann-o-meter> which redirects to <https://wannometer.de>
