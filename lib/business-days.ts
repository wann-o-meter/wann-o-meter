// "Werktag" ("business day") in German civil-law deadline calculations has
// two distinct, non-interchangeable meanings, and conflating them is exactly
// how this kind of rule goes subtly wrong:
// - COUNTING day: which days count when counting "the Nth Werktag" of a
//   month. Saturday counts (BGH, Urt. v. 27.4.2005 - VIII ZR 206/04); Sunday
//   and public holidays don't.
// - LANDING day: which day a deadline may actually fall/end on. Saturday
//   does NOT count here (§ 193 BGB) - a deadline landing on a Saturday rolls
//   forward, exactly like landing on a Sunday or a holiday would.
import { holidaysFor } from "./holidays";

export interface HolidaySet {
  region: string; // human-readable, e.g. "DE-BW" - for deriv­ation text, not lookup
  dates: Set<string>;
}

// Spans year and year+1 so a landing day that rolls across a year boundary
// (rare, but possible right at Dec 31) still finds the right holiday set.
export function loadHolidays(year: number, countryCode: string, regionCode?: string): HolidaySet {
  const dates = new Set(
    [...holidaysFor(year, countryCode, regionCode), ...holidaysFor(year + 1, countryCode, regionCode)].map(
      (h) => h.date,
    ),
  );
  return { region: regionCode ? `${countryCode}-${regionCode}` : countryCode, dates };
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function isCountingDay(date: Date, holidays: HolidaySet): boolean {
  return date.getUTCDay() !== 0 && !holidays.dates.has(iso(date));
}

function isLandingDay(date: Date, holidays: HolidaySet): boolean {
  const dow = date.getUTCDay();
  return dow !== 0 && dow !== 6 && !holidays.dates.has(iso(date));
}

// § 193 BGB: rolls forward to the next valid landing day if `date` isn't one
// (lands on a Saturday, Sunday, or public holiday). A no-op if `date` is
// already a valid landing day.
export function rollToLandingDay(date: Date, holidays: HolidaySet): Date {
  const d = new Date(date);
  while (!isLandingDay(d, holidays)) d.setUTCDate(d.getUTCDate() + 1);
  return d;
}

/**
 * The Nth counting day of the given month (1-indexed `n`, 0-indexed
 * `month0`), landing day rolled forward per rollToLandingDay. `rolled` is
 * true only when that roll actually moved the date - i.e. the raw Nth
 * counting day itself was a Saturday. A holiday shifting *which* day is the
 * Nth counting day (by excluding an earlier candidate) is not a "roll", it's
 * already reflected in `raw`.
 */
export function nthCountingDayOfMonth(
  year: number,
  month0: number,
  n: number,
  holidays: HolidaySet,
): { date: Date; raw: Date; rolled: boolean } {
  let count = 0;
  const d = new Date(Date.UTC(year, month0, 1));
  while (true) {
    if (isCountingDay(d, holidays)) {
      count += 1;
      if (count === n) break;
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
  const raw = new Date(d);
  const date = rollToLandingDay(d, holidays);
  return { date, raw, rolled: date.getTime() !== raw.getTime() };
}
