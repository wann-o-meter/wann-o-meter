import { z } from "zod";
import { loadHolidays, rollToLandingDay } from "./business-days";
import { FACET_IDS } from "./facets";
import { toDate } from "./format-date";
import { holidaysFor } from "./holidays";
import type { Holiday } from "./holidays";
import { bgb573cNoticeDeadline } from "./notice-period";
import type { DerivationStep } from "./notice-period";

// What a task is, before anything computes a date for it.
//   statutory-absolute  the statute names the day, no user input
//   statutory-relative  the statute names an offset from a date the user gives
//   soft                no legal anchor, so no defensible date either
export const TASK_KINDS = [
  "statutory-absolute",
  "statutory-relative",
  "soft",
] as const;

export const deadlineSchema = z
  .object({
    id: z.string(),
    kind: z.enum(TASK_KINDS),
    // before: the deadline precedes the anchor. after: the clock starts at it.
    direction: z.enum(["before", "after"]).optional(),
    // The Vorhaben this task appears in. Filled in by the loader from the
    // directory, one entry until a second Vorhaben genuinely reuses a task.
    belongsTo: z.array(z.string()).default([]),
    label: z.string(),
    offset_days: z.number().int().nullable(),
    offset_rule: z.enum(["bgb-573c-notice"]).optional(),
    needs_office: z.boolean().optional(),
    earliest_offset_days: z.number().int().optional(),
    lead_time_days: z.number().int().positive().optional(),
    lead_time_source: z.string().optional(),
    source_url: z.url().nullable(),
    source_label: z.string().optional(),
    no_source_needed: z.boolean().optional(),
    applies_if: z.array(z.enum(FACET_IDS)).optional(),
    note: z.string().optional(),
  })
  .refine((d) => (d.kind === "soft") === (d.direction === undefined), {
    message: "statutory tasks need a direction, soft tasks must not have one",
    path: ["direction"],
  });

export type Deadline = z.infer<typeof deadlineSchema>;

export interface ScheduleEntry extends Deadline {
  date: string | null;
  earliestDate: string | null;
  startByDate: string | null;
  impossible: boolean;
  weekend: boolean;
  collision: string | null;
  movedFrom?: string;
  derivation?: DerivationStep[];
  pastDeadline?: boolean;
  rescue?: { date: string; label: string } | null;
  leaseEnd?: { date: string; overlapDays: number };
}

function addDays(iso: string, days: number): string {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function endOfMonth(yyyyMm: string): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);
}

function shiftMonth(yyyyMm: string, n: number): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  const total = m - 1 + n;
  const year = y + Math.floor(total / 12);
  const month = (((total % 12) + 12) % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

export function computeSchedule(
  anchorDate: string,
  deadlines: Deadline[],
  countryCode: string,
  regionCode?: string,
  today: string = new Date().toISOString().slice(0, 10),
  deferMonths = 0,
): ScheduleEntry[] {
  const resolved = deadlines.map((d) => {
    let derivation: DerivationStep[] | undefined;
    let pastDeadline: boolean | undefined;
    let rescue: { date: string; label: string } | null | undefined;
    let leaseEnd: { date: string; overlapDays: number } | undefined;
    let date: string | null;
    if (d.offset_days === null) {
      date = null;
    } else if (d.offset_rule === "bgb-573c-notice") {
      const targetEndMonth = shiftMonth(anchorDate.slice(0, 7), deferMonths);
      const result = bgb573cNoticeDeadline(
        targetEndMonth,
        countryCode,
        regionCode,
        today,
        deferMonths,
      );
      date = result.date;
      derivation = result.derivation;
      pastDeadline = result.pastDeadline;
      rescue = result.rescue
        ? { date: result.rescue.date, label: result.rescue.label }
        : null;
      const lastDay = endOfMonth(
        result.rescue?.leaseEndMonth ?? result.leaseEndMonth,
      );
      leaseEnd = {
        date: lastDay,
        overlapDays: Math.round(
          (toDate(lastDay).getTime() - toDate(anchorDate).getTime()) / 86400000,
        ),
      };
    } else {
      date = addDays(anchorDate, d.offset_days);
    }
    let movedFrom: string | undefined;
    if (date !== null && d.needs_office && d.offset_days !== 0) {
      const set = loadHolidays(
        toDate(date).getUTCFullYear(),
        countryCode,
        regionCode,
      );
      const landed = rollToLandingDay(toDate(date), set)
        .toISOString()
        .slice(0, 10);
      if (landed !== date) {
        movedFrom = date;
        date = landed;
      }
    }
    const earliestDate =
      date === null
        ? null
        : d.earliest_offset_days !== undefined
          ? addDays(anchorDate, d.earliest_offset_days)
          : date;
    const startByDate =
      date === null
        ? null
        : d.lead_time_days
          ? addDays(date, -d.lead_time_days)
          : date;
    return {
      ...d,
      date,
      earliestDate,
      startByDate,
      derivation,
      pastDeadline,
      rescue,
      leaseEnd,
      movedFrom,
    };
  });

  const years = new Set(
    resolved.flatMap((d) => (d.date ? [toDate(d.date).getUTCFullYear()] : [])),
  );
  years.add(toDate(anchorDate).getUTCFullYear());
  const holidays: Holiday[] = [...years].flatMap((y) =>
    holidaysFor(y, countryCode, regionCode),
  );
  const byDate = new Map(holidays.map((h) => [h.date, h.name]));

  return (
    resolved
      .map((d) => {
        const weekend =
          d.date !== null && [0, 6].includes(toDate(d.date).getUTCDay());
        const impossible =
          d.startByDate !== null &&
          d.earliestDate !== null &&
          d.startByDate < d.earliestDate;
        return {
          ...d,
          weekend,
          impossible,
          collision: d.date ? (byDate.get(d.date) ?? null) : null,
        };
      })
      .sort((a, b) => {
        const ka = a.date;
        const kb = b.date;
        if (ka === null) return kb === null ? 0 : 1;
        if (kb === null) return -1;
        return ka < kb ? -1 : ka > kb ? 1 : 0;
      })
  );
}
