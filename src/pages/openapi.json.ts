import type { APIRoute } from "astro";
import { z } from "zod";
import { allFristSummaries, fristDetailSchema, fristSummarySchema } from "../../lib/frist-api";
import { allFristTasks, yearsFor } from "../../lib/tasks";

// The spec used to be a hand-kept file in public/ and it drifted, as such files
// do. Now the paths are the only part written by hand: the response schemas come
// out of the Zod objects the routes serialise through, and every example and
// enum comes from the data, so neither can describe something the API does not do.

const derived = (schema: z.ZodType) => z.toJSONSchema(schema, { io: "input" });
const ref = (name: string) => ({ $ref: `#/components/schemas/${name}` });
const ok = (description: string, schema: object) => ({
  "200": { description, content: { "application/json": { schema } } },
});

export const GET: APIRoute = () => {
  const fristen = allFristSummaries();
  const ids = fristen.map((f) => f.id);
  // Only a Frist the statute fixes by itself has a day to put in a calendar.
  const feeds = allFristTasks().flatMap(({ task }) =>
    yearsFor(task).map((year) => `${task.id}/${year}`),
  );

  const spec = {
    openapi: "3.1.0",
    info: {
      title: "Wann-O-Meter API",
      version: "2.0.0",
      description: [
        `German statutory deadlines, machine readable. ${fristen.length} Fristen, each naming the Paragraf it rests on, with the statute wording quoted verbatim from gesetze-im-internet.de.`,
        "Gesetze genießen keinen urheberrechtlichen Schutz (§ 5 Abs. 1 UrhG), so quote them freely and cite gesetze-im-internet.de rather than this site.",
        "No authentication and no rate limit. Please cache instead of re-fetching the same URL.",
        "See /llms.txt for a plain-text overview.",
      ].join(" "),
      license: {
        name: "MIT for the code, the statute text is gemeinfrei under § 5 Abs. 1 UrhG",
        url: "https://www.gesetze-im-internet.de/urhg/__5.html",
      },
    },
    servers: [{ url: "https://wannometer.de/" }],
    paths: {
      "/api/v1/fristen.json": {
        get: {
          summary: "Every Frist with the Paragraf it comes from",
          description:
            "The index. Each entry names its Gesetz. Fetch one Frist's wording and dates via its dataUrl.",
          operationId: "getFristen",
          responses: ok("Array of Fristen", { type: "array", items: ref("FristSummary") }),
        },
      },
      "/api/v1/fristen/{id}.json": {
        get: {
          summary: "One Frist, with the statute wording and its dates",
          description:
            "Includes the quoted Absätze verbatim. A Frist the statute fixes by itself carries one entry per year in occurrences. A Frist counted from a date you supply carries none, because the day depends on your input.",
          operationId: "getFrist",
          parameters: [
            {
              name: "id",
              in: "path",
              required: true,
              schema: { type: "string", enum: ids },
              example: ids[0],
            },
          ],
          responses: {
            ...ok("One Frist", ref("FristDetail")),
            "404": { description: "Unknown Frist" },
          },
        },
      },
      "/frist/{fristPath}.ics": {
        get: {
          summary: "One Frist as a calendar entry",
          description: "fristPath is {id}/{year}, and exists only where the statute fixes the day.",
          operationId: "getFristIcs",
          parameters: [
            {
              name: "fristPath",
              in: "path",
              required: true,
              schema: { type: "string", enum: feeds },
              example: feeds[0],
            },
          ],
          responses: {
            "200": {
              description: "iCalendar, RFC 5545",
              content: { "text/calendar": { schema: { type: "string" } } },
            },
            "404": { description: "Unknown Frist or year" },
          },
        },
      },
    },
    components: {
      schemas: {
        FristSummary: derived(fristSummarySchema),
        FristDetail: derived(fristDetailSchema),
      },
    },
  };

  return new Response(JSON.stringify(spec, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
