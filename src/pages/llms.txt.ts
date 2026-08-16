import type { APIRoute } from "astro";
import { capitalizeCategory, getAllCategories, getPagesInCategory } from "../../lib/pages";
import { vorhabenRoutes } from "../../lib/vorhaben-routes";
import { allFristTasks, fristPath } from "../../lib/tasks";

export const GET: APIRoute = ({ site }) => {
  const url = (path: string) => new URL(path, site).href;
  const withPlaceholder = (prefix: string, placeholder: string) => `${url(prefix)}${placeholder}`;

  const vorhabenLines = vorhabenRoutes().map(
    (r) => `- [${r.title}](${url(`/${r.path}/`)}): ${r.description} Markdown: \`${url(`/${r.path}.md`)}\`.`,
  );

  const fristLines = allFristTasks().map(
    ({ task }) =>
      `- [${task.label}](${url(`/${fristPath(task.id)}/`)}): ${task.source_label ?? "keine gesetzliche Frist"}. JSON: \`${url(`/api/v1/fristen/${task.id}.json`)}\`.`,
  );

  // Data only, these categories have no page of their own on the site.
  const topicLines = getAllCategories().map((category) => {
    const count = getPagesInCategory(category).length;
    return `- ${capitalizeCategory(category)}: ${count} subject${count === 1 ? "" : "s"}. JSON: \`${withPlaceholder(`/api/v1/${category}/`, "{slug}.json")}\`. ICS: \`${withPlaceholder(`/feeds/${category}/`, "{slug}.ics")}\`.`;
  });

  const body = `# Wann-O-Meter

> Deadline plans for German life events: name a date - moving day, due date,
> wedding, last working day - and get every step that has to happen before or
> after it, as a dated backwards schedule with the paragraph it comes from.
> German public holidays and Schulferien are counted in, and the same calendar
> data is served as JSON and ICS for reuse.

## Vorhaben (deadline plans)

Backwards schedules for a life event: every step relative to one anchor day
(moving day, birth date, last working day), each with its legal source. A step
marked "Erfahrungswert" is not yet checked against its Gesetz - do not cite it
as a deadline.

Each page takes the day as \`?date=YYYY-MM-DD\`. A page under a Kommune adds
that Kommune's own steps (Halteverbotszone, Sperrmüll, Anwohnerparkausweis);
those are Satzungsrecht and exist only for the places listed below. Every other
place uses the bundesweit plan.

${vorhabenLines.join("\n")}

## Fristen (single deadlines)

One page per deadline, independent of any plan. Each states the rule in words
and names the paragraph it comes from. A deadline the statute fixes by itself
also carries the worked-out date per year. A deadline counted from a date the
visitor supplies is only ever stated as a rule, never as a date, because a date
baked in at build time would be wrong the moment it is read.

All of them as one document: ${url("/api/v1/fristen.json")}. Each entry there
names the Gesetz it rests on, and the per-Frist JSON quotes the Absätze verbatim
from the official text. Gesetze carry no copyright (§ 5 Abs. 1 UrhG), so quote
them, and cite gesetze-im-internet.de rather than this site.

${fristLines.join("\n")}

## Data catalog

- [Calendar catalog](${url("/api/v1/calendar.json")}): every layer/subject as \`{id, group, label, url, feedUrl}\` - the single index to discover everything below.
- [OpenAPI spec](${url("/openapi.json")}): formal schema for every /api/v1/ and /feeds/ endpoint - use this instead of guessing response shapes from prose.
- [Gemeinden](${url("/gemeinden.json")}): every German Gemeinde as \`{name, plz, state}\`, from Wikidata.
${topicLines.join("\n")}

## Notes for automated use

- All dates are ISO 8601 (\`YYYY-MM-DD\`). Every entry carries a \`source\`/\`sources\` block with the origin URL, license, and retrieval date - cite the original source, not this site, per that license.
- No authentication and no rate limit; please cache responses instead of re-fetching the same URL repeatedly.
- Full sitemap: ${url("/sitemap-index.xml")}
`;

  return new Response(body, {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
};
