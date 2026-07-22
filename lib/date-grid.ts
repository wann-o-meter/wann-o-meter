// Calendar grid geometry (weeks-of-a-month, day matching), shared between
// Kalender.vue's year/month views and MonthGrid.vue - split out of
// date-display.ts because that file's job is name/label formatting shared
// with Layout.astro (a non-calendar consumer that has no reason to see grid
// geometry).
import { isoWeekNumber } from "./date-display";

export function isoFromDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function mondayOf(d: Date): Date {
  const copy = new Date(d);
  const weekday = (copy.getDay() + 6) % 7; // Mon=0
  copy.setDate(copy.getDate() - weekday);
  return copy;
}

export function daysInMonth(year: number, monthIndex0: number): number {
  return new Date(year, monthIndex0 + 1, 0).getDate();
}

export function isoDate(year: number, monthIndex0: number, day: number): string {
  return `${year}-${String(monthIndex0 + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export interface WeekRow {
  mondayIso: string;
  number: number;
  days: string[];
}

// Full Monday-Sunday weeks covering a month (including the leading/trailing
// days of adjacent months a week straddles) - shared by month view (its own
// month) and the year view (every month's mini-grid, so week numbers show
// up there too instead of just in month view).
export function weeksOfMonth(year: number, monthIndex0: number): WeekRow[] {
  const lastDay = new Date(year, monthIndex0 + 1, 0);
  let monday = mondayOf(new Date(year, monthIndex0, 1));
  const weeks: WeekRow[] = [];
  while (monday <= lastDay) {
    const days = Array.from({ length: 7 }, (_, i) => {
      const day = new Date(monday);
      day.setDate(day.getDate() + i);
      return isoFromDate(day);
    });
    weeks.push({ mondayIso: isoFromDate(monday), number: isoWeekNumber(monday), days });
    monday = new Date(monday);
    monday.setDate(monday.getDate() + 7);
  }
  return weeks;
}

export interface DayWindow {
  start: string;
  end: string;
  description: string;
}

export interface DayLayer {
  color: string;
  label: string;
  url: string;
  visible: boolean;
  windows: DayWindow[];
}

export interface Match {
  color: string;
  title: string;
  url: string;
}

export function matchesForDay(iso: string, layers: DayLayer[]): Match[] {
  const matches: Match[] = [];
  for (const layer of layers) {
    if (!layer.visible) continue;
    for (const w of layer.windows) {
      if (w.start <= iso && iso <= w.end) {
        // Fragment points at the matching row on the target page (see the
        // :target highlight in the detail pages).
        matches.push({ color: layer.color, title: `${layer.label}: ${w.description}`, url: `${layer.url}#${w.start}` });
      }
    }
  }
  return matches;
}
