export const MONTH_NAMES = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

const WEEKDAY_NAMES_LONG = [
  "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag",
];

const WEEKDAY_NAMES_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

function utcParts(iso: string) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return {
    weekday: WEEKDAY_NAMES_SHORT[(d.getUTCDay() + 6) % 7],
    weekdayLong: WEEKDAY_NAMES_LONG[(d.getUTCDay() + 6) % 7],
    day: d.getUTCDate(),
    month0: d.getUTCMonth(),
    year: d.getUTCFullYear(),
  };
}

export function shortDate(iso: string): string {
  const p = utcParts(iso);
  const day = String(p.day).padStart(2, "0");
  const month = String(p.month0 + 1).padStart(2, "0");
  return `${p.weekday}, ${day}.${month}.${p.year}`;
}

export function dayMonth(iso: string): string {
  const p = utcParts(iso);
  return `${p.weekday}, ${String(p.day).padStart(2, "0")}.${String(p.month0 + 1).padStart(2, "0")}.`;
}

export function monthLabel(iso: string, currentYear: number): string {
  const p = utcParts(iso);
  const name = MONTH_NAMES[p.month0];
  return p.year === currentYear ? name : `${name} ${p.year}`;
}

export function longDate(iso: string): string {
  const p = utcParts(iso);
  return `${p.weekdayLong}, ${p.day}. ${MONTH_NAMES[p.month0]} ${p.year}`;
}

