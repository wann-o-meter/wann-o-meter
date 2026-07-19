// Feiertage has no facts on disk at all - 200+ country/German-state subjects,
// entirely computed via date-holidays (lib/holidays.ts). Registered in
// lib/pages.ts's GENERATORS map instead of a data.yaml/page.yaml pair per
// subject, since there's nothing to author.
import { allCountries } from "../../lib/countries";
import { formatDate } from "../../lib/format-date";
import { holidaySource, rollingYears } from "../../lib/materialization";
import { holidaysFor } from "../../lib/holidays";
import { parsePageData, parsePageMeta } from "../../lib/pages-schema";
import { STATES } from "../../lib/states";
import type { Page } from "../../lib/pages";
import type { RawWindow } from "../../lib/schema";

// Names the next upcoming holiday instead of just repeating "{name}" back -
// otherwise all 200+ generated meta descriptions differ only by region name,
// with no reason of their own to click through. Build-time "now" is fine
// here (static generation, same tradeoff as lib/date-display.ts's client-side
// "today" label): a description that's a build cycle stale is still far more
// specific than a purely mechanical one.
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
    holidaysFor(year, countryCode, regionCode).map((h) => ({
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
  // "every country": DE is already covered above per state, here's the rest
  // nationally (without subdivision - >200 countries x states wouldn't be a
  // sensible scope).
  const others = Object.entries(allCountries())
    .filter(([code]) => code !== "DE")
    .map(([code, name]) => buildPage(code.toLowerCase(), name, code, undefined, years, false));
  return [...de, ...others];
}
