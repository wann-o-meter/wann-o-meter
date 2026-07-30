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

// A chart with no colored cell anywhere carries no information - same
// escape-hatch principle as lib/year-grid.ts's own density guard, just
// measured across the whole rolling window instead of a single year.
export function hasCoverage(chart: BandChart): boolean {
  return chart.rows.some((row) => row.cells.some((c) => c.state === "primary" || c.state === "accent"));
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
