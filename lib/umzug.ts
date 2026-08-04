// Umzug deadlines are relative to a date the user picks at runtime (the move
// day), not a concrete calendar date - they don't fit RawWindow/materialization
// (lib/schema.ts, lib/materialization.ts), which resolve to absolute years at
// build time. So this is its own small model: an offset in days from the move
// day, resolved to a concrete date only once a user supplies one.
//
// Browser-safe on purpose: UmzugPlaner.vue (a client:load island) imports
// computeUmzugSchedule directly, so nothing here may import node:fs/path -
// that lives in lib/umzug-data.ts instead, imported only from Astro
// frontmatter. Importing anything from a module pulls in its whole top-level
// import graph, so even a single fs import here would break client hydration.
import { z } from "zod";
import { toDate } from "./format-date";
import { holidaysFor } from "./holidays";
import type { Holiday } from "./holidays";

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

export type UmzugDeadline = z.infer<typeof umzugDeadlineSchema>;

export interface UmzugKommune {
  slug: string;
  name: string;
  state: string;
}

export interface UmzugKommuneData extends UmzugKommune {
  deadlines: UmzugDeadline[];
}

export interface UmzugScheduleEntry extends UmzugDeadline {
  date: string | null; // ISO YYYY-MM-DD, null when offset_days is unknown
  weekend: boolean;
  collision: string | null; // holiday name the date falls on, if any
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
