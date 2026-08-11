// Pure geometry for the timeline rail, testable without a DOM. Browser-safe
// by construction, nothing here imports anything (see lib/deadline-plan.ts).
// A day is an integer day number in UTC, never a Date, so no daylight saving
// change can shift a column by an hour.

export const DAY_MS = 86400000;

export function utcDay(d: Date): Date {
  return new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getTime() + n * DAY_MS);
}

export function isoOf(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function daysBetween(from: Date, to: Date): number {
  return Math.round((to.getTime() - from.getTime()) / DAY_MS);
}

/** ISO day string to day number. */
export function dayNum(isoDate: string): number {
  return Math.round(Date.parse(`${isoDate}T00:00:00Z`) / DAY_MS);
}

/** Day number back to an ISO day string. */
export function isoOfDay(n: number): string {
  return new Date(n * DAY_MS).toISOString().slice(0, 10);
}

export function dateOfDay(n: number): Date {
  return new Date(n * DAY_MS);
}

/** 0 = Sunday, matching Date.getUTCDay. 1970-01-01 was a Thursday. */
export function dow(n: number): number {
  return (((n + 4) % 7) + 7) % 7;
}

export function isWeekend(n: number): boolean {
  return dow(n) === 0 || dow(n) === 6;
}

/**
 * The day window the rail shows: everything relevant, widened to whole
 * months so month labels always have their full column and the ends of the
 * strip never cut a month in half.
 */
export function monthWindow(days: number[]): { from: number; to: number } {
  const lo = new Date(Math.min(...days) * DAY_MS);
  const hi = new Date(Math.max(...days) * DAY_MS);
  const from = Date.UTC(lo.getUTCFullYear(), lo.getUTCMonth(), 1);
  const to = Date.UTC(hi.getUTCFullYear(), hi.getUTCMonth() + 1, 0);
  return { from: Math.round(from / DAY_MS), to: Math.round(to / DAY_MS) };
}

/** First day of every month in [from, to], as day numbers. */
export function monthFirsts(from: number, to: number): number[] {
  const out: number[] = [];
  const d = new Date(from * DAY_MS);
  let m = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  while (Math.round(m / DAY_MS) <= to) {
    const n = Math.round(m / DAY_MS);
    if (n >= from) out.push(n);
    const c = new Date(m);
    m = Date.UTC(c.getUTCFullYear(), c.getUTCMonth() + 1, 1);
  }
  return out;
}

export interface LaneItem {
  left: number; // leftmost occupied pixel, capsule included
  right: number; // rightmost occupied pixel, marker included
}

/**
 * Greedy packing over the full occupied width, so two markers can never sit
 * on top of each other. Items must already be sorted by their left edge.
 * Returns one lane index per item, in the order they were passed.
 */
export function packLanes(items: LaneItem[], minGap: number): number[] {
  const laneEnd: number[] = [];
  return items.map((item) => {
    let lane = laneEnd.findIndex((end) => item.left - end >= minGap);
    if (lane === -1) lane = laneEnd.push(-Infinity) - 1;
    laneEnd[lane] = item.right;
    return lane;
  });
}
