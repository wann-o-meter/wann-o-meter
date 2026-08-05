<script setup lang="ts">
// Template: twelve mini month grids. One of the interchangeable renderers
// under this directory - takes state as props, emits navigation intent, owns
// no business logic (see Kalender.vue, which holds the state).
import { MONTH_NAMES } from "../../../lib/date-display";
import type { DayLayer } from "../../../lib/date-grid";
import MonthGrid from "./MonthGrid.vue";

defineProps<{
  year: number;
  layers: DayLayer[];
  todayIso: string;
  highlightIso?: string | null;
}>();
const emit = defineEmits<{
  (e: "month-click", monthIndex0: number): void;
  (e: "day-click", dayIso: string): void;
  (e: "week-click", mondayIso: string): void;
}>();
</script>

<template>
  <div class="months">
    <div v-for="(name, monthIndex0) in MONTH_NAMES" :key="name" class="month">
      <!-- A real <button> inside the heading, not role="button" on the heading
        itself: that role *replaces* the heading role, so the twelve months
        vanished from the document outline (leaving H1 -> H4 in the sidebar,
        which is what axe's heading-order flagged) and screen readers lost
        the only structure this view has. Native button also brings Space,
        the disabled/focus semantics and the keydown handler for free. -->
      <h2 class="month-title">
        <button type="button" @click="emit('month-click', monthIndex0)">
          {{ name }}
        </button>
      </h2>
      <MonthGrid
        :year="year"
        :month-index0="monthIndex0"
        :layers="layers"
        :today-iso="todayIso"
        :highlight-iso="highlightIso"
        variant="mini"
        @day-click="emit('day-click', $event)"
        @week-click="emit('week-click', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.months {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.month {
  background: var(--paper);
  padding: 0.9rem;
}
.month-title {
  margin: 0 0 0.6rem;
  padding: 0;
  border: 0;
  font-size: 0.85rem;
  width: fit-content;
}
.month-title button {
  font: inherit;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  background: none;
  border: 0;
  padding: 0.2rem 0.3rem;
  margin: -0.2rem -0.3rem;
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}
.month-title button:hover {
  color: var(--accent);
  border: 0;
}
</style>
