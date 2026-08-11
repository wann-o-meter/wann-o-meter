<script setup lang="ts">
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { longDate } from "../../../lib/date-display";

defineProps<{
  entry: ScheduleEntry;
  isPast: boolean;
  done: boolean;
  /** A rescue label is redundant next to the double-rent line on the card. */
  showRescueLabel: boolean;
}>();
</script>

<template>
  <!-- A missed deadline gets one instruction in ink and the dates behind it
    in grey. Everything else on the card ranks below that line. -->
  <p v-if="isPast && !done && entry.rescue" class="dates">
    <span class="lead">Bis {{ longDate(entry.rescue.date) }} nachholen.</span>
    <br />
    <span class="meta">
      Frist war {{ longDate(entry.date!) }}.
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
/* Three levels and no more: the instruction, the consequence, the record.
  Mono is for the fact row only, a date set in mono inside a sentence is the
  thing that made these cards read as noise. */
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
/* Not struck through: the day still governs the legal outcome, it is only
  behind us. */
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
