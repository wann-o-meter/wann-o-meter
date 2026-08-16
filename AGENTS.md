# AI Coding Guidelines

How AI agents (Claude Code, Mistral Vibe, etc.) should approach this project. For the
project's structure, see [README.md](./README.md).

- Keep code simple and maintainable.
- Rules and Fristen live in yaml under `data/`, never in TypeScript. Code reads a
  small vocabulary of steps (`add_months`, `snap`, `roll`, `first_year`) and knows
  no law. Changing a Frist means editing one yaml entry, not hunting for it in a
  function.
- A Frist no such step can express keeps its code beside its yaml, under the same
  name: `data/fristen/wohnung-kuendigen.ts` next to `wohnung-kuendigen.yaml`, found
  by the Frist's id. That is the only place a law may be written as code.
- Statute wording is never typed by hand. `data/fristen/*.yaml` names the Absätze
  and `bun run gesetze` pulls the words from the official XML.
- Comment only what isn't self-explanatory. Never restate what the code does or describe
  behaviour that no longer exists.
- Write code, comments, and identifiers in English.
- Use plain language: no em-dashes, no semicolons.
- Commit with conventional commits, under 100 characters.
- Prefer short bulletpoints instead of texts.
