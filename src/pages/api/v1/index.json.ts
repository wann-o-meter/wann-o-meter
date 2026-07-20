import type { APIRoute } from "astro";
import { getAllCategories, getPagesInCategory } from "../../../../lib/pages";

// One-shot map of every category to its page slugs - lets a consumer
// discover the full site tree (and build /api/v1/{category}/{slug}.json or
// /api/v1/{category}/all.json URLs) without walking every page listing.
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
