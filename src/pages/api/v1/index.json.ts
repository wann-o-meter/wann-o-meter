import type { APIRoute } from "astro";
import { getAllCategories, getPagesInCategory } from "../../../../lib/pages";
import { allFristSummaries } from "../../../../lib/frist-api";

export const GET: APIRoute = () => {
  const index: Record<string, string[]> = {
    fristen: allFristSummaries().map((f) => f.id),
  };
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
