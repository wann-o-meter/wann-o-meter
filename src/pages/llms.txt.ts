import type { APIRoute } from "astro";
import { capitalizeCategory, getAllCategories, getPagesInCategory } from "../../lib/pages";
import { vorhabenRoutes } from "../../lib/vorhaben-routes";

// llms.txt (llmstxt.org convention): a machine-readable summary for LLMs and
// answer engines, pointing straight at the structured JSON/ICS data instead
// of leaving them to scrape rendered HTML. Absolute URLs throughout - unlike
// an HTML page, a plain-text file has no implicit base URL for a relative
// link to resolve against.
export const GET: APIRoute = ({ site }) => {
  const url = (path: string) => new URL(path, site).href;

  // Deadline verticals aren't part of getAllCategories() (they're reserved,
  // see lib/pages.ts) and have no JSON endpoint - the .md twin is the
  // machine-readable form, so it goes first on each line.
  const vorhabenLines = vorhabenRoutes().map(
    (r) => `- [${r.title}](${url(`/${r.path}/`)}): ${r.description} Markdown: \`${url(`/${r.path}.md`)}\`.`,
  );

  // Calendar categories have no HTML page any more, only data endpoints -
  // link the bulk JSON, never a /{category}/ URL that would 404. `new URL()`
  // would percent-encode the "{slug}" placeholder, so append it as a plain
  // string to keep it readable.
  const topicLines = getAllCategories().map((category) => {
    const count = getPagesInCategory(category).length;
    const one = `${url(`/api/v1/${category}/`)}{slug}.json`;
    const ics = `${url(`/feeds/${category}/`)}{slug}.ics`;
    return `- [${capitalizeCategory(category)}](${url(`/api/v1/${category}/all.json`)}): ${count} subject${count === 1 ? "" : "s"} in one JSON file. Single subject: \`${one}\`. ICS feed: \`${ics}\`.`;
  });

  const body = `# Wann-O-Meter

> "Wann muss ich anfangen?" - backwards deadline plans for German life events
> (Umzug, Geburt, Hochzeit, Jobwechsel): pick the target date, get every step
> that has to happen before it, each with its legal source. Plus the calendar
> data those plans are built on (public holidays, school holidays, bridge-day
> vacation windows) as JSON and subscribable ICS feeds - fetch the data, no
> scraping needed.

## Vorhaben (deadline plans)

Backwards schedules for a life event: every step relative to one anchor day
(moving day, birth date, last working day), each with its legal source. A step
marked "Quelle fehlt" is not yet checked against its Gesetz - do not cite it
as a deadline. Every plan page has a \`.md\` twin with the same steps and no
HTML chrome - prefer that one.

${vorhabenLines.join("\n")}

## Data catalog

Calendar data is API-only: there are no HTML pages for it, just the endpoints
below.

- [Calendar catalog](${url("/api/v1/calendar.json")}): every layer/subject on the site as \`{id, group, label, url, feedUrl}\` - the single index to discover everything below.
- [Category index](${url("/api/v1/index.json")}): every category mapped to its subject slugs, for building \`/api/v1/{category}/{slug}.json\` URLs.
- [OpenAPI spec](${url("/openapi.json")}): formal schema for the per-subject JSON and ICS endpoints - use this instead of guessing response shapes from prose.
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
