<script setup lang="ts">
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { longDate, shortDate } from "../../../lib/date-display";

defineProps<{
  entry: ScheduleEntry;
  isPast: boolean;
  done: boolean;
}>();
</script>

<template>
  <p v-if="isPast && !done && entry.rescue" class="dates">
    Frist war <span class="d">{{ shortDate(entry.date!) }}</span
    >, nachholen bis <b class="d">{{ longDate(entry.rescue.date) }}</b
    >.
  </p>
  <p v-else class="dates">
    <span :class="{ overdue: isPast }"
      >Frist: <b class="d">{{ longDate(entry.date!) }}</b
      ><template v-if="isPast"> (verstrichen)</template></span
    >
    <template v-if="entry.earliestDate !== entry.date">
      &nbsp;·&nbsp; möglich ab
      <span class="d">{{ shortDate(entry.earliestDate!) }}</span>
    </template>
    <template v-if="entry.startByDate !== entry.date">
      &nbsp;·&nbsp; Termin buchen bis
      <b class="d">{{ shortDate(entry.startByDate!) }}</b>
    </template>
  </p>
</template>

<style scoped>
.dates {
  margin: 0.35rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}
/* Monospace marks hard dates only, never the prose around them. */
.d {
  font-family: var(--font-mono);
}
.dates b {
  color: var(--ink);
  font-weight: 600;
}
.overdue {
  color: var(--warn);
}
</style>
