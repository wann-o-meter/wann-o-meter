// Turns a rolling day window plus per-scope ranges into the schulferien.org-
// style band chart src/components/BandChart.astro renders: one row per scope
// (Bundesland, fruit/vegetable, ...), one column per day, a colored band
// where a range covers that day. Domain-agnostic on purpose - the caller
// decides what a "scope" and a "range" are (src/pages/[...path].astro merges
// in a second, higher-priority range kind for Schulferien's Feiertage
// overlay, which this file knows nothing about).
import { MONTH_NAMES, WEEKDAY_NAMES_SHORT } from "./date-display";

export type BandCellState = "plain" | "weekend" | "primary" | "accent";

export interface BandChartRangeInput {
  start: string;
  end: string; // inclusive, same as `start` for a single day
  title: string;
  kind: "primary" | "accent"; // accent wins where both cover the same day
}

export interface BandChartRowInput {
  scopeId: string;
  label: string;
  href: string;
  layerId: string; // e.g. "schulferien--nw" - what a day cell's calendar link activates
  ranges: BandChartRangeInput[];
}

export interface BandChartCell {
  iso: string;
  state: BandCellState;
  title?: string;
}

export interface BandChartRow {
  scopeId: string;
  label: string;
  href: string;
  layerId: string;
  cells: BandChartCell[];
}

export interface BandChartDay {
  iso: string;
  weekday: string;
  dayOfMonth: number;
  weekend: boolean;
  today: boolean;
}

export interface BandChartMonthSegment {
  label: string;
  days: number; // colspan over the day header row
}

export interface BandChart {
  days: BandChartDay[];
  months: BandChartMonthSegment[];
  rows: BandChartRow[];
}

function shiftIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// STRUCTURAL, not a per-category allowlist (same rule lib/year-pages.ts
// documents for its own state-code detection): a category's data is
// "range-shaped" when most of its events span more than a single day
// (PageEvent.to set) - Schulferien and Urlaubsfenster windows, not
// Feiertage's single dates. Majority vote, not "any", so one stray
// multi-day entry in an otherwise point-shaped category doesn't flip it.
export function isRangeShaped(events: { to?: string }[]): boolean {
  if (events.length === 0) return false;
  return events.filter((e) => e.to !== undefined).length / events.length > 0.5;
}

// Rolling ~70 days centred on today (spec's own default): the question this
// view answers is "who is off right now / soon", not a fixed calendar year.
export function defaultWindow(todayIso: string): { start: string; end: string } {
  return { start: shiftIso(todayIso, -10), end: shiftIso(todayIso, 60) };
}

function buildDays(windowStart: string, windowEnd: string, todayIso: string): BandChartDay[] {
  const days: BandChartDay[] = [];
  for (let iso = windowStart; iso <= windowEnd; iso = shiftIso(iso, 1)) {
    const weekdayIndex = (new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7; // Mon=0
    days.push({
      iso,
      weekday: WEEKDAY_NAMES_SHORT[weekdayIndex],
      dayOfMonth: Number(iso.slice(8, 10)),
      weekend: weekdayIndex >= 5,
      today: iso === todayIso,
    });
  }
  return days;
}

function buildMonths(days: BandChartDay[]): BandChartMonthSegment[] {
  const segments: BandChartMonthSegment[] = [];
  for (const day of days) {
    const label = `${MONTH_NAMES[Number(day.iso.slice(5, 7)) - 1]} ${day.iso.slice(0, 4)}`;
    const last = segments.at(-1);
    if (last && last.label === label) last.days += 1;
    else segments.push({ label, days: 1 });
  }
  return segments;
}

function cellFor(day: BandChartDay, ranges: BandChartRangeInput[]): BandChartCell {
  const matches = ranges.filter((r) => r.start <= day.iso && day.iso <= r.end);
  const hit = matches.find((r) => r.kind === "accent") ?? matches.find((r) => r.kind === "primary");
  return {
    iso: day.iso,
    state: hit ? hit.kind : day.weekend ? "weekend" : "plain",
    title: hit?.title,
  };
}

export function buildBandChart(rows: BandChartRowInput[], windowStart: string, windowEnd: string, todayIso: string): BandChart {
  const days = buildDays(windowStart, windowEnd, todayIso);
  return {
    days,
    months: buildMonths(days),
    rows: rows.map((row) => ({
      scopeId: row.scopeId,
      label: row.label,
      href: row.href,
      layerId: row.layerId,
      cells: days.map((day) => cellFor(day, row.ranges)),
    })),
  };
}
