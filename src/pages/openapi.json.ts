import type { APIRoute } from "astro";
import { getAllCategories, getPagesInCategory } from "../../lib/pages";
import { getAllCalendarEntries } from "../../lib/calendar-sources";
import { allFristTasks, fristPath, yearsFor } from "../../lib/tasks";
import { z } from "zod";
import { sourceSchema } from "../../lib/schema";
import { pageDataSchema, pageMetaSchema } from "../../lib/pages-schema";
import { fristDetailSchema, fristSummarySchema, allFristSummaries } from "../../lib/frist-api";

// The spec used to be a hand-kept file in public/. It drifted, as such files do:
// it still advertised categories that had been deleted and documented four of
// the seven routes. Now everything countable comes from the same functions the
// routes themselves call, so a deleted category or a new Frist shows up here on
// the next build. Only the prose and the response shapes are written by hand,
// and those are in this one file rather than spread across a JSON document.

// Anything the loader already validates with Zod is emitted from that schema
// rather than described a second time by hand. What is left below as a literal
// is exactly the part the code has no contract for yet.
// "input" rather than "output": a schema that ends in .transform() has no
// output shape JSON Schema can express, and the input shape is what a consumer
// of this API actually receives anyway.
const derived = (schema: z.ZodType) => z.toJSONSchema(schema, { io: "input" });

const json = (schema: object) => ({ "application/json": { schema } });
const ref = (name: string) => ({ $ref: `#/components/schemas/${name}` });

function ok(description: string, schema: object) {
  return { "200": { description, content: json(schema) } };
}

function pathParam(name: string, description: string, example: string) {
  return {
    name,
    in: "path",
    required: true,
    schema: { type: "string" },
    description,
    example,
  };
}

