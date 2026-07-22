<script setup lang="ts">
// The grid-building logic (weeksOfMonth + day-cell + matchesForDay marks)
// used to be duplicated twice in Kalender.vue: once per month in the year
// view's 12 mini-grids, once for the month view's single big grid. Same
// iteration, same day-matching, just different CSS sizing and a different
// click target (an individual day in the mini grid vs. the whole week row
// in the full grid) - modeled here as one `variant` prop instead of two
// components, since the geometry that actually varies (which element you
// click) is a real difference, not incidental duplication.
import { computed } from "vue";
import { type DayLayer, matchesForDay, weeksOfMonth } from "../../lib/date-grid";

const WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

const props = defineProps<{
  year: number;
  monthIndex0: number;
  layers: DayLayer[];
  todayIso: string;
  variant: "mini" | "full";
}>();

const emit = defineEmits<{
  (e: "day-click", dayIso: string): void;
  (e: "week-click", mondayIso: string): void;
}>();

const weeks = computed(() => weeksOfMonth(props.year, props.monthIndex0));

function isOtherMonth(dayIso: string): boolean {
  return Number(dayIso.slice(5, 7)) - 1 !== props.monthIndex0;
}

function matches(dayIso: string) {
  return matchesForDay(dayIso, props.layers);
}
</script>

<template>
  <template v-if="variant === 'mini'">
    <div class="weekdays">
      <span class="week-col-header">KW</span>
      <span v-for="wd in WEEKDAY_NAMES" :key="wd">{{ wd }}</span>
    </div>
    <div v-for="week in weeks" :key="week.mondayIso" class="day-week">
      <button type="button" class="week-number mini" title="Woche öffnen" @click="emit('week-click', week.mondayIso)">
        {{ week.number }}
      </button>
      <span
        v-for="dayIso in week.days"
        :key="dayIso"
        class="day"
        :class="{ today: dayIso === todayIso, 'other-month': isOtherMonth(dayIso) }"
        role="button"
        tabindex="0"
        :title="[...matches(dayIso).map((m) => m.title), 'Woche öffnen'].join(', ')"
        @click="emit('day-click', dayIso)"
        @keydown.enter="emit('day-click', dayIso)"
      >
        {{ Number(dayIso.slice(8)) }}
        <span class="marks">
          <a
            v-for="(match, i) in matches(dayIso)"
            :key="i"
            class="mark"
            :href="match.url"
            :title="match.title"
            :style="{ background: match.color }"
          />
        </span>
      </span>
    </div>
  </template>

  <template v-else>
    <div class="month-grid-header">
      <span class="week-number-header">KW</span>
      <span v-for="wd in WEEKDAY_NAMES" :key="wd">{{ wd }}</span>
    </div>
    <div
      v-for="week in weeks"
      :key="week.mondayIso"
      class="week-row"
      role="button"
      tabindex="0"
      title="Diese Woche öffnen"
      @click="emit('week-click', week.mondayIso)"
      @keydown.enter="emit('week-click', week.mondayIso)"
    >
      <button type="button" class="week-number" title="Diese Woche öffnen" @click.stop="emit('week-click', week.mondayIso)">
        {{ week.number }}
      </button>
      <span
        v-for="dayIso in week.days"
        :key="dayIso"
        class="day-cell"
        :class="{ 'other-month': isOtherMonth(dayIso), today: dayIso === todayIso }"
        :title="matches(dayIso).map((m) => m.title).join(', ')"
      >
        <span class="day-number">{{ Number(dayIso.slice(8)) }}</span>
        <span class="marks">
          <a
            v-for="(match, i) in matches(dayIso)"
            :key="i"
            class="mark"
            :href="match.url"
            :title="match.title"
            :style="{ background: match.color }"
          />
        </span>
      </span>
    </div>
  </template>
</template>

<style scoped>
.weekdays,
.day-week {
  display: grid;
  grid-template-columns: 1.4rem repeat(7, 1fr);
  gap: 2px;
}
.day-week {
  margin-bottom: 2px;
}
.weekdays span {
  text-align: center;
  color: var(--muted);
  font-size: 0.68rem;
}
.week-col-header {
  font-family: var(--font-mono);
}
.day {
  text-align: center;
  padding: 0.2rem 0;
  cursor: pointer;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.day:hover {
  background: var(--paper-raised);
}
.day.today {
  background: var(--accent);
  color: var(--accent-ink);
}
.day.other-month {
  color: var(--muted);
  opacity: 0.5;
}
.marks {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 1px;
  min-height: 0.3rem;
  margin-top: 0.15rem;
}
.mark {
  width: 0.3rem;
  height: 0.3rem;
  display: inline-block;
}
.mark:hover {
  outline: 1px solid var(--ink);
  outline-offset: 1px;
}

.month-grid-header,
.week-row {
  display: grid;
  grid-template-columns: 2.5rem repeat(7, 1fr);
  gap: 2px;
}
.month-grid-header {
  margin-bottom: 2px;
}
.month-grid-header span {
  text-align: center;
  color: var(--muted);
  font-size: 0.7rem;
}
.week-number-header {
  font-family: var(--font-mono);
}
.week-row {
  background: var(--line);
  margin-bottom: 2px;
  cursor: pointer;
}
.week-row:hover .day-cell {
  background: var(--paper-raised);
}
.week-number {
  background: var(--paper);
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.week-number:hover {
  color: var(--accent);
  background: var(--paper-raised);
}
.week-number.mini {
  background: none;
  font-size: 0.62rem;
  padding: 0;
}
.day-cell {
  background: var(--paper);
  min-height: 4rem;
  padding: 0.4rem;
  display: flex;
  flex-direction: column;
  font-family: var(--font-mono);
}
.day-cell.other-month {
  color: var(--muted);
  opacity: 0.5;
}
.day-cell.today {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.day-cell.today .day-number {
  color: var(--accent);
  font-weight: 600;
}
.day-number {
  font-variant-numeric: tabular-nums;
}
.day-cell .marks {
  justify-content: flex-start;
  margin-top: auto;
}
</style>
