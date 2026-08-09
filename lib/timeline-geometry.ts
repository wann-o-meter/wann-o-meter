// Pure geometry for the timeline rail: the day/pixel scale, the window that
// has to stay on screen, and the lane packer. Lives outside Timeline.vue so
// the math can be tested without a DOM, and so the component is left with
// rendering and events only. Browser-safe by construction, nothing here
// imports anything (see lib/deadline-plan.ts on why that matters).

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

export interface Scale {
  start: Date;
  end: Date;
  ppd: number; // pixels per day
  edge: number; // px reserved left and right for caps and labels
  width: number; // total track width in px
  x(d: Date): number;
  dateAt(x: number): Date;
}

export function makeScale(
  start: Date,
  end: Date,
  ppd: number,
  edge = 0,
): Scale {
  const days = Math.max(1, daysBetween(start, end));
  return {
    start,
    end,
    ppd,
    edge,
    width: Math.round(days * ppd) + edge * 2,
    x: (d) => Math.round(edge + ((d.getTime() - start.getTime()) / DAY_MS) * ppd),
    dateAt: (x) => addDays(start, Math.round((x - edge) / ppd)),
  };
}

/**
 * The day window the rail must show: today plus every relevant date, with a
 * little air on both sides. Dates outside [hardStart, hardEnd] are ignored
 * (a +1400 day Rundfunkbeitrag would otherwise flatten the whole scale), and
 * today is always inside the result, which is what keeps the "HEUTE" marker
 * on screen no matter which task is in focus.
 */
export function fitWindow(
  today: Date,
  dates: Date[],
  hardStart: Date,
  hardEnd: Date,
  padDays = 3,
  minSpanDays = 0,
): { start: Date; end: Date } {
  let lo = today.getTime();
  let hi = today.getTime();
  for (const d of dates) {
    const t = d.getTime();
    if (t < hardStart.getTime() || t > hardEnd.getTime()) continue;
    if (t < lo) lo = t;
    if (t > hi) hi = t;
  }
  const span = Math.max(1, Math.round((hi - lo) / DAY_MS));
  // The minimum is what stops a two-task plan from spreading a single week
  // across a whole screen, so the scale below needs no upper clamp of its own.
  const pad = Math.ceil(
    Math.max(padDays, span * 0.06, (minSpanDays - span) / 2),
  );
  return { start: addDays(new Date(lo), -pad), end: addDays(new Date(hi), pad) };
}

/**
 * Pixels per day that makes `spanDays` fill `width`, minus the `edge` px the
 * first and last node need for their caps and labels. Only clamped from
 * below: under `min` a dense plan is unreadable, so it scrolls instead. There
 * is no upper clamp on purpose, the window's own minimum span (see fitWindow
 * and zoomWindow) is what keeps a short plan from spreading, and a clamp here
 * would leave the strip narrower than its container.
 */
export function fitPpd(
  spanDays: number,
  width: number,
  min: number,
  edge = 0,
): number {
  const usable = width - edge * 2;
  if (!(usable > 0) || !(spanDays > 0)) return min;
  return Math.max(min, usable / spanDays);
}

/**
 * Horizontal scroll offset that centres `focusX` while keeping `todayX` on
 * screen. Only needed when the rail does not fit its container (see fitPpd's
 * min clamp) - when both cannot be centred, today wins, so the HEUTE marker
 * never leaves the strip.
 */
export function scrollTargetFor(
  focusX: number,
  todayX: number,
  viewportW: number,
  trackW: number,
  margin = 24,
): number {
  const centred = focusX - viewportW / 2;
  const earliest = todayX + margin - viewportW; // today at the right edge
  const latest = todayX - margin; // today at the left edge
  const keptVisible = Math.min(Math.max(centred, earliest), latest);
  return Math.min(Math.max(keptVisible, 0), Math.max(0, trackW - viewportW));
}

export interface LaneItem {
  id: string;
  left: number;
  width: number;
}

/**
 * Greedy first-fit interval packing on rendered pixel spans, so two capsules
 * share a lane exactly when they do not touch on screen. First fit keeps the
 * strip hugging the axis, only real collisions climb. Ties break widest-first
 * so long bars claim the low lanes and short dots stack above them rather
 * than fragmenting a lane.
 */
export function packLanes(
  items: LaneItem[],
  maxLanes: number,
  pad = 6,
): Map<string, number> {
  const laneEnd: number[] = [];
  const lanes = new Map<string, number>();
  const sorted = [...items].sort(
    (a, b) => a.left - b.left || b.width - a.width || a.id.localeCompare(b.id),
  );
  for (const item of sorted) {
    const right = item.left + item.width;
    let lane = laneEnd.findIndex((end) => end + pad <= item.left);
    if (lane === -1) {
      if (laneEnd.length < maxLanes) {
        lane = laneEnd.length;
        laneEnd.push(-Infinity);
      } else {
        // Cap reached: drop into the lane that frees up soonest, the one
        // where the unavoidable overlap is smallest.
        lane = laneEnd.indexOf(Math.min(...laneEnd));
      }
    }
    // max(), never plain assignment - a narrow capsule dropped into an
    // occupied lane must not shorten that lane's occupancy and let the next
    // one land on top of the wide bar underneath.
    laneEnd[lane] = Math.max(laneEnd[lane] ?? -Infinity, right);
    lanes.set(item.id, lane);
  }
  return lanes;
}

export function laneCount(lanes: Map<string, number>): number {
  let max = 0;
  for (const lane of lanes.values()) max = Math.max(max, lane);
  return max + 1;
}

/** Mondays inside [start, end], as Dates. */
export function mondays(start: Date, end: Date): Date[] {
  const out: Date[] = [];
  const d = new Date(start);
  d.setUTCDate(d.getUTCDate() + ((7 - ((d.getUTCDay() + 6) % 7)) % 7));
  for (; d <= end; d.setUTCDate(d.getUTCDate() + 7)) out.push(new Date(d));
  return out;
}

/** First of every month inside [start, end], as Dates. */
export function monthStarts(start: Date, end: Date): Date[] {
  const out: Date[] = [];
  let m = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
  while (m < end) {
    if (m >= start) out.push(m);
    m = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1));
  }
  return out;
}
