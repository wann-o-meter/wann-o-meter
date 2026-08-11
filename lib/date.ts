type Resolution = "month" | "day" | "minute";

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
