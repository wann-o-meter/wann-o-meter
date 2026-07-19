# Contributing

Thanks for wanting to help make wann's calendar more complete. There are two
ways to contribute a data source, depending on how much work you want to do,
plus the usual code contribution path.

## 1. Suggest a source (low effort)

Add a line to [`data/community-sources.txt`](data/community-sources.txt) and
open a pull request:

```
@your-github-handle https://example.com/the-page-you-found
```

The handle is optional. An operator will run the URL through the crawler,
review the extracted result, and open the actual data PR - you'll be
credited as the source on the resulting page (see `contributed_by` below)
once it's live.

## 2. Contribute the data directly (more effort, faster to land)

If you already have clean, sourced data, skip the crawler and author the
files yourself:

```
data/{category}/{slug}/
  page.yaml   # title, description, tags - written once, survives re-scrapes
  data.yaml   # subject, source, and either `windows` (calendar-style facts)
              # or `raw_data` (arbitrary scraped content) - see lib/schema.ts
              # and lib/pages-schema.ts for the exact shape.
```

Every field is validated against the same Zod schema the site's build uses
(`bun run build` runs this automatically) - a malformed file fails the build
instead of silently shipping bad data, so that's your review gate. Open a PR
with your `data.yaml`/`page.yaml` pair; a maintainer reviews and merges it
like anything else here (no auto-merge, GitHub is the queue).

### Attribution

Add yourself to a source entry with `contributed_by`:

```yaml
source:
  url: https://example.com/the-page-you-found
  license: tos_checked
  retrieved_at: "2026-07-19"
  extraction: manual
  contributed_by: your-github-handle
```

It shows up on the page's "Quelle & Stand" section, linked to
`github.com/your-github-handle`.

### Licenses

- Your `data.yaml`/`page.yaml` contribution is licensed under the same terms
  as the rest of `/data` - see [`data/LICENSE`](data/LICENSE) (CC BY 4.0).
- Cite the real origin of the facts in `source.url` and pick the closest
  `source.license` value from `lib/schema.ts`'s `licenseSchema` - if the
  origin has its own license/terms of use that differ from CC BY 4.0, note
  that in `source.license_note`.
- Don't submit data you don't have the right to redistribute.

## 3. Code contributions

Standard PR flow - fork, branch, `bun run test` and `bun run build` locally
before opening a PR (both run against every new data file too). The code
(`/lib`, `/src`, `/pipeline`, everything outside `/data`) is MIT-licensed,
see [`LICENSE`](LICENSE).

## Getting stuck / questions

Open a GitHub Issue - that's the queue for everything here (source
suggestions included, if you'd rather not touch YAML at all).
