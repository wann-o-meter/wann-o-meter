<script setup lang="ts">
// Template: twelve mini month grids. One of the interchangeable renderers
// under this directory - takes state as props, emits navigation intent, owns
// no business logic (see Kalender.vue, which holds the state).
import { MONTH_NAMES } from "../../../lib/date-display";
import type { DayLayer } from "../../../lib/date-grid";
import MonthGrid from "./MonthGrid.vue";

defineProps<{ year: number; layers: DayLayer[]; todayIso: string }>();
const emit = defineEmits<{
  (e: "month-click", monthIndex0: number): void;
  (e: "day-click", dayIso: string): void;
  (e: "week-click", mondayIso: string): void;
}>();
</script>

<template>
  <div class="months">
    <div v-for="(name, monthIndex0) in MONTH_NAMES" :key="name" class="month">
      <h3
        role="button"
        tabindex="0"
        @click="emit('month-click', monthIndex0)"
        @keydown.enter="emit('month-click', monthIndex0)"
      >
        {{ name }}
      </h3>
      <MonthGrid
        :year="year"
        :month-index0="monthIndex0"
        :layers="layers"
        :today-iso="todayIso"
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
.month h3 {
  margin: 0 0 0.6rem;
  font-size: 0.85rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  cursor: pointer;
  width: fit-content;
}
.month h3:hover {
  color: var(--accent);
}
</style>
