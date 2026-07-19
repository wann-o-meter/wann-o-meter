import type { APIRoute } from "astro";
import { capitalizeCategory, getAllCategories, getPagesInCategory } from "../../lib/pages";

// llms.txt (llmstxt.org convention): a machine-readable summary for LLMs and
// answer engines, pointing straight at the structured JSON/ICS data instead
// of leaving them to scrape rendered HTML. Absolute URLs throughout - unlike
// an HTML page, a plain-text file has no implicit base URL for a relative
// link to resolve against.
export const GET: APIRoute = ({ site }) => {
  const url = (path: string) => new URL(path, site).href;
  // `new URL()` percent-encodes "{" and "}", which would turn a literal
  // placeholder segment like "{slug}" into "%7Bslug%7D" - build the real
  // (encodable) prefix through URL, then append the placeholder as a plain
  // string so it stays human/LLM-readable.
  const withPlaceholder = (prefix: string, placeholder: string) => `${url(prefix)}${placeholder}`;

  const topicLines = getAllCategories().map((category) => {
    const count = getPagesInCategory(category).length;
    return `- [${capitalizeCategory(category)}](${url(`/${category}/`)}): ${count} page${count === 1 ? "" : "s"}. JSON: \`${withPlaceholder(`/api/v1/${category}/`, "{slug}.json")}\`. ICS (where dated events exist): \`${withPlaceholder(`/feeds/${category}/`, "{slug}.ics")}\`.`;
  });

  const body = `# Wann-O-Meter

> A structured, machine-readable calendar of "when is X" answers for Germany
> and beyond: public holidays, optimal vacation windows (bridge days), a
> seasonal produce calendar, and curated civic-data topic pages (elections,
> astronomical events, ...). Every entry has a canonical page, a JSON
> endpoint, and a subscribable ICS calendar feed - fetch the JSON, no
> scraping needed.

## Data catalog

- [Calendar catalog](${url("/api/v1/calendar.json")}): every layer/subject on the site as \`{id, group, label, url, feedUrl}\` - the single index to discover everything below.
- [OpenAPI spec](${url("/openapi.json")}): formal schema for every /api/v1/ and /feeds/ endpoint below - use this instead of guessing response shapes from prose.
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
