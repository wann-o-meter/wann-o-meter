// Server only: date-holidays carries the rules of every country on earth, far
// too much for a page bundle. The browser reads the generated German table in
// holidays.ts instead, and this module stays behind the build.
import Holidays from "date-holidays";
import type { Holiday } from "./holidays";

const cache = new Map<string, Holiday[]>();

export function holidaysFromLibrary(
  year: number,
  countryCode: string,
  regionCode?: string,
): Holiday[] {
  const key = `${countryCode}-${regionCode ?? ""}-${year}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const h = new Holidays(countryCode, regionCode ?? "", { types: ["public"] });
  const result = h
    .getHolidays(year)
    .filter((d) => d.type === "public")
    .map((d) => ({ date: d.date.slice(0, 10), name: d.name }));
  cache.set(key, result);
  return result;
}
