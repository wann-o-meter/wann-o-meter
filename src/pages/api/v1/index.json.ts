import type { APIRoute } from "astro";
import { getAllCategories, getPagesInCategory } from "../../../../lib/pages";

export const GET: APIRoute = () => {
  const index: Record<string, string[]> = {};
  for (const category of getAllCategories()) {
    index[category] = getPagesInCategory(category)
      .map((p) => p.slug)
      .sort((a, b) => a.localeCompare(b, "de"));
  }
  return new Response(JSON.stringify(index, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
