// Generic pages built from accepted scraper output (see pipeline/main.py
// POST /create-page). Two files per folder, deliberately split: data.yaml
// (facts, rewritten on every re-scrape) and page.yaml (title/description/
// tags, written only on first creation so human edits survive a re-scrape).
import { z } from "zod";
import { rawWindowSchema, sourceSchema } from "./schema";

export const pageMetaSchema = z.object({
  title: z.string(),
  description: z.string().default(""),
  tags: z.array(z.string()).default([]),
  featured: z.boolean().default(true),
});

// A category is a "/"-joined path of 1-4 URL-safe segments (data/{seg1}/
// {seg2}/.../{slug}/ on disk, see lib/pages.ts's recursive walk) - lets
// pages nest ("sport/fussball/bundesliga") while a plain single-segment
// value ("astronomie") stays valid, so existing depth-1 categories need no
// migration. Each segment must have the same shape _slugify() (pipeline/
// main.py) produces: lowercase, hyphenated, no empty/slash-only segments.
// Deliberately doesn't know about RESERVED_CATEGORIES/"tag" reservation -
// those are a routing-collision concern (lib/pages.ts's directory walk,
// pipeline/main.py's create-page validation), not a generic shape rule.
const CATEGORY_SEGMENT = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export const MAX_CATEGORY_DEPTH = 4;

const categoryPathSchema = z.string().refine(
  (value) => {
    const segments = value.split("/");
    return segments.length <= MAX_CATEGORY_DEPTH && segments.every((s) => CATEGORY_SEGMENT.test(s));
  },
  { message: `category must be 1-${MAX_CATEGORY_DEPTH} lowercase, hyphenated "/"-joined segments` },
);

// raw_data is deliberately loosely typed: its shape depends on the scraper's
// content sniffing result (html_page/tabular_text/directory_listing/
// zip_archive, see pipeline/scraper.py extract_any()) and isn't part of the
// time window data model.
//
// source accepts either a single object (scraped pages, one origin) or an
// array (calendar-style categories - e.g. urlaubsfenster's school-holiday
// facts, which genuinely cite two sources for some Bundeslaender) and
// normalizes to an array either way, so every consumer deals with one shape.
//
// windows is the calendar-facts counterpart to raw_data: RawWindow entries
// (lib/schema.ts) that getPageEvents() (lib/pages.ts) resolves via
// materializeRawWindow() instead of the raw_data-based llm_events/
// found-dates fallback. A page populates EITHER windows (curated/computed
// calendar facts - Feiertage/Urlaubsfenster/Schulferien/Saisonkalender) OR
// raw_data (arbitrary scraped content), not both.
export const pageDataSchema = z
  .object({
    subject: z.object({ slug: z.string(), category: categoryPathSchema }),
    source: z
      .union([sourceSchema, z.array(sourceSchema).min(1)])
      .transform((v) => (Array.isArray(v) ? v : [v])),
    windows: z.array(rawWindowSchema).default([]),
    raw_data: z.record(z.string(), z.unknown()).default({}),
  })
  .superRefine((data, ctx) => {
    // Integrity check: a window's source_urls (if present) must reference
    // URLs that actually exist in this page's source[] - otherwise the
    // materialization fallback in lib/materialization.ts would silently
    // treat the reference as unresolvable and re-attach the whole list,
    // masking a typo'd or stale URL instead of failing the build on it.
    const knownUrls = new Set(data.source.map((s) => s.url));
    data.windows.forEach((w, i) => {
      for (const url of w.source_urls ?? []) {
        if (!knownUrls.has(url)) {
          ctx.addIssue({
            code: "custom",
            message: `windows[${i}].source_urls references a URL not present in source[]: ${url}`,
            path: ["windows", i, "source_urls"],
          });
        }
      }
    });
  });

// One per category folder (data/{category}/_category.yaml), written the
// first time a category is created (see pipeline/main.py POST /create-page)
// - lets an operator set a real display name ("Religiöse Feiertage") that's
// decoupled from the URL-safe folder slug ("religioese-feiertage"), instead
// of deriving one from the slug at display time.
export const categoryMetaSchema = z.object({
  name: z.string(),
  description: z.string().default(""),
});

export type PageMeta = z.infer<typeof pageMetaSchema>;
export type PageData = z.infer<typeof pageDataSchema>;
export type CategoryMeta = z.infer<typeof categoryMetaSchema>;

export function parsePageMeta(doc: unknown): PageMeta {
  return pageMetaSchema.parse(doc);
}

export function parsePageData(doc: unknown): PageData {
  return pageDataSchema.parse(doc);
}

export function parseCategoryMeta(doc: unknown): CategoryMeta {
  return categoryMetaSchema.parse(doc);
}
