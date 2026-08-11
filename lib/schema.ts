import { z } from "zod";
import { resolution } from "./date";

const licenseSchema = z.enum([
  "official_par5",
  "dl_de_by",
  "cc_by",
  "tos_checked",
  "permission_granted",
  "own_derivation",
]);

const extractionSchema = z.enum(["manual", "llm", "parser"]);

export const sourceSchema = z.object({
  url: z.url(),
  license: licenseSchema,
  license_note: z.string().nullable().optional(),
  retrieved_at: z.iso.date(),
  extraction: extractionSchema,
  confidence: z.number().min(0).max(1).optional(),
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

const precisionSchema = z.enum(["exact", "approximate"]);

function withValueUnitCheck<T extends z.ZodType<{ value?: number; unit?: string }>>(schema: T) {
  return schema.refine((f) => (f.value === undefined) === (f.unit === undefined), {
    message: "value and unit must be set together or both omitted",
    path: ["unit"],
  });
}

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
    last_verified: z.iso.date().optional(),
    rrule: z.string().optional(),
    notes: z.string().optional(),
  }),
);

export type Source = z.infer<typeof sourceSchema>;
export type RawWindow = z.infer<typeof rawWindowSchema>;

const materializedWindowSchema = withValueUnitCheck(
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

