import Holidays from "date-holidays";

export interface Holiday {
  date: string;
  name: string;
}

const cache = new Map<string, Holiday[]>();

export function holidaysFor(year: number, countryCode: string, regionCode?: string): Holiday[] {
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
