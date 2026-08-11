import type { APIRoute } from "astro";
import { getAllCalendarEntries } from "../../../../../lib/calendar-sources";

export function getStaticPaths() {
  return getAllCalendarEntries().map((entry) => ({
    params: { id: entry.id },
    props: { entry },
  }));
}

export const GET: APIRoute = ({ props }) => {
  return new Response(JSON.stringify(props.entry), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
