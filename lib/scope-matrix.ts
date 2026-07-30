// Turns the 16 German Feiertage pages into a holiday x Bundesland matrix, the
// data shape src/components/ScopeMatrix.astro renders. Generalized over any
// state-coded Page[] (not hardcoded to "feiertage") so a future range-type
// category with the same shape (rows differing only by scope) can reuse it -
// today /feiertage/ is the only caller.
import { getPageEvents } from "./pages";
import type { Page } from "./pages";
import { eventsInYear, yearSubjectCode } from "./year-pages";
import { STATE_ABBREVIATIONS, STATES } from "./states";

export interface ScopeMatrixScope {
  code: string; // e.g. "BW"
  label: string; // short column header, e.g. "BW" or "NRW"
  name: string; // full name, for a title/abbr attribute
  href: string;
  layerId: string;
}

export interface ScopeMatrixRow {
  title: string;
  dateByScope: Record<string, string | null>; // keyed by ScopeMatrixScope.code
}

export interface ScopeMatrix {
  scopes: ScopeMatrixScope[];
  rows: ScopeMatrixRow[];
}

function toScope(page: Page): ScopeMatrixScope | null {
  const code = yearSubjectCode(page.category, page.slug);
  if (!code) return null;
  return {
    code,
    label: STATE_ABBREVIATIONS[code] ?? code,
    name: STATES[code],
    href: `/${page.category}/${page.slug}/`,
    layerId: `${page.category.replace(/\//g, "-")}--${page.slug}`,
  };
}

export function buildScopeMatrix(statePages: Page[], year: number): ScopeMatrix {
  const scopes = statePages
    .map(toScope)
    .filter((s): s is ScopeMatrixScope => s !== null)
    .sort((a, b) => a.name.localeCompare(b.name, "de"));

  const dateByTitle = new Map<string, Record<string, string | null>>();
  for (const page of statePages) {
    const scope = toScope(page);
    if (!scope) continue;
    for (const e of eventsInYear(getPageEvents(page), year)) {
      const dateByScope = dateByTitle.get(e.label) ?? {};
      dateByScope[scope.code] = e.date;
      dateByTitle.set(e.label, dateByScope);
    }
  }

  const earliestDate = (dateByScope: Record<string, string | null>): string =>
    Object.values(dateByScope)
      .filter((d): d is string => d !== null)
      .sort()[0];

  const rows = [...dateByTitle.entries()]
    .map(([title, dateByScope]) => ({ title, dateByScope }))
    .sort((a, b) => earliestDate(a.dateByScope).localeCompare(earliestDate(b.dateByScope)) || a.title.localeCompare(b.title, "de"));

  return { scopes, rows };
}
