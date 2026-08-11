# Wann-O-Meter

Deadline planner: it works backwards from your date and tells you when to start.

## Architecture

- Vorhaben and their deadlines live in `data/vorhaben.yaml` and `data/{vorhaben}/`.
- Time windows live in `data/`, as plain YAML or a `generator.ts` that computes them.

```text
/lib                  Zod schema, holiday rules, deadline math, ICS generator
/data/vorhaben.yaml   Vorhaben definitions, deadlines per variant
/data/_sources        One YAML per upstream source
/data/{category}/...  data.yaml + page.yaml + meta.toml per subject
/data/{category}/generator.ts  Derived categories (feiertage, urlaubsfenster)
/src/components       DeadlinePlanner.vue and Index.vue, the Vue islands
/src/pages            Astro pages, /api/v1/ JSON, /feeds/ ICS
```

## Frontend Commands

| Command         | Does                           |
| :-------------- | :----------------------------- |
| `bun install`   | Install dependencies           |
| `bun run dev`   | Dev server on `localhost:4321` |
| `bun run build` | Production build to `./dist/`  |

## Deploy

URLs:

- <https://wannometer.de>
- <https://wann-o-meter.github.io> which redirects to <https://wannometer.de>
- <https://wann-o-meter> which redirects to <https://wannometer.de>
