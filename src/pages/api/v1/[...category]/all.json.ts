import type { APIRoute } from "astro";
import { getAllCategories, getPagesInCategory, getPageEvents } from "../../../../../lib/pages";

// Bundles every page in one category into a single response - the
// per-page equivalent of api/v1/[...path].json.ts, for a consumer that
// wants a whole category (e.g. all 16 Schulferien Bundeslaender) without
// firing one request per slug. [...category] mirrors src/pages/[...path].astro:
// a rest param is required since a category can nest (see that file's
// docstring), followed here by the literal "all.json" leaf.
export function getStaticPaths() {
  return getAllCategories().map((category) => ({
    params: { category },
    props: { category },
  }));
}

export const GET: APIRoute = ({ props }) => {
  const body = getPagesInCategory(props.category).map((page) => ({
    ...page,
    events: getPageEvents(page),
  }));
  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
