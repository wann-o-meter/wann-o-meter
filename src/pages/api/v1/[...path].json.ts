import type { APIRoute } from "astro";
import { getAllPages, getPageEvents } from "../../../../lib/pages";

// Replaces api/v1/[category]/[slug].json.ts - a rest param is required once
// a category can nest (see src/pages/[...path].astro's docstring for why),
// and params.path already carries the full "{category}/{slug}" string
// (category itself "/"-joined), so this needs no change beyond that.
export function getStaticPaths() {
  return getAllPages().map((p) => ({
    params: { path: `${p.category}/${p.slug}` },
    props: { page: p },
  }));
}

export const GET: APIRoute = ({ props }) => {
  // `events` is a derived field (not part of the validated PageData shape) -
  // LLM-labeled or regex-found dates, computed once here so consumers (e.g.
  // the calendar's "Seiten" layer) don't re-implement the parsing/labeling
  // heuristic client-side.
  const body = { ...props.page, events: getPageEvents(props.page) };
  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
