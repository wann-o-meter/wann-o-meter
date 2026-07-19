import type { APIRoute } from "astro";
import { getAllCalendarEntries } from "../../../../../lib/calendar-sources";

// The one place that resolves a category-agnostic id into real data - every
// content type's specifics are already hidden inside getAllCalendarEntries().
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
