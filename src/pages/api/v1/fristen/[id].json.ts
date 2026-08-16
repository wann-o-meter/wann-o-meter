import type { APIRoute } from "astro";
import { fristDetailSchema, fristDetails } from "../../../../../lib/frist-api";

export function getStaticPaths() {
  return fristDetails().map((frist) => ({ params: { id: frist.id }, props: { frist } }));
}

export const GET: APIRoute = ({ props }) => {
  const body = fristDetailSchema.parse(props.frist);
  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
