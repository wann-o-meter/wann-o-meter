import Holidays from "date-holidays";

export interface Holiday {
  date: string; // ISO date YYYY-MM-DD
  name: string;
}

const cache = new Map<string, Holiday[]>();

// Statutory holidays per country (optionally state/subdivision), derived from
// each place's holiday laws via the date-holidays library instead of a
// custom Easter-formula implementation - ladder rung 4, no reason to write
// that ourselves. date-holidays covers >200 countries, see lib/countries.ts
// for the list.
export function holidaysFor(year: number, countryCode: string, regionCode?: string): Holiday[] {
  const key = `${countryCode}-${regionCode ?? ""}-${year}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const h = new Holidays(countryCode, regionCode, { types: ["public"] });
  const result = h
    .getHolidays(year)
    .filter((d) => d.type === "public")
    .map((d) => ({ date: d.date.slice(0, 10), name: d.name }));
  cache.set(key, result);
  return result;
}
