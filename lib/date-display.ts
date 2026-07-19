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

// ISO-8601 week number (Thursday rule).
export function isoWeekNumber(d: Date): number {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const weekday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - weekday + 3);
  const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
  const diffDays = Math.round((date.getTime() - firstThursday.getTime()) / 86400000);
  return 1 + Math.round(diffDays / 7);
}

export function formatTodayLabel(d: Date = new Date()): string {
  return `Heute: ${WEEKDAY_NAMES_LONG[(d.getDay() + 6) % 7]}, ${d.getDate()}. ${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()} · KW ${isoWeekNumber(d)}`;
}
