# AI Coding Guidelines

How AI agents (Claude Code, Mistral Vibe, etc.) should approach this project. For the
project's structure, see [docs/architecture.md](./docs/architecture.md).

- Keep code simple and maintainable.
- Comment only what isn't self-explanatory. Never restate what the code does or describe
  behaviour that no longer exists.
- Write code, comments, and identifiers in English.
- Use plain language: no em-dashes, no semicolons.
- Write tests for core components (`/lib`, `pipeline/`). Skip tests for the frontend or for
  code that changes rapidly.
- Commit with conventional commits, under 100 characters.
- Prefer short bulletpoints instead of texts.
