import type { APIRoute } from "astro";
import { getAllCategories, getPagesInCategory, getPageEvents } from "../../../../../lib/pages";

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
