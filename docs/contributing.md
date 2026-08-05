# Contributing

Three ways to help, in increasing effort.

## Suggest a source

- Add a line to [`data/community-sources.txt`](../data/community-sources.txt): `@your-github-handle https://example.com/the-page-you-found`.
- The handle is optional. An operator runs the URL through the crawler, reviews the result, and opens the data PR.
- You get credited as the source (see `contributed_by` below) once it's live.

## Contribute data directly

Skip the crawler and author the files yourself:

```
data/{category}/{slug}/
  page.yaml   # title, description, tags
  data.yaml   # subject, source, and either `windows` or `raw_data` (see lib/schema.ts)
  meta.toml   # subject, category, mode = "manual", sources = [...] if a data/_sources/ entry feeds it
```

- Every field is validated against the site's Zod schema (`bun run build` runs this automatically).
- Open a PR with your `data.yaml`, `page.yaml`, and `meta.toml`. A maintainer reviews and merges it, no auto-merge.

### Attribution

Add yourself to a source entry:

```yaml
source:
  url: https://example.com/the-page-you-found
  license: tos_checked
  retrieved_at: "2026-07-19"
  extraction: manual
  contributed_by: your-github-handle
```

This shows up on the page, linked to `github.com/your-github-handle`.

### Licenses

- Your contribution is licensed under the same terms as the rest of `/data`. See [`data/LICENSE`](../data/LICENSE) (CC BY 4.0).
- Cite the real origin in `source.url` and pick the closest `source.license` from `lib/schema.ts`'s `licenseSchema`. Note any deviating terms in `source.license_note`.
- Don't submit data you don't have the right to redistribute.

## Code contributions

- Standard PR flow: fork, branch, run `bun run test` and `bun run build` locally.
- Code (`/lib`, `/src`, everything outside `/data`) is MIT-licensed. See [`LICENSE`](../LICENSE).

## Getting stuck

Open a GitHub Issue. It's the queue for everything here, source suggestions included.
