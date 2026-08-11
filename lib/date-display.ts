// German month/weekday names and ISO week calculation, shared between the
// calendar (Kalender.vue) and the site-wide "today" indicator (Layout.astro)
// - both need the exact same "what week is it" logic, kept in one place.

export const MONTH_NAMES = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

export const WEEKDAY_NAMES_LONG = [
  "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag",
];

export const WEEKDAY_NAMES_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

// Two date forms for the whole planner, so no view invents a third. Short is
// numeric and fits a dense row, long spells the month out and is reserved for
// the one date the plan hangs on. Both read the ISO day in UTC, the same way
// lib/format-date.ts does, and neither depends on the runtime's locale data.
function utcParts(iso: string) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return {
    weekday: WEEKDAY_NAMES_SHORT[(d.getUTCDay() + 6) % 7],
    day: d.getUTCDate(),
    month0: d.getUTCMonth(),
    year: d.getUTCFullYear(),
  };
}

/** "Di, 04.08.2026" */
export function shortDate(iso: string): string {
  const p = utcParts(iso);
  const day = String(p.day).padStart(2, "0");
  const month = String(p.month0 + 1).padStart(2, "0");
  return `${p.weekday}, ${day}.${month}.${p.year}`;
}

/** "Fr, 16. Oktober 2026" */
export function longDate(iso: string): string {
  const p = utcParts(iso);
  return `${p.weekday}, ${p.day}. ${MONTH_NAMES[p.month0]} ${p.year}`;
}

// ISO-8601 week number (Thursday rule).
export function isoWeekNumber(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const weekday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - weekday + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const diffDays = Math.round((date.getTime() - firstThursday.getTime()) / 86400000);
  return 1 + Math.round(diffDays / 7);
}

// "Sa., 26.07." - no "Heute:" prefix, no year, no month name: it sits in the
// header next to the calendar and search links, where a full sentence was the
// widest thing in the bar and told the reader what the date already implies.
export function formatTodayLabel(d: Date = new Date()): string {
  const day = String(d.getDate()).padStart(2, "0");
  const month = String(d.getMonth() + 1).padStart(2, "0");
  return `${WEEKDAY_NAMES_SHORT[(d.getDay() + 6) % 7]}., ${day}.${month}.`;
}
