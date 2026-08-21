<script setup lang="ts">
import { computed } from "vue";
import { daysUntil, dativeUnit, spanParts } from "../../../lib/date-display";
import { toDate } from "../../../lib/format-date";
import { isPast, isoToday } from "../../../lib/today";
import type { ScheduleEntry } from "../../../lib/deadline-plan";

const props = defineProps<{
  entries: ScheduleEntry[];
  doneIds: Record<string, boolean>;
  anchorDate: string;
  anchorLabel: string;
}>();

defineEmits<{ (e: "select", id: string): void }>();

const open = computed(() => props.entries.filter((e) => !props.doneIds[e.id]));
// Only a real Frist can be overdue or next, a soft step has no date to miss.
const dated = computed(() => open.value.filter((e) => e.kind !== "soft"));
const overdue = computed(() => dated.value.filter((e) => isPast(e.date!)));
const total = computed(() => props.entries.length);
const doneCount = computed(() => total.value - open.value.length);
const pct = computed(() =>
  total.value === 0 ? 0 : Math.round((doneCount.value / total.value) * 100),
);

// The list below owns every date on this page, so the status says how far away
// the next one is and lets the row itself say which day that is.
const nextOpen = computed(() => {
  const upcoming = dated.value.filter((e) => !isPast(e.date!));
  if (upcoming.length === 0) return null;
  const next = upcoming.reduce((a, b) => (a.date! <= b.date! ? a : b));
  const days = daysUntil(next.date!, isoToday());
  if (days === 0) return { id: next.id, when: "heute" };
  const span = spanParts(days);
  return { id: next.id, when: `in ${span.n} ${dativeUnit(span.unit)}` };
});

const anchorIsSunday = computed(
  () => toDate(props.anchorDate).getUTCDay() === 0,
);
</script>

<template>
  <div class="summary">
    <div class="stats">
      <div class="stat">
        <span class="t-label">Erledigt</span>
        <span class="t-title tnum">{{ doneCount }}/{{ total }}</span>
        <span class="bar" aria-hidden="true">
          <i :style="{ width: pct + '%' }"></i>
        </span>
      </div>

      <p v-if="overdue.length > 0" class="stat late">
        <span class="t-label">Verstrichen</span>
        <span class="t-title tnum">
          {{ overdue.length }} {{ overdue.length === 1 ? "Aufgabe" : "Aufgaben" }}
        </span>
      </p>

      <button
        v-else-if="nextOpen"
        type="button"
        class="stat"
        @click="$emit('select', nextOpen!.id)"
      >
        <span class="t-label">Nächste Frist</span>
        <span class="t-title">{{ nextOpen.when }}</span>
      </button>

      <p v-else class="stat">
        <span class="t-label">Fertig</span>
        <span class="t-title tnum">{{ total }}/{{ total }}</span>
      </p>
    </div>

    <p v-if="anchorIsSunday" class="sunday t-meta">
      {{ anchorLabel }} ist ein Sonntag - Ämter und Übergaben brauchen einen
      Werktag.
    </p>
  </div>
</template>

<style scoped>
/* Plain: two facts on the page itself, no container to look at. */
.summary {
  margin: var(--s-2) 0;
}
.stats {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1) var(--s-4);
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
  background: none;
  color: var(--ink);
  text-align: left;
}
button.stat {
  cursor: pointer;
}
button.stat:hover .t-title {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
.late .t-title {
  color: var(--overdue);
}

.bar {
  display: block;
  height: 0.25rem;
  width: 100%;
  min-width: 8rem;
  margin-top: 0.15rem;
  border-radius: var(--r-sm);
  background: color-mix(in srgb, var(--ink) 12%, transparent);
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}

.sunday {
  overflow: hidden;
  max-height: 3rem;
  margin: var(--s-1) 0 0;
  color: var(--muted);
  transition:
    max-height 0.22s,
    opacity 0.22s;
}
.compact .sunday {
  max-height: 0;
  opacity: 0;
  margin: 0;
}
</style>
