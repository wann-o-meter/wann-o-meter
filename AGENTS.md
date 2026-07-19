# Agent notes

See [README.md](./README.md) for what this project is and how it's structured, and
[CONTRIBUTING.md](./CONTRIBUTING.md) for adding data sources.

## The one rule that decides where code goes

Every time window is either **decreed** (published, decided by an authority - school holidays,
a festival date) or **derived** (computable from a rule - holidays, bridge-day windows).

- Decreed → data: a YAML file under `/data`, validated against `lib/schema.ts`.
- Derived → code: `/lib`, computed at build time.

Both feed into `lib/materialisierung.ts`, which is the only thing the calendar UI, static
pages, JSON API, and ICS feeds are allowed to read from. Don't have a page or endpoint read
`/data` directly.

## Commands

| Command         | Does                                                        |
| :-------------- | :----------------------------------------------------------- |
| `bun install`    | install dependencies                                         |
| `bun run dev`    | dev server on `localhost:4321`                                |
| `bun run build`  | production build to `./dist/` (also validates every `/data` file against the Zod schema) |
| `bun run test`   | Vitest suite for `/lib`                                       |

When starting the dev server yourself, run it in background mode so it doesn't block the
session:

```
astro dev --background
```

Manage it with `astro dev stop`, `astro dev status`, and `astro dev logs`.

## Astro docs

- [Routing](https://docs.astro.build/en/guides/routing/)
- [Astro components](https://docs.astro.build/en/basics/astro-components/)
- [Framework components (Vue, etc.)](https://docs.astro.build/en/guides/framework-components/)
- [Content collections](https://docs.astro.build/en/guides/content-collections/)
- [Styling](https://docs.astro.build/en/guides/styling/)
- [i18n](https://docs.astro.build/en/guides/internationalization/)
