import type { APIRoute } from "astro";
import { getAllPages, getPageEvents } from "../../../../lib/pages";

export function getStaticPaths() {
  return getAllPages().map((p) => ({
    params: { path: `${p.category}/${p.slug}` },
    props: { page: p },
  }));
}

export const GET: APIRoute = ({ props }) => {
  const body = { ...props.page, events: getPageEvents(props.page) };
  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