export const GET: APIRoute = () => {
  const categories = getAllCategories();
  const catalog = getAllCalendarEntries();
  const fristen = allFristTasks();
  const withFeed = fristen.filter(({ task }) => yearsFor(task).length > 0);

  // Real values, so an example in the spec is always a URL that answers.
  const someCategory = categories[0] ?? "schulferien";
  const someSlug = getPagesInCategory(someCategory)[0]?.slug ?? "bw";
  const somePath = `${someCategory}/${someSlug}`;
  const someId = catalog[0]?.id ?? `${someCategory}--${someSlug}`;
  const fristIds = allFristSummaries().map((f) => f.id);
  const someFrist = withFeed[0];
  const someFristPath = someFrist
    ? `${someFrist.task.id}/${yearsFor(someFrist.task)[0]}`
    : "steuererklaerung-abgeben/2026";

  const spec = {
    openapi: "3.1.0",
    info: {
      title: "Wann-O-Meter API",
      version: "1.0.0",
      description: [
        "Machine-readable German statutory deadlines, with the paragraph each one rests on and the statute wording quoted verbatim.",
        `${fristen.length} Fristen at /api/v1/fristen.json.`,
        `Calendar layers: ${catalog.length} across ${categories.length} ${categories.length === 1 ? "category" : "categories"} (${categories.join(", ")}).`,
        "No authentication and no rate limit, please cache instead of re-fetching the same URL.",
        "Every entry carries a source block with origin URL, license and retrieval date. Cite the original source per that license, not this API.",
        "See /llms.txt for a plain-text overview of the same data.",
      ].join(" "),
      license: {
        name: "CC BY 4.0 for the data, MIT for the code serving it",
        url: "https://creativecommons.org/licenses/by/4.0/legalcode",
      },
    },
    servers: [{ url: "https://wannometer.de/" }],
    paths: {
      "/api/v1/fristen.json": {
        get: {
          summary: "Every Frist with the paragraph it comes from",
          description:
            "The index of German statutory deadlines this site tracks. Each entry names the Gesetz it rests on. Fetch one Frist's wording and dates via its dataUrl.",
          operationId: "getFristen",
          responses: ok("Array of Fristen", { type: "array", items: ref("FristSummary") }),
        },
      },
      "/api/v1/fristen/{id}.json": {
        get: {
          summary: "One Frist, with the statute wording and its dates",
          description:
            "Includes the quoted Absätze verbatim from gesetze-im-internet.de. A Frist the statute fixes by itself also carries one entry per year in occurrences.",
          operationId: "getFrist",
          parameters: [
            {
              ...pathParam("id", "Frist identifier", fristIds[0] ?? "wohnung-kuendigen"),
              schema: { type: "string", enum: fristIds },
            },
          ],
          responses: {
            ...ok("One Frist", ref("FristDetail")),
            "404": { description: "Unknown Frist" },
          },
        },
      },
      "/api/v1/index.json": {
        get: {
          summary: "Every category and the slugs in it",
          description:
            "The smallest possible index: an object keyed by category, each value the sorted list of slugs in it. Use it to discover what {categoryPath} values are valid.",
          operationId: "getIndex",
          responses: ok("Category to slugs", {
            type: "object",
            additionalProperties: { type: "array", items: { type: "string" } },
            example: Object.fromEntries([
              ["fristen", fristIds],
              ...categories.map((c) => [c, getPagesInCategory(c).map((p) => p.slug)]),
            ]),
          }),
        },
      },
      "/api/v1/calendar.json": {
        get: {
          summary: "Calendar catalog",
          description:
            "Every calendar layer as a lightweight index without event data. The entry point for discovery: fetch one entry's full data via /api/v1/calendar/{id}.json.",
          operationId: "getCalendarCatalog",
          responses: ok("Array of catalog entries", {
            type: "array",
            items: ref("CalendarCatalogEntry"),
          }),
        },
      },
      "/api/v1/calendar/{id}.json": {
        get: {
          summary: "One calendar layer with its dates",
          operationId: "getCalendarEntry",
          parameters: [
            pathParam(
              "id",
              'The catalog entry\'s id, category and slug joined with "--".',
              someId,
            ),
          ],
          responses: {
            ...ok("Full entry including materialized windows", ref("CalendarEntry")),
            "404": { description: "Unknown id" },
          },
        },
      },
      "/api/v1/{categoryPath}.json": {
        get: {
          summary: "One page's data",
          description:
            "categoryPath is {category}/{slug} and mirrors the page's own URL one to one: the page at /{category}/{slug}/ has its JSON here.",
          operationId: "getPageData",
          parameters: [
            pathParam("categoryPath", "Full {category}/{slug} path, slashes included", somePath),
          ],
          responses: {
            ...ok("The page's validated data plus derived events", ref("Page")),
            "404": { description: "Unknown category or slug" },
          },
        },
      },
      "/api/v1/{category}/all.json": {
        get: {
          summary: "Every page in one category",
          description: "The same objects as /api/v1/{categoryPath}.json, for a whole category at once.",
          operationId: "getCategory",
          parameters: [
            {
              ...pathParam("category", "One category", someCategory),
              schema: { type: "string", enum: categories },
            },
          ],
          responses: {
            ...ok("Array of pages", { type: "array", items: ref("Page") }),
            "404": { description: "Unknown category" },
          },
        },
      },
      "/feeds/{categoryPath}.ics": {
        get: {
          summary: "Subscribable calendar feed for one page",
          description:
            "Same addressing as /api/v1/{categoryPath}.json. Only pages with at least one event have a feed.",
          operationId: "getPageIcs",
          parameters: [pathParam("categoryPath", "Full {category}/{slug} path", somePath)],
          responses: {
            "200": { description: "iCalendar, RFC 5545", content: { "text/calendar": { schema: { type: "string" } } } },
            "404": { description: "Unknown page, or the page has no events" },
          },
        },
      },
      "/frist/{fristPath}.ics": {
        get: {
          summary: "One Frist as a calendar entry",
          description:
            "Only for a Frist the statute fixes by itself, where the day does not depend on a date the visitor supplies. fristPath is {id}/{year}.",
          operationId: "getFristIcs",
          parameters: [
            {
              ...pathParam("fristPath", "{id}/{year}", someFristPath),
              schema: {
                type: "string",
                enum: withFeed.flatMap(({ task }) =>
                  yearsFor(task).map((y) => `${task.id}/${y}`),
                ),
              },
            },
          ],
          responses: {
            "200": { description: "iCalendar, RFC 5545", content: { "text/calendar": { schema: { type: "string" } } } },
            "404": { description: "Unknown Frist or year" },
          },
        },
      },
    },
    components: {
      schemas: {
        CalendarCatalogEntry: {
          type: "object",
          required: ["id", "group", "label", "url", "feedUrl"],
          properties: {
            id: { type: "string", description: 'Category and slug joined with "--"' },
            group: { type: "string", description: "Display name of the category" },
            label: { type: "string", description: "Page title" },
            url: { type: "string", description: "Path to the human-readable page" },
            feedUrl: { type: "string", description: "Path to this entry's ICS feed" },
          },
        },
        CalendarWindow: {
          type: "object",
          required: ["from", "to", "description"],
          properties: {
            from: { type: "string", format: "date" },
            to: { type: "string", format: "date" },
            description: { type: "string" },
          },
        },
        CalendarEntry: {
          allOf: [
            ref("CalendarCatalogEntry"),
            {
              type: "object",
              required: ["windows"],
              properties: { windows: { type: "array", items: ref("CalendarWindow") } },
            },
          ],
        },
        FristSummary: derived(fristSummarySchema),
        FristDetail: derived(fristDetailSchema),
        Source: derived(sourceSchema),
        PageMeta: derived(pageMetaSchema),
        PageData: derived(pageDataSchema),
        PageEvent: {
          type: "object",
          required: ["date", "label"],
          properties: {
            date: { type: "string", format: "date" },
            to: {
              type: "string",
              format: "date",
              description: "Only on a multi-day window, when it differs from date",
            },
            label: { type: "string" },
          },
        },
        Page: {
          type: "object",
          required: ["category", "slug", "meta", "data", "events"],
          properties: {
            category: { type: "string", enum: categories },
            slug: { type: "string" },
            meta: ref("PageMeta"),
            data: ref("PageData"),
            events: {
              type: "array",
              description: "Display-ready dates, resolved from data.windows where present",
              items: ref("PageEvent"),
            },
          },
        },
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
