<script setup lang="ts">
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { longDate, shortDate, windowLabel } from "../../../lib/date-display";

defineProps<{
  entry: ScheduleEntry;
  anchorLabel: string;
  isPast: boolean;
  done: boolean;
}>();
</script>

<template>
  <!-- Two treatments, and the wording is the whole difference: a Frist names
  the day it is due, a recommendation names the window it sits in. -->
  <p v-if="entry.kind === 'soft'" class="dates soft">
    <template v-if="entry.offset_days === 0">
      Empfohlen: am {{ anchorLabel }}
    </template>
    <template v-else>
      Empfohlen: ab <span class="d">{{ windowLabel(entry.date!) }}</span>
    </template>
  </p>
  <p v-else-if="isPast && !done && entry.rescue" class="dates">
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
  margin: var(--s-1) 0 0;
  font-size: var(--t-meta);
  color: var(--muted);
}
.d {
  font-variant-numeric: tabular-nums;
}
.dates b {
  color: var(--ink);
  font-weight: var(--fw-semibold);
}
.overdue {
  color: var(--overdue);
}
</style>
