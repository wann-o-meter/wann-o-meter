import { HOLIDAYS_DE } from "./holidays-de-data";

export interface Holiday {
  date: string;
  name: string;
}

// Only Germany, and only from the generated table: the library those entries
// come from is 260 KiB of rules for every country and has no business in a
// page bundle. Server code that needs another country uses holidays-lib.ts.
export function holidaysFor(
  year: number,
  countryCode: string,
  regionCode?: string,
): Holiday[] {
  if (countryCode !== "DE") return [];
  const table = HOLIDAYS_DE[regionCode || "DE"] ?? HOLIDAYS_DE.DE;
  return (table[String(year)] ?? []).map(([date, name]) => ({ date, name }));
}
