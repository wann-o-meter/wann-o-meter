// Urlaubsfenster is a pure computed layer, same shape as Feiertage: no
// facts on disk (school holidays live in their own data/schulferien/
// category now), just bridge-day windows computed per German state from
// date-holidays. Registered in lib/pages.ts's GENERATORS map.
import { formatDate } from "../../lib/format-date";
import { holidaysFor } from "../../lib/holidays";
import { holidaySource, rollingYears } from "../../lib/materialization";
import { parsePageData, parsePageMeta } from "../../lib/pages-schema";
import { STATES } from "../../lib/states";
import { calculateOptimalWindows } from "../../lib/vacation-windows";
import type { Page } from "../../lib/pages";
import type { RawWindow } from "../../lib/schema";

export function generate(): Page[] {
  const years = rollingYears();
  return Object.entries(STATES).map(([code, name]) => {
    const slug = code.toLowerCase();
    const windows: RawWindow[] = years.flatMap((year) =>
      calculateOptimalWindows(year, holidaysFor(year, "DE", code)).map((w) => ({
        type: "optimal",
        year,
        from: w.from,
        to: w.to,
        precision: "exact" as const,
        ics: true,
        name: `Mit ${w.requiredVacationDays} Urlaubstag${w.requiredVacationDays === 1 ? "" : "en"} vom ${formatDate(w.from)} bis ${formatDate(w.to)} frei (${w.totalDaysOff} Tage am Stück).`,
      })),
    );
    return {
      category: "urlaubsfenster",
      slug,
      meta: parsePageMeta({
        title: `Brückentage ${name}`,
        description: `Brückentage & optimale Urlaubsfenster für ${name}: mit wenigen Urlaubstagen lange frei, als Kalender abonnierbar.`,
      }),
      data: parsePageData({
        subject: { slug, category: "urlaubsfenster" },
        source: holidaySource(),
        windows,
      }),
    };
  });
}
