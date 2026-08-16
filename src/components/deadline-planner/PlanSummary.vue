<script setup lang="ts">
import { computed } from "vue";
import { shortDate } from "../../../lib/date-display";
import { toDate } from "../../../lib/format-date";
import { isPast } from "../../../lib/today";
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

const nextOpen = computed(() => {
  const upcoming = dated.value.filter((e) => !isPast(e.date!));
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
  <div class="summary">
    <div class="stats">
      <div class="stat">
        <span class="row">
          <span class="k">Erledigt</span>
          <span class="v">{{ doneCount }}/{{ total }}</span>
        </span>
        <span class="bar" aria-hidden="true">
          <i :style="{ width: pct + '%' }"></i>
        </span>
      </div>

      <a
        v-if="catchUp"
        class="stat late"
        :href="`#task-${catchUp.id}`"
        @click.prevent="$emit('select', catchUp!.id)"
      >
        <span class="row">
          <span class="k">{{ overdue.length }} verstrichen</span>
          <span class="v">bis {{ shortDate(catchUp.date) }}</span>
        </span>
      </a>

      <p v-else-if="overdue.length > 0" class="stat late">
        <span class="row">
          <span class="k">{{ overdue.length }} verstrichen</span>
          <span class="v">vorbei</span>
        </span>
      </p>

      <a
        v-else-if="nextOpen"
        class="stat"
        :href="`#task-${nextOpen.id}`"
        @click.prevent="$emit('select', nextOpen!.id)"
      >
        <span class="row">
          <span class="k">Nächste Frist</span>
          <span class="v">{{ shortDate(nextOpen.date) }}</span>
        </span>
      </a>

      <p v-else class="stat done">
        <span class="row">
          <span class="k">Fertig</span>
          <span class="v">{{ total }}/{{ total }}</span>
        </span>
      </p>
    </div>

    <p v-if="anchorIsSunday" class="sunday">
      {{ anchorLabel }} ist ein Sonntag - Ämter und Übergaben brauchen einen
      Werktag.
    </p>
  </div>
</template>

<style scoped>
.summary {
  margin: 0.6rem 0 0.2rem;
}
.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.stat {
  display: flex;
  /* Side by side even on the narrowest phone: two short facts, one row. */
  flex: 1 1 0;
  flex-direction: column;
  justify-content: center;
  gap: 0.3rem;
  min-width: 0;
  margin: 0;
  padding: 0.45rem 0.6rem;
  background: var(--paper);
  border-radius: var(--radius-sm);
  color: var(--ink);
  text-decoration: none;
  transition:
    padding 0.22s,
    background 0.12s;
}
a.stat:hover {
  background: color-mix(in srgb, var(--accent) 10%, var(--paper));
}
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0 0.6rem;
  min-width: 0;
}
.k {
  overflow: hidden;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.v {
  flex-shrink: 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  white-space: nowrap;
}
.late .k {
  color: var(--warn);
}
.done .k {
  color: var(--muted);
}

.bar {
  display: block;
  height: 0.3rem;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--ink) 14%, var(--paper));
  overflow: hidden;
}
.bar i {
  display: block;
  height: 100%;
  border-radius: var(--radius-pill);
  background: var(--accent);
  transition: width 0.3s;
}

.sunday {
  display: block;
  overflow: hidden;
  max-height: 3rem;
  margin: 0.4rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
  transition:
    max-height 0.22s,
    opacity 0.22s;
}

.compact .stat {
  padding: 0.3rem 0.5rem;
}
.compact .sunday {
  max-height: 0;
  opacity: 0;
  margin: 0;
}
</style>
