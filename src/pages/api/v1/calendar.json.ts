import type { APIRoute } from "astro";
import { getAllCalendarEntries } from "../../../../lib/calendar-sources";

// Lightweight catalog for the calendar's layer search - no `windows`, so
// this stays small even with 200+ Feiertage entries. Full per-entry data is
// fetched lazily via /api/v1/calendar/[id].json once a layer is actually added.
export const GET: APIRoute = () => {
  const catalog = getAllCalendarEntries().map(({ id, group, label, url, feedUrl }) => ({
    id,
    group,
    label,
    url,
    feedUrl,
  }));
  return new Response(JSON.stringify(catalog), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
