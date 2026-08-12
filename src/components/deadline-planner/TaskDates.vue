<script setup lang="ts">
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { longDate } from "../../../lib/date-display";

defineProps<{
  entry: ScheduleEntry;
  isPast: boolean;
  done: boolean;
  showRescueLabel: boolean;
}>();
</script>

<template>
  <p v-if="isPast && !done && entry.rescue" class="dates">
    <span class="meta">
      Die Frist war am {{ longDate(entry.date!) }}. Bis
      {{ longDate(entry.rescue.date) }} nachholen.
      <template v-if="showRescueLabel">{{ entry.rescue.label }}.</template>
    </span>
  </p>
  <p v-else class="dates">
    <span :class="{ overdue: isPast }">
      Frist: {{ longDate(entry.date!)
      }}<template v-if="isPast"> (verstrichen)</template>
    </span>
    <template v-if="entry.earliestDate !== entry.date">
      &nbsp;·&nbsp; möglich ab: {{ longDate(entry.earliestDate!) }}
    </template>
    <template v-if="entry.startByDate !== entry.date">
      &nbsp;·&nbsp;
      <b>Termin buchen bis: {{ longDate(entry.startByDate!) }}</b>
    </template>
  </p>
</template>

<style scoped>
.dates {
  margin: 0.35rem 0 0;
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--muted);
}
.dates b {
  color: var(--ink);
  font-weight: 600;
}
.overdue {
  color: var(--warn);
}
.lead {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--ink);
}
.meta {
  font-size: var(--fs-sm);
  color: var(--muted);
}
</style>
