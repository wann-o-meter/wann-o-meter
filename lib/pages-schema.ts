import { z } from "zod";
import { rawWindowSchema, sourceSchema } from "./schema";

const pageMetaSchema = z.object({
  title: z.string(),
  description: z.string().default(""),
  intro: z.string().default(""),
  tags: z.array(z.string()).default([]),
  featured: z.boolean().default(true),
});

const CATEGORY_SEGMENT = /^[a-z0-9]+(-[a-z0-9]+)*$/;
export const MAX_CATEGORY_DEPTH = 4;

const categoryPathSchema = z.string().refine(
  (value) => {
    const segments = value.split("/");
    return segments.length <= MAX_CATEGORY_DEPTH && segments.every((s) => CATEGORY_SEGMENT.test(s));
  },
  { message: `category must be 1-${MAX_CATEGORY_DEPTH} lowercase, hyphenated "/"-joined segments` },
);

const pageDataSchema = z
  .object({
    subject: z.object({ slug: z.string(), category: categoryPathSchema }),
    source: z
      .union([sourceSchema, z.array(sourceSchema).min(1)])
      .transform((v) => (Array.isArray(v) ? v : [v])),
    windows: z.array(rawWindowSchema).default([]),
    raw_data: z.record(z.string(), z.unknown()).default({}),
  })
  .superRefine((data, ctx) => {
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

const categoryMetaSchema = z.object({
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
