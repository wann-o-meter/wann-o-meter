type Resolution = "month" | "day" | "minute";

// Month arithmetic on "YYYY-MM". Kept as strings rather than Date objects
// because a month is what the calendar rules count in, and a Date drags a day
// and a timezone along that then have to be argued away.
export function shiftMonth(
  yyyyMm: string,
  n: number,
): { year: number; month0: number } {
  const [y, m] = yyyyMm.split("-").map(Number);
  const total = m - 1 + n;
  return { year: y + Math.floor(total / 12), month0: ((total % 12) + 12) % 12 };
}

export function monthKey(year: number, month0: number): string {
  return `${year}-${String(month0 + 1).padStart(2, "0")}`;
}

// Day 0 of the next month is the last day of this one, leap years included.
export function endOfMonth(yyyyMm: string): string {
  const { year, month0 } = shiftMonth(yyyyMm, 0);
  return new Date(Date.UTC(year, month0 + 1, 0)).toISOString().slice(0, 10);
}

const MONTH_RE = /^--(\d{2})$/;
const DAY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const MINUTE_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

export function resolution(date: string): Resolution {
  if (MONTH_RE.test(date)) return "month";
  if (DAY_RE.test(date)) return "day";
  if (MINUTE_RE.test(date)) return "minute";
  throw new Error(`Unknown ISO 8601 partial date format: "${date}"`);
}

interface ConcreteWindow {
  from: string;
  to: string;
}

function lastDayOfMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function resolveMonthWindow(from: string, to: string, year: number): ConcreteWindow {
  const fromMatch = from.match(MONTH_RE);
  const toMatch = to.match(MONTH_RE);
  if (!fromMatch || !toMatch) {
    throw new Error(`resolveMonthWindow expects "--MM" format, got "${from}".."${to}"`);
  }
  const fromMonth = Number(fromMatch[1]);
  const toMonth = Number(toMatch[1]);
  const toYear = toMonth < fromMonth ? year + 1 : year;

  return {
    from: `${year}-${pad(fromMonth)}-01`,
    to: `${toYear}-${pad(toMonth)}-${pad(lastDayOfMonth(toYear, toMonth))}`,
  };
}
