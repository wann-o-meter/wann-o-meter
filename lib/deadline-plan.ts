// A deadline plan: deadlines relative to a date picked at runtime (the
// anchor day), not a concrete calendar date - doesn't fit RawWindow/
// materialization (lib/schema.ts), which resolves to absolute years at
// build time. Domain-agnostic on purpose, Umzug is just the first consumer
// (lib/umzug-data.ts). Browser-safe on purpose too: DeadlinePlanner.vue (a
// client:load island) imports computeSchedule directly, so nothing here may
// import node:fs/path (that lives in each domain's own *-data.ts) - a
// module's whole import graph loads with it, so even one fs import here
// would break client hydration.
import { z } from "zod";
import { loadHolidays, rollToLandingDay } from "./business-days";
import { FACET_IDS } from "./facets";
import { toDate } from "./format-date";
import { holidaysFor } from "./holidays";
import type { Holiday } from "./holidays";
import { bgb573cNoticeDeadline } from "./notice-period";
import type { DerivationStep } from "./notice-period";

// source_url null is not "not yet filled in", it's the product's core promise
// ("jede Frist hat eine sichtbare Quelle") made checkable: a deadline with no
// source must render as unverified, never as a plausible-looking day count.
export const deadlineSchema = z.object({
  id: z.string(),
  label: z.string(),
  offset_days: z.number().int().nullable(), // the legal/actual deadline - a ballpark approximation when offset_rule is set, since sorting still needs a plain number
  offset_rule: z.enum(["bgb-573c-notice"]).optional(), // computes the real date instead of using offset_days directly - see lib/notice-period.ts
  needs_office: z.boolean().optional(), // true when the step depends on an Amt being open
  earliest_offset_days: z.number().int().optional(), // frühestens möglich - absent means "same as the deadline", not "unknown"
  lead_time_days: z.number().int().positive().optional(), // Vorlaufzeit (Termin etc.) - absent means "no known lead time"
  lead_time_source: z.string().optional(),
  source_url: z.url().nullable(),
  source_label: z.string().optional(),
  // Some tasks (e.g. Sperrmüllabholung) aren't governed by any Gesetz/Satzung
  // deadline at all - there's nothing to cite, ever. Distinct from
  // source_url: null, which means "real source exists, not yet researched".
  no_source_needed: z.boolean().optional(),
  // Only relevant under one of these circumstances (see lib/facets.ts).
  // Absent means "applies to everyone" - the default.
  applies_if: z.array(z.enum(FACET_IDS)).optional(),
  note: z.string().optional(),
});

export type Deadline = z.infer<typeof deadlineSchema>;

export interface ScheduleEntry extends Deadline {
  date: string | null; // ISO YYYY-MM-DD, null when offset_days is unknown - the legal deadline
  earliestDate: string | null; // date, unless earliest_offset_days moves it earlier
  startByDate: string | null; // date minus lead_time_days - the day you actually have to act
  impossible: boolean; // startByDate before earliestDate: the lead time alone doesn't fit before the deadline is even reachable
  weekend: boolean;
  collision: string | null; // holiday name the date falls on, if any
  movedFrom?: string; // the closed day a needs_office step was rolled off (§ 193 BGB)
  // Only set for offset_rule-based entries (currently just bgb-573c-notice) -
  // a plain offset deadline has nothing hidden to explain, so this stays
  // undefined rather than a meaningless value.
  derivation?: DerivationStep[];
  pastDeadline?: boolean;
  rescue?: { date: string; label: string } | null;
}

function addDays(iso: string, days: number): string {
  const d = toDate(iso);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/**
 * Resolves each deadline to a concrete date given the anchor day, and flags
 * weekends/public holidays it lands on. Unknown offsets (not yet researched)
 * stay null and sort last. countryCode/regionCode select which holidays count
 * as a collision (see lib/holidays.ts). `today` defaults to the real current
 * date - only offset_rule entries that need to check "has this already
 * passed" (currently bgb-573c-notice) actually read it. Pass it explicitly
 * in tests to keep them deterministic.
 *
 * Also resolves earliestDate/startByDate/impossible - a deadline is not just
 * a point, most are a window (earliest possible day .. legal deadline), and
 * anything needing an appointment has a real "start by" day well before the
 * deadline itself once lead time is subtracted. Both default to `date` when
 * the corresponding *_days field is unresearched, so an entry with neither
 * field behaves exactly like a plain point deadline.
 *
 * A needs_office step never keeps a day the office is shut on: offsets in the
 * data are round weeks, so a Sunday anchor would otherwise put every single
 * one of them on a Sunday. It rolls forward to the next Werktag, which is
 * also what § 193 BGB does with a deadline landing on a Saturday, Sunday or
 * public holiday. The day it moved off stays in `movedFrom`.
 */
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
  deferMonths = 0, // push an offset_rule's target period back by n months
): ScheduleEntry[] {
  const resolved = deadlines.map((d) => {
    let derivation: DerivationStep[] | undefined;
    let pastDeadline: boolean | undefined;
    let rescue: { date: string; label: string } | null | undefined;
    let date: string | null;
    if (d.offset_days === null) {
      date = null;
    } else if (d.offset_rule === "bgb-573c-notice") {
      // The rule's target period is the anchor month, unless the caller
      // deliberately pushes it back (see deferMonths).
      const targetEndMonth = shiftMonth(anchorDate.slice(0, 7), deferMonths);
      const result = bgb573cNoticeDeadline(
        targetEndMonth,
        countryCode,
        regionCode,
        today,
        deferMonths,
      );
      date = result.date; // always 1:1 with anchorDate, even when past - see notice-period.ts
      derivation = result.derivation;
      pastDeadline = result.pastDeadline;
      // Projected down on purpose: the scheduler carries a date and a
      // sentence, never the rule's own domain fields.
      rescue = result.rescue
        ? { date: result.rescue.date, label: result.rescue.label }
        : null;
    } else {
      date = addDays(anchorDate, d.offset_days);
    }
    // A step on the anchor day itself happens at the move, closed office or
    // not, so only the movable ones roll.
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
      // By the day the entry actually lands on, not by the offset that only
      // approximates it: an offset_rule computes its own date. Never by the
      // rescue date - an expired deadline belongs where it was missed, at the
      // start of the plan, not after everything still to come. Unresearched
      // entries sort last.
      .sort((a, b) => {
        const ka = a.date;
        const kb = b.date;
        if (ka === null) return kb === null ? 0 : 1;
        if (kb === null) return -1;
        return ka < kb ? -1 : ka > kb ? 1 : 0;
      })
  );
}
