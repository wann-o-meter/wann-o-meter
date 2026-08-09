# ICS worker

Serves a deadline plan as a subscribable calendar:

```
webcal://wannometer.de/ics/umzug?date=2026-12-26&variant=rottenburg&facets=auto
```

- Stateless: the plan is recomputed per request from `(vorhaben, variant, date, facets)`, all of which are in the URL. Nothing stored, no account, no personal data at the edge.
- Reads the plan data from `/api/v1/vorhaben/<vorhaben>/<variant>.json`, a static build artefact.
- Runs on the existing Cloudflare zone in front of GitHub Pages. Every other path falls through to the static origin.

Why server side at all: `DeadlinePlanner.vue` already builds the same ICS in the browser for a one-off download, but a Blob has no URL that survives, so nothing can subscribe to it.

## Local run

The static origin has to be reachable, so serve `dist/` separately and point the worker at it:

```sh
bun run build
python3 -m http.server 8800 --directory dist &
cd workers/ics && bunx wrangler dev --port 8799 --var PLAN_ORIGIN:http://127.0.0.1:8800
curl "http://127.0.0.1:8799/ics/umzug?date=2026-12-26&variant=rottenburg"
```

## Deploy

```sh
cd workers/ics && bunx wrangler deploy
```

Needs a Cloudflare account with the `wannometer.de` zone. Deploy the site first, so `/api/v1/vorhaben/*.json` exists.
