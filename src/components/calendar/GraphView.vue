<script setup lang="ts">
// Template: a year-wide second lens over the same layer data. The other
// templates stay true/false per day (PLAN.md 4.2); this one aggregates that
// into a per-bucket density count per layer instead of drilling into a
// single day - which is why it owns its own granularity state rather than
// following the shared month/week navigation.
//
// No numeric value/unit is populated on any window yet (checked across
// data/**/*.yaml - lib/schema.ts's MaterializedWindow already has the fields
// for when that lands), so the only honest thing to plot today is density:
// how many days per bucket a layer is active. It still surfaces the
// seasonality/clustering the calendar marks don't make visible at a glance.
// Bucket size is user-chosen (month/week) - the underlying windows are
// day-precision already, so this is just a different grouping of the same
// data. Day buckets (365 near-empty slivers, no useful axis) were tried and
// dropped; week is the finest granularity worth looking at.
import { computed, ref } from "vue";
import { MONTH_NAMES, isoWeekNumber } from "../../../lib/date-display";
import { type DayLayer, daysInMonth, isoDate, isoFromDate, mondayOf } from "../../../lib/date-grid";
import ViewNav from "./ViewNav.vue";

type GraphLayer = DayLayer & { id: string };

const props = defineProps<{
  year: number;
  layers: GraphLayer[];
  prevDisabled?: boolean;
  nextDisabled?: boolean;
}>();
const emit = defineEmits<{ (e: "prev"): void; (e: "next"): void }>();

type Granularity = "month" | "week";
const granularity = ref<Granularity>("month");

interface GraphBucket {
  label: string;
  count: number;
  total: number;
}

function isActiveDay(layer: GraphLayer, iso: string): boolean {
  return layer.windows.some((w) => w.start <= iso && iso <= w.end);
}

function activeDaysInMonth(layer: GraphLayer, monthIndex0: number): number {
  const total = daysInMonth(props.year, monthIndex0);
  let count = 0;
  for (let day = 1; day <= total; day++) {
    if (isActiveDay(layer, isoDate(props.year, monthIndex0, day))) count++;
  }
  return count;
}

// All ISO dates in the given year, in order - only used to build weekGroups
// below (month buckets have their own cheap dedicated path above).
function isoDatesOfYear(y: number): string[] {
  const dates: string[] = [];
  for (let m = 0; m < 12; m++) {
    const total = daysInMonth(y, m);
    for (let day = 1; day <= total; day++) dates.push(isoDate(y, m, day));
  }
  return dates;
}

// Every Monday-Sunday week touching the year, with the (possibly partial)
// list of that week's days that fall in it. Computed once per year
// regardless of layer count, since every layer's week buckets and the shared
// x-axis both need the exact same weeks.
const weekGroups = computed(() => {
  const byMonday = new Map<string, string[]>();
  for (const iso of isoDatesOfYear(props.year)) {
    const monday = isoFromDate(mondayOf(new Date(`${iso}T00:00:00`)));
    if (!byMonday.has(monday)) byMonday.set(monday, []);
    byMonday.get(monday)!.push(iso);
  }
  return [...byMonday.entries()].map(([mondayIso, days]) => ({ mondayIso, days }));
});

// A week's "month" is the month of its first in-year day, not of its Monday -
// the year's first/last week is partial (isoDatesOfYear never includes the
// adjacent year's days), so for e.g. the week Monday=Dec 29 whose only
// in-year days are Jan 1-4, this reports January (what the bar and its axis
// label are actually showing), not December (which contributed zero days).
function weekMonthIndex0(days: string[]): number {
  return Number(days[0].slice(5, 7)) - 1;
}

function weekBuckets(layer: GraphLayer): GraphBucket[] {
  return weekGroups.value.map((w) => ({
    // Both month and week in the label (not just "KW 29") since the x-axis
    // only groups by month - the week number would otherwise be invisible
    // except on hover.
    label: `${MONTH_NAMES[weekMonthIndex0(w.days)]}, KW ${isoWeekNumber(new Date(`${w.mondayIso}T00:00:00`))}`,
    count: w.days.filter((iso) => isActiveDay(layer, iso)).length,
    total: w.days.length,
  }));
}

const rows = computed(() =>
  props.layers
    .filter((l) => l.visible)
    .map((l) => ({
      layer: l,
      buckets:
        granularity.value === "month"
          ? MONTH_NAMES.map((name, monthIndex0) => ({
              label: name.slice(0, 3),
              count: activeDaysInMonth(l, monthIndex0),
              total: daysInMonth(props.year, monthIndex0),
            }))
          : weekBuckets(l),
    })),
);

