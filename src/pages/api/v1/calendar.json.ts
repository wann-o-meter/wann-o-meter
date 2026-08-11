import type { APIRoute } from "astro";
import { getAllCalendarEntries } from "../../../../lib/calendar-sources";

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
