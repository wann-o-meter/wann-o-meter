<script setup lang="ts">
// Template: one week, a column per day, every match spelled out by name
// (the only template that shows titles rather than colour marks).
import { computed } from "vue";
import { WEEKDAY_NAMES_LONG, isoWeekNumber } from "../../../lib/date-display";
import { type DayLayer, isoFromDate, matchesForDay } from "../../../lib/date-grid";
import ViewNav from "./ViewNav.vue";

const props = defineProps<{
  weekStart: string;
  layers: DayLayer[];
  todayIso: string;
  selectedDay: string | null;
  prevDisabled?: boolean;
  nextDisabled?: boolean;
}>();
const emit = defineEmits<{ (e: "prev"): void; (e: "next"): void }>();

const days = computed(() => {
  const start = new Date(`${props.weekStart}T00:00:00`);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return isoFromDate(d);
  });
});

const weekNumber = computed(() => isoWeekNumber(new Date(`${props.weekStart}T00:00:00`)));

function formatShort(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}.`;
}

const title = computed(() => {
  const d = days.value;
  // No space before the year: formatShort already ends in the separating dot,
  // so "09.08." + "2026" is the German "09.08.2026", not "09.08. 2026".
  return `KW ${weekNumber.value} · ${formatShort(d[0])}–${formatShort(d[6])}${d[6].slice(0, 4)}`;
});

function matches(dayIso: string) {
  return matchesForDay(dayIso, props.layers);
}
</script>

<template>
  <div class="week-view">
    <ViewNav
      :title="title"
      :prev-disabled="prevDisabled"
      :next-disabled="nextDisabled"
      @prev="emit('prev')"
      @next="emit('next')"
    />
    <div class="week-days">
      <div
        v-for="(dayIso, i) in days"
        :key="dayIso"
        class="day-column"
        :class="{ today: dayIso === todayIso, selected: dayIso === selectedDay }"
      >
        <!-- h2, not h4: the seven days are this view's top-level sections and
             the only heading above them is the page's h1, so h4 skipped two
             levels (axe heading-order). -->
        <h2>
          {{ WEEKDAY_NAMES_LONG[i] }} <span class="day-number">{{ Number(dayIso.slice(8)) }}</span>
        </h2>
        <ul class="event-list">
          <li v-for="(match, j) in matches(dayIso)" :key="j">
            <a :href="match.url" class="event-link">
              <span class="dot" :style="{ background: match.color }" />
              {{ match.title }}
            </a>
          </li>
          <li v-if="matches(dayIso).length === 0" class="no-events">–</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.week-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.day-column {
  background: var(--paper);
  padding: 0.7rem;
  min-height: 10rem;
}
.day-column.today {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.day-column.today h2 {
  color: var(--accent);
}
.day-column.selected {
  background: var(--paper-raised);
  outline: 2px dashed var(--accent);
  outline-offset: -2px;
}
/* border/padding reset: global.css underlines every h2, and these are column
   captions rather than page sections. */
.day-column h2 {
  margin: 0 0 0.6rem;
  padding: 0;
  border: 0;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
}
.day-column .day-number {
  color: var(--ink);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.78rem;
}
.event-link {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: inherit;
  text-decoration: none;
}
.event-link:hover {
  color: var(--accent);
}
.dot {
  width: 0.65rem;
  height: 0.65rem;
  display: inline-block;
  flex-shrink: 0;
  margin-top: 0.3rem;
}
.no-events {
  color: var(--muted);
}

@media (max-width: 60rem) {
  .week-days {
    grid-template-columns: 1fr;
  }
}
</style>