// Grid columns for the bar rows (and the x-axis row, which must line up with
// them exactly) - a plain 1fr split for month's fixed 12 columns, a floor
// width for week so a year's ~52 columns don't squeeze into invisible
// slivers (the container scrolls horizontally instead).
const barsColumns = computed(() => {
  const n = rows.value[0]?.buckets.length ?? 12;
  return granularity.value === "week" ? `repeat(${n}, minmax(5px, 1fr))` : `repeat(${n}, 1fr)`;
});

// One label per month, each spanning however many grid columns belong to it -
// 1 each for month granularity, a run-length-encoded span of weeks for week.
const axisGroups = computed(() => {
  if (granularity.value === "month") return MONTH_NAMES.map((name) => ({ label: name.slice(0, 3), span: 1 }));
  const groups: { label: string; span: number }[] = [];
  for (const w of weekGroups.value) {
    const label = MONTH_NAMES[weekMonthIndex0(w.days)].slice(0, 3);
    const last = groups[groups.length - 1];
    if (last && last.label === label) last.span++;
    else groups.push({ label, span: 1 });
  }
  return groups;
});
</script>

<template>
  <div class="graph-view">
    <ViewNav
      :title="`Verteilung ${year}`"
      :prev-disabled="prevDisabled"
      :next-disabled="nextDisabled"
      @prev="emit('prev')"
      @next="emit('next')"
    />
    <div class="granularity-toggle">
      <button type="button" :class="{ active: granularity === 'month' }" @click="granularity = 'month'">Monat</button>
      <button type="button" :class="{ active: granularity === 'week' }" @click="granularity = 'week'">Woche</button>
    </div>
    <p v-if="rows.length === 0" class="no-layers">Keine sichtbaren Ebenen ausgewählt.</p>
    <template v-else>
      <div class="graph-rows">
        <div v-for="row in rows" :key="row.layer.id" class="graph-row">
          <span class="graph-row-label" :title="row.layer.label">
            <span class="dot" :style="{ background: row.layer.color }" />
            <span class="layer-label-text">{{ row.layer.label }}</span>
          </span>
          <div class="graph-bars" :style="{ gridTemplateColumns: barsColumns }">
            <div
              v-for="(bucket, i) in row.buckets"
              :key="i"
              class="graph-bar-slot"
              :title="`${bucket.label}: ${bucket.count}/${bucket.total} Tag(e)`"
            >
              <div
                class="graph-bar"
                :style="{ height: `${(bucket.count / bucket.total) * 100}%`, background: row.layer.color }"
              />
            </div>
          </div>
        </div>
      </div>
      <div class="graph-months-row">
        <span class="graph-row-label-spacer" />
        <div class="graph-months" :style="{ gridTemplateColumns: barsColumns }">
          <span v-for="(group, i) in axisGroups" :key="i" :style="{ gridColumn: `span ${group.span}` }">
            {{ group.label }}
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.granularity-toggle {
  display: flex;
  justify-content: center;
  gap: 0.4rem;
  margin-bottom: 1rem;
}
.granularity-toggle button {
  font-size: 0.78rem;
  padding: 0.25rem 0.7rem;
}
.granularity-toggle button.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.no-layers {
  color: var(--muted);
  font-size: 0.85rem;
  padding: 0.5rem 0.1rem;
}
.graph-rows {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}
.graph-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.graph-row-label,
.graph-row-label-spacer {
  width: 12rem;
  flex-shrink: 0;
}
.graph-row-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  font-size: 0.8rem;
}
.dot {
  width: 0.65rem;
  height: 0.65rem;
  display: inline-block;
  flex-shrink: 0;
}
.layer-label-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.graph-bars {
  flex: 1;
  display: grid;
  gap: 3px;
  height: 3rem;
  overflow-x: auto;
}
.graph-bar-slot {
  height: 100%;
  display: flex;
  align-items: flex-end;
  background: var(--paper-raised);
}
.graph-bar {
  width: 100%;
  min-height: 2px;
}
.graph-months-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.4rem;
}
.graph-months {
  flex: 1;
  display: grid;
  gap: 3px;
  overflow-x: auto;
}
.graph-months span {
  text-align: center;
  font-size: 0.65rem;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
