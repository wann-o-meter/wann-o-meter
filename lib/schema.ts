// Zod schema for the data model (PLAN.md section 5). One source for types
// AND runtime validation - no separate JSON schema.
import { z } from "zod";
import { resolution } from "./date";

export const licenseSchema = z.enum([
  "official_par5",
  "dl_de_by",
  "cc_by",
  "tos_checked",
  "permission_granted",
  "own_derivation",
]);

// manual: a human typed/curated it. llm: a model extracted it from free text/PDF
// (use the confidence field, PR review is the quality layer). parser:
// deterministic code read it from structured data (CSV, JSON API, directory
// listing, ...) or computed it (holiday formula) - no model needed at
// runtime. Sourcing strategy: homogeneity x volume decides, see PLAN.md
// section 7.
export const extractionSchema = z.enum(["manual", "llm", "parser"]);

export const sourceSchema = z.object({
  url: z.url(),
  license: licenseSchema,
  license_note: z.string().nullable().optional(),
  retrieved_at: z.iso.date(),
  extraction: extractionSchema,
  confidence: z.number().min(0).max(1).optional(),
  // GitHub handle of whoever suggested this URL (see data/community-sources.txt's
  // "@handle url" format and pipeline/main.py's create-page contributed_by
  // field) - optional, most sources have none. Rendered by SourceList.astro.
  contributed_by: z.string().optional(),
});

const datePartSchema = z.string().refine(
  (s) => {
    try {
      resolution(s);
      return true;
    } catch {
      return false;
    }
  },
  { message: 'Invalid ISO 8601 partial date format (expected "--MM", "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM")' },
);

export const precisionSchema = z.enum(["exact", "approximate"]);

// Second axis alongside plain presence (from/to): a numeric reading per
// window (temperature, traffic, waiting time, ...). Optional and only valid
// together - a value without a unit is meaningless.
function withValueUnitCheck<T extends z.ZodType<{ value?: number; unit?: string }>>(schema: T) {
  return schema.refine((f) => (f.value === undefined) === (f.unit === undefined), {
    message: "value and unit must be set together or both omitted",
    path: ["unit"],
  });
}

// Definition layer: one row in the YAML source file (PLAN.md 5.3).
//
// source_urls links a window back to the specific entries in the file's
// `sources[]` that reported it (matched by Source.url) - without this, every
// window in a file was materialized with the file's ENTIRE source list
// attached, whether or not that source actually said anything about that
// date (see the two-source urlaubsfenster/*.yaml files, where one source
// covers only one of the two years present in the file).
//
// Optional rather than required: existing committed data/**/*.yaml files
// predate this field entirely (verified against the repo's data/ directory),
// and there's no reliable way to infer after the fact which of a file's
// (possibly several) sources produced a given legacy window - guessing would
// risk misattribution, which is worse than the status quo. Absent
// source_urls falls back to today's behavior (attach the file's full source
// list) at materialization time - see materializeRawWindow in
// lib/materialization.ts. New/re-run pipeline windows populate it going
// forward (pipeline/core/types.py stamps it from the adapter's Quelle).
export const rawWindowSchema = withValueUnitCheck(
  z.object({
    type: z.string(),
    year: z.number().int().nullable(),
    from: datePartSchema,
    to: datePartSchema,
    precision: precisionSchema,
    ics: z.boolean(),
    name: z.string().optional(),
    value: z.number().optional(),
    unit: z.string().optional(),
    source_urls: z.array(z.url()).min(1).optional(),
  }),
);

export type License = z.infer<typeof licenseSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type RawWindow = z.infer<typeof rawWindowSchema>;

// Materialized layer: what pages/JSON/ICS actually consume (PLAN.md 5.1) -
// concrete years, resolved day-level dates, source per window.
export const materializedWindowSchema = withValueUnitCheck(
  z.object({
    subject_id: z.string(),
    year: z.number().int(),
    from: z.iso.date(),
    to: z.iso.date(),
    type: z.string(),
    precision: precisionSchema,
    ics: z.boolean(),
    quality: z.string().optional(),
    description: z.string(),
    source: z.array(sourceSchema).min(1),
    metadata: z.record(z.string(), z.unknown()).optional(),
    value: z.number().optional(),
    unit: z.string().optional(),
  }),
);

export type MaterializedWindow = z.infer<typeof materializedWindowSchema>;

// Presets (PLAN.md 5.3 / 4.3): saved calendar URLs, curated as YAML, turned
// into static landing pages + pre-filled calendar parameters.
export const presetSchema = z.object({
  slug: z.string(),
  name: z.string(),
  description: z.string(),
  layers: z.array(z.enum(["holiday", "school_holidays", "produce"])).min(1),
  region: z.string(),
  mode: z.literal("overlay"), // window mode is explicitly not V1 (PLAN.md 4.2)
});

export type Preset = z.infer<typeof presetSchema>;

export function parsePreset(doc: unknown): Preset {
  return presetSchema.parse(doc);
}

// Homepage H1 rotator (src/pages/index.astro): one sentence template per
// category, containing a literal "{subject}" placeholder that
// lib/homepage-questions.ts fills in with a real subject from that
// category's data (a produce name, a Bundesland, ...) - decreed wording,
// same "curated as YAML" treatment as presets above.
export const homepageQuestionTemplatesSchema = z.object({
  templates: z.record(z.string(), z.string().min(1).refine((s) => s.includes("{subject}"), "template must contain a {subject} placeholder")),
});

export type HomepageQuestionTemplates = z.infer<typeof homepageQuestionTemplatesSchema>["templates"];

export function parseHomepageQuestionTemplates(doc: unknown): HomepageQuestionTemplates {
  return homepageQuestionTemplatesSchema.parse(doc).templates;
}
