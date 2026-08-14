export const MONTH_NAMES = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

const WEEKDAY_NAMES_LONG = [
  "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag",
];

export const WEEKDAY_NAMES_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

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

// One date rule for the whole site: an Anker or a Frist carries its year
// (shortDate), rows in a list drop it (dayMonth). No third form.
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

export function daysUntil(iso: string, from: string): number {
  return Math.round(
    (new Date(`${iso}T00:00:00Z`).getTime() -
      new Date(`${from}T00:00:00Z`).getTime()) /
      86400000,
  );
}

// Number and unit stay separate so the number can be set in mono like a date.
// Below two weeks days read more precisely than a rounded week count.
export function spanParts(days: number): { n: number; unit: string } {
  const n = Math.abs(days);
  if (n < 14) return { n, unit: n === 1 ? "Tag" : "Tage" };
  return { n: Math.round(n / 7), unit: "Wochen" };
}

// "vor drei Tagen", "in drei Wochen": only the plural of Tag takes the -n.
export function dativeUnit(unit: string): string {
  return unit === "Tage" ? "Tagen" : unit;
}

export function longDate(iso: string): string {
  const p = utcParts(iso);
  return `${p.weekdayLong}, ${p.day}. ${MONTH_NAMES[p.month0]} ${p.year}`;
}

