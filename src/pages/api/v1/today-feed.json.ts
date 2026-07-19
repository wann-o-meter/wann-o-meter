import type { APIRoute } from "astro";
import { getTodayFeedEntries } from "../../../../lib/calendar-sources";

export const GET: APIRoute = () => {
  return new Response(JSON.stringify(getTodayFeedEntries()), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
