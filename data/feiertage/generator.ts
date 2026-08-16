import { allCountries } from "../../lib/countries";
import { formatDate } from "../../lib/format-date";
import { holidaySource, rollingYears } from "../../lib/materialization";
import { holidaysFromLibrary } from "../../lib/holidays-lib";
import { parsePageData, parsePageMeta } from "../../lib/pages-schema";
import { STATES } from "../../lib/states";
import type { Page } from "../../lib/pages";
import type { RawWindow } from "../../lib/schema";

function nextHolidayBlurb(windows: RawWindow[]): string {
  const today = new Date().toISOString().slice(0, 10);
  const next = windows.filter((w) => w.from >= today).sort((a, b) => a.from.localeCompare(b.from))[0];
  return next ? ` Nächster Feiertag: ${next.name} am ${formatDate(next.from)}.` : "";
}

function buildPage(
  slug: string,
  name: string,
  countryCode: string,
  regionCode: string | undefined,
  years: number[],
  featured?: boolean,
): Page {
  const windows: RawWindow[] = years.flatMap((year) =>
    holidaysFromLibrary(year, countryCode, regionCode).map((h) => ({
      type: "holiday",
      year,
      from: h.date,
      to: h.date,
      precision: "exact" as const,
      ics: true,
      name: h.name,
    })),
  );
  return {
    category: "feiertage",
    slug,
    meta: parsePageMeta({
      title: name,
      description: `Gesetzliche Feiertage für ${name}.${nextHolidayBlurb(windows)}`,
      intro: `Gesetzliche Feiertage für ${name}.`,
      featured,
    }),
    data: parsePageData({
      subject: { slug, category: "feiertage" },
      source: holidaySource(),
      windows,
    }),
  };
}

export function generate(): Page[] {
  const years = rollingYears();
  const de = Object.entries(STATES).map(([code, name]) => buildPage(`de-${code.toLowerCase()}`, `Deutschland – ${name}`, "DE", code, years, true));
  const others = Object.entries(allCountries())
    .filter(([code]) => code !== "DE")
    .map(([code, name]) => buildPage(code.toLowerCase(), name, code, undefined, years, false));
  return [...de, ...others];
}
