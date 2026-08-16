import type { APIRoute } from "astro";
import { allFristSummaries, fristSummarySchema } from "../../../../lib/frist-api";

export const GET: APIRoute = () => {
  // Parsed rather than trusted: the response cannot drift from the schema
  // /openapi.json publishes, because it is the schema that produces it.
  const body = allFristSummaries().map((f) => fristSummarySchema.parse(f));
  return new Response(JSON.stringify(body, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
