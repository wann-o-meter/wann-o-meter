# Pipeline

FastAPI + Jinja2 admin dashboard for the scoped crawler and review workflow.

For where each piece lives and how it fits together, see
[docs/architecture.md](../docs/architecture.md), or explore the code with CodeGraph
(`codegraph explore "<question or symbol>"`).

## CLI (`wom`)

```bash
cd pipeline
uv run wom sources                          # list sources and which runner owns each
uv run wom run wiesnkini-de                 # crawl a source, stage its candidates
uv run wom run schulferien_kmk --jahr 2028  # batch sources take --key value params
uv run wom review                           # serve the review app on :8000
uv run wom registry university_de           # fetch a Wikidata entity registry
```

- Already-reviewed candidates write straight to `data/`. Everything else waits in
  `staging/` for `wom review`.
- The CLI and the dashboard call the same functions, so they can't drift apart.

## LLM config

`pipeline/.env`, read by `core/llm.py` so every entry point sees the same config:

```sh
LLM_PROVIDER=mistral   # anthropic | openai | google | mistral | openrouter
MISTRAL_API_KEY=...    # whichever provider's key matches
LLM_MODEL=             # optional, each provider has a small default
```

`LLM_PROVIDER` defaults to `anthropic` when unset, so a missing or unread `.env` shows up
as a missing Anthropic key even on a machine configured for another provider.

## Lint, types, tests

```bash
cd pipeline
uvx ruff check .    # lint (--fix applies safe fixes)
uvx ty check        # types
uv run pytest -q    # tests
```

All three run on every push. Config lives in `pyproject.toml` under `[tool.ruff]`.
`ruff format` is available but not enforced.

## Using the dashboard

1. Go to **Crawl Sources**, paste a seed URL, click **Add Source**.
  This writes `data/_sources/<id>.yaml`.
2. Click **Run**. It crawls within scope, extracts events,
  and stages one candidate per event.
3. Go to **Review**. Approve, modify, or reject each candidate
  next to its source snapshot. Approve/modify writes straight to `data/`.
4. Commit and push `data/` and `pipeline/review-state/` yourself,
  like any other change.

Re-running a source later only surfaces genuinely new or changed candidates. Anything
matching a prior decision auto-waves-through or stays silently dropped.
