import { holidaysFor } from "./holidays";

interface HolidaySet {
  region: string;
  dates: Set<string>;
}

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

function isCountingDay(date: Date, holidays: HolidaySet): boolean {
  return date.getUTCDay() !== 0 && !holidays.dates.has(iso(date));
}

function isLandingDay(date: Date, holidays: HolidaySet): boolean {
  const dow = date.getUTCDay();
  return dow !== 0 && dow !== 6 && !holidays.dates.has(iso(date));
}

export function rollToLandingDay(date: Date, holidays: HolidaySet): Date {
  const d = new Date(date);
  while (!isLandingDay(d, holidays)) d.setUTCDate(d.getUTCDate() + 1);
  return d;
}

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
