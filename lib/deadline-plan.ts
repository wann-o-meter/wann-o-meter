import { loadHolidays, rollToLandingDay } from "./business-days";
import { toDate, toIso } from "./format-date";
import { holidaysFor } from "./holidays";
import type { Holiday } from "./holidays";
import { nextOccurrence } from "./calendar-rule";
import { solve as wohnungKuendigen } from "../data/fristen/wohnung-kuendigen";
import type { DerivationStep, FristSolver } from "./derivation";
import type { Deadline } from "./deadline-schema";

// A Frist whose statute no yaml rule can express keeps its code next to its
// yaml, under the same name. The id is the only link, so adding one is adding a
// file and a line here.
const SOLVERS: Record<string, FristSolver> = {
  "wohnung-kuendigen": wohnungKuendigen,
};

export type { Deadline };

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
  return toIso(d);
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
    if (d.rule) {
      // The statute fixes the day. The anchor only says which occurrence of it
      // the visitor is looking at.
      const hit = nextOccurrence(d.rule, anchorDate, countryCode, regionCode);
      date = hit?.date ?? null;
      derivation = hit?.derivation;
    } else if (SOLVERS[d.id]) {
      const result = SOLVERS[d.id](anchorDate, countryCode, regionCode, today, deferMonths);
      date = result.date;
      derivation = result.derivation;
      pastDeadline = result.pastDeadline;
      rescue = result.rescue ?? null;
      leaseEnd = result.leaseEnd;
    } else if (d.offset_days === null) {
      date = null;
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
