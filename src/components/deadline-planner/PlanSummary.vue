<script setup lang="ts">
import { computed } from "vue";
import { shortDate } from "../../../lib/date-display";
import { toDate } from "../../../lib/format-date";
import { isPast } from "../../../lib/today";
import type { ScheduleEntry } from "../../../lib/deadline-plan";

const props = defineProps<{
  entries: ScheduleEntry[];
  taskCount: number;
  doneIds: Record<string, boolean>;
  anchorDate: string;
  anchorLabel: string;
}>();

defineEmits<{ (e: "select", id: string): void }>();

const open = computed(() => props.entries.filter((e) => !props.doneIds[e.id]));
const overdue = computed(() => open.value.filter((e) => isPast(e.date!)));
const openCount = computed(() => open.value.length - overdue.value.length);

const nextOpen = computed(() => {
  const upcoming = open.value.filter((e) => !isPast(e.date!));
  if (upcoming.length === 0) return null;
  const next = upcoming.reduce((a, b) => (a.date! <= b.date! ? a : b));
  return { id: next.id, label: next.label, date: next.date! };
});

const catchUp = computed(() => {
  const withRescue = overdue.value.filter((e) => e.rescue);
  if (withRescue.length === 0) return null;
  const first = withRescue.reduce((a, b) =>
    a.rescue!.date <= b.rescue!.date ? a : b,
  );
  return { id: first.id, date: first.rescue!.date };
});

const anchorIsSunday = computed(
  () => toDate(props.anchorDate).getUTCDay() === 0,
);
</script>

<template>
  <p class="summary">
    <template v-if="overdue.length > 0">
      <strong class="late">Du bist spät dran.</strong>
      {{ overdue.length }}
      {{ overdue.length === 1 ? "Frist" : "Fristen" }} verstrichen,
      {{ openCount }} offen.
      <template v-if="catchUp">
        Nachholen bis
        <a
          :href="`#task-${catchUp.id}`"
          @click.prevent="$emit('select', catchUp!.id)"
          >{{ shortDate(catchUp.date) }}</a
        >.
      </template>
    </template>
    <template v-else-if="nextOpen">
      {{ taskCount }} Aufgaben, {{ openCount }} noch offen. Die nächste Frist
      ist am
      <a
        :href="`#task-${nextOpen.id}`"
        @click.prevent="$emit('select', nextOpen!.id)"
        >{{ shortDate(nextOpen.date) }}</a
      >: {{ nextOpen.label }}.
    </template>
    <template v-else>Alle Aufgaben sind erledigt.</template>
    <span v-if="anchorIsSunday" class="sunday">
      {{ anchorLabel }} ist ein Sonntag - Ämter und Übergaben brauchen einen
      Werktag.
    </span>
  </p>
</template>

<style scoped>
.summary {
  margin: 0.6rem 0 0.4rem;
  font-size: var(--fs-md);
  transition:
    font-size 0.22s,
    margin 0.22s;
}
.summary a {
  color: var(--accent);
}
.late {
  color: var(--warn);
}
.sunday {
  display: block;
  overflow: hidden;
  max-height: 3rem;
  font-size: var(--fs-sm);
  color: var(--muted);
  transition:
    max-height 0.22s,
    opacity 0.22s;
}
.compact .summary {
  margin: 0.3rem 0 0.2rem;
  font-size: var(--fs-sm);
}
.compact .sunday {
  max-height: 0;
  opacity: 0;
}
</style>
