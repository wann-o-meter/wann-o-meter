// Turns a year plus a page's events into a 12-month x 31-day grid, the data
// shape src/components/YearGrid.astro renders. Kept separate from
// lib/date-grid.ts, which is week-shaped (Kalender.vue's month/week views) -
// this is month-rows/day-columns, a different geometry for a different job.
import { daysInMonth, isoDate } from "./date-grid";
import { MONTH_NAMES } from "./date-display";
import type { PageEvent } from "./pages";

export type DayCellState = "empty" | "weekend" | "event" | "plain";

export interface YearGridCell {
  day: number;
  iso: string;
  state: DayCellState;
  titles: string[];
}

export interface YearGridMonth {
  name: string;
  cells: YearGridCell[];
}

// Spec's own escape hatch: a sparser year makes a mostly-empty grid more
// misleading than the plain list it would sit above. Measured in covered
// DAYS, not entry count - a handful of multi-week Schulferien windows fills
// the grid just as much as a dozen single-day Feiertage, and counting
// entries would wrongly hide the grid on exactly the range-heavy pages the
// spec calls out as YearGrid's other primary case.
export const YEAR_GRID_MIN_DAYS = 8;

export function shouldRenderYearGrid(grid: YearGridMonth[]): boolean {
  const eventDays = grid.reduce((n, month) => n + month.cells.filter((c) => c.state === "event").length, 0);
  return eventDays >= YEAR_GRID_MIN_DAYS;
}

function isWeekend(iso: string): boolean {
  const day = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return day === 0 || day === 6;
}

export function buildYearGrid(year: number, events: PageEvent[]): YearGridMonth[] {
  const yearStart = `${year}-01-01`;
  const yearEnd = `${year}-12-31`;
  const titlesByIso = new Map<string, string[]>();
  for (const e of events) {
    // Clamp to the year: a window can cross a year boundary (e.g.
    // Weihnachtsferien 23.12.-06.01.) and lib/year-pages.ts's eventsInYear()
    // deliberately leaves the un-clamped range on both years' event lists.
    const from = e.date < yearStart ? yearStart : e.date;
    const to = (e.to ?? e.date) > yearEnd ? yearEnd : (e.to ?? e.date);
    const cursor = new Date(`${from}T00:00:00Z`);
    const end = new Date(`${to}T00:00:00Z`);
    while (cursor <= end) {
      const iso = cursor.toISOString().slice(0, 10);
      const list = titlesByIso.get(iso) ?? [];
      list.push(e.label);
      titlesByIso.set(iso, list);
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
  }

  return MONTH_NAMES.map((name, monthIndex0) => {
    const monthLength = daysInMonth(year, monthIndex0);
    const cells: YearGridCell[] = Array.from({ length: 31 }, (_, i) => {
      const day = i + 1;
      if (day > monthLength) return { day, iso: "", state: "empty" as const, titles: [] };
      const iso = isoDate(year, monthIndex0, day);
      const titles = titlesByIso.get(iso) ?? [];
      const state: DayCellState = titles.length > 0 ? "event" : isWeekend(iso) ? "weekend" : "plain";
      return { day, iso, state, titles };
    });
    return { name, cells };
  });
}
