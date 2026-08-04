// Umzug deadlines are relative to a date the user picks at runtime (the move
// day), not a concrete calendar date - they don't fit RawWindow/materialization
// (lib/schema.ts, lib/materialization.ts), which resolve to absolute years at
// build time. So this is its own small model: an offset in days from the move
// day, resolved to a concrete date only once a user supplies one.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { toDate } from "./format-date";
import { holidaysFor } from "./holidays";
import type { Holiday } from "./holidays";

const DATA_ROOT = join(process.cwd(), "data", "umzug");
const BUNDESWEIT_FILE = "_bundesweit.yaml";

// source_url null is not "not yet filled in", it's the product's core promise
// ("jede Frist hat eine sichtbare Quelle") made checkable: a deadline with no
// source must render as unverified, never as a plausible-looking day count.
export const umzugDeadlineSchema = z.object({
  id: z.string(),
  label: z.string(),
  offset_days: z.number().int().nullable(),
  source_url: z.url().nullable(),
  source_label: z.string().optional(),
  note: z.string().optional(),
});

const deadlineListSchema = z.object({
  deadlines: z.array(umzugDeadlineSchema).default([]),
});

const kommuneFileSchema = deadlineListSchema.extend({
  name: z.string(),
  state: z.string(),
});

export type UmzugDeadline = z.infer<typeof umzugDeadlineSchema>;

export interface UmzugKommune {
  slug: string;
  name: string;
  state: string;
}

export interface UmzugScheduleEntry extends UmzugDeadline {
  date: string | null; // ISO YYYY-MM-DD, null when offset_days is unknown
  weekend: boolean;
  collision: string | null; // holiday name the date falls on, if any
}

function readYaml(path: string): unknown {
  return load(readFileSync(path, "utf-8"));
}

export function listUmzugKommunen(): UmzugKommune[] {
  return readdirSync(DATA_ROOT, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".yaml") && e.name !== BUNDESWEIT_FILE)
    .map((e) => {
      const slug = e.name.replace(/\.yaml$/, "");
      const doc = kommuneFileSchema.parse(readYaml(join(DATA_ROOT, e.name)));
      return { slug, name: doc.name, state: doc.state };
    })
    .sort((a, b) => a.name.localeCompare(b.name, "de"));
}

// Bundesweit deadlines apply to every Kommune, local ones add to them - plain
// concat, no override-by-id merge.
// ponytail: concat only, override-by-id when a Kommune actually contradicts a
// federal step.
export function loadUmzugKommune(slug: string): { name: string; state: string; deadlines: UmzugDeadline[] } | null {
  let kommuneDoc: z.infer<typeof kommuneFileSchema>;
  try {
    kommuneDoc = kommuneFileSchema.parse(readYaml(join(DATA_ROOT, `${slug}.yaml`)));
  } catch {
    return null;
  }
  const bundesweit = deadlineListSchema.parse(readYaml(join(DATA_ROOT, BUNDESWEIT_FILE)));
  return {
    name: kommuneDoc.name,
    state: kommuneDoc.state,
    deadlines: [...bundesweit.deadlines, ...kommuneDoc.deadlines],
  };
}

function addDays(iso: string, days: number): string {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * Resolves each deadline to a concrete date given the move day, and flags
 * weekends/public holidays it lands on. Unknown offsets (not yet researched)
 * stay null and sort last. countryCode/regionCode select which holidays count
 * as a collision (see lib/holidays.ts).
 */
export function computeUmzugSchedule(
  moveDate: string,
  deadlines: UmzugDeadline[],
  countryCode: string,
  regionCode?: string,
): UmzugScheduleEntry[] {
  const resolved = deadlines.map((d) => ({
    ...d,
    date: d.offset_days === null ? null : addDays(moveDate, d.offset_days),
  }));

  const years = new Set(resolved.flatMap((d) => (d.date ? [toDate(d.date).getUTCFullYear()] : [])));
  years.add(toDate(moveDate).getUTCFullYear());
  const holidays: Holiday[] = [...years].flatMap((y) => holidaysFor(y, countryCode, regionCode));
  const byDate = new Map(holidays.map((h) => [h.date, h.name]));

  return resolved
    .map((d) => {
      const weekend = d.date !== null && [0, 6].includes(toDate(d.date).getUTCDay());
      return { ...d, weekend, collision: d.date ? (byDate.get(d.date) ?? null) : null };
    })
    .sort((a, b) => {
      if (a.offset_days === null) return b.offset_days === null ? 0 : 1;
      if (b.offset_days === null) return -1;
      return a.offset_days - b.offset_days;
    });
}
