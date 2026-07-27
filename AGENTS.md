# Agent notes

See [README.md](./README.md) for what this project is and how it's structured, and
[CONTRIBUTING.md](./CONTRIBUTING.md) for adding data sources.

## The one rule that decides where code goes

Every time window is either **decreed** (published, decided by an authority - school holidays,
a festival date) or **derived** (computable from a rule - holidays, bridge-day windows).

- Decreed → data: `data/{category}/{subject}/data.yaml`, validated against `lib/schema.ts`.
- Derived → code: a `generator.ts` in the category folder, run at build time.

Both feed into `lib/materialization.ts`, which is the only thing the calendar UI, static
pages, JSON API, and ICS feeds are allowed to read from. Don't have a page or endpoint read
`/data` directly.

## Where a file goes

Organised by **subject, not by how the data was produced**. How it was produced is a field
(`mode` in `meta.toml`), not a directory.

```text
data/{category}/{subject}/   data.yaml (facts) + page.yaml (title) + meta.toml (what it is)
data/{category}/generator.ts derived categories - no subject folders at all
data/_sources/{id}.yaml      one file per upstream: where the facts came from
```

`data/_sources/` is the single home for source config. It cannot live inside a subject folder:
one KMK page feeds sixteen `schulferien` subjects, two NASA catalogs feed one
`astronomie/sonnenfinsternis` page, and a source may exist before its subject does. A leading
underscore keeps a directory out of the category walk, so `_sources/` is never a route.

`meta.toml` names the subject, its category, its `mode` (`generator` | `transform` | `scraper` |
`manual`) and which `_sources/` entries feed it. It does **not** repeat licence or source URL -
those live in the `source:` block of the `data.yaml` beside it, where the Zod schema validates
them. `pipeline/tests/test_invariants.py` enforces all of this.

## Review

The local review app (`pipeline/review/`) is the approval step: an LLM can guess, so a human
sees each candidate before it reaches `data/`. GitHub is the merge gate and the audit log -
two different things. The scraper never writes to `data/` directly; it writes to
`pipeline/staging/`, and only an approval moves a candidate across.

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
