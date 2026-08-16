# AI Coding Guidelines

How AI agents (Claude Code, Mistral Vibe, etc.) should approach this project. For the
project's structure, see [README.md](./README.md).

- Keep code simple and maintainable.
- Rules and Fristen live in yaml under `data/`, never in TypeScript. Code reads a
  small vocabulary of steps (`add_months`, `snap`, `roll`, `first_year`) and knows
  no law. Changing a Frist means editing one yaml entry, not hunting for it in a
  function. `lib/notice-period.ts` predates this rule and still needs converting.
- Comment only what isn't self-explanatory. Never restate what the code does or describe
  behaviour that no longer exists.
- Write code, comments, and identifiers in English.
- Use plain language: no em-dashes, no semicolons.
- Commit with conventional commits, under 100 characters.
- Prefer short bulletpoints instead of texts.
