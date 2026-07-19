import type { APIRoute } from "astro";
import { getAllPages, getPageEvents } from "../../../lib/pages";
import type { Page, PageEvent } from "../../../lib/pages";
import { generateIcs } from "../../../lib/ics";

// Replaces feeds/[category]/[slug].ics.ts - a rest param is required once a
// category can nest (see src/pages/[...path].astro's docstring for why).
// Only pages with at least one event get a feed - nothing else to put in a
// calendar. Rows are either single dates (LLM-labeled/regex-found scraped
// content) or date ranges (materialized calendar windows - see
// getPageEvents()'s `to` field), not necessarily curated/verified.
export function getStaticPaths() {
  return getAllPages()
    .map((p) => ({ page: p, events: getPageEvents(p) }))
    .filter(({ events }) => events.length > 0)
    .map(({ page, events }) => ({
      params: { path: `${page.category}/${page.slug}` },
      props: { page, events },
    }));
}

export const GET: APIRoute = ({ props }) => {
  const { page, events } = props as { page: Page; events: PageEvent[] };
  const sourceUrls = page.data.source.map((s) => s.url).join(", ");
  const ics = generateIcs(
    events.map((event: PageEvent) => ({
      uid: `${page.category}-${page.slug}-${event.date}@wann.local`,
      from: event.date,
      to: event.to ?? event.date,
      title: page.meta.title,
      description: `${event.label} - ${sourceUrls}`,
      url: page.data.source[0].url,
    })),
    page.meta.title,
  );
  return new Response(ics, {
    headers: {
      "Content-Type": "text/calendar; charset=utf-8",
      "Content-Disposition": `attachment; filename="${page.category.replace(/\//g, "-")}-${page.slug}.ics"`,
    },
  });
};
