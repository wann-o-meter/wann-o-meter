<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, CalendarDays } from "lucide-vue-next";
import { computeSchedule } from "../../lib/deadline-plan";
import { formatDate } from "../../lib/format-date";
import { isPast } from "../../lib/today";
import { STATES } from "../../lib/states";
import type { Deadline } from "../../lib/deadline-plan";

const props = defineProps<{
  task: Deadline;
  anchorLabel: string;
  planSlug?: string;
  planLabel?: string;
}>();

const anchorDate = ref("");

// Everything is worked out here, in the browser. The page around this island is
// about the rule, which does not go stale, and never about a date.
const result = computed(() => {
  if (!anchorDate.value) return null;
  const [entry] = computeSchedule(anchorDate.value, [props.task], "DE");
  return entry?.date ? entry : null;
});

const late = computed(() => !!result.value && isPast(result.value.date!));

// Feiertage are Landesrecht, so the bundesweit answer is not everyone's answer.
// Rather than warn about that on every page, work out whether it is true for
// the date actually entered: run the same sum for all sixteen Bundesländer and
// see which ones land somewhere else.
const differing = computed(() => {
  const here = result.value?.date;
  if (!here) return [];
  return Object.entries(STATES)
    .filter(([code]) => {
      const [entry] = computeSchedule(anchorDate.value, [props.task], "DE", code);
      return !!entry?.date && entry.date !== here;
    })
    .map(([, name]) => name);
});

const differingLabel = computed(() => {
  const names = differing.value;
  if (names.length > 3) return `${names.length} Bundesländern`;
  return names.length > 1
    ? `${names.slice(0, -1).join(", ")} und ${names[names.length - 1]}`
    : names[0];
});
const inputId = `frist-anchor-${props.task.id}`;
</script>

<template>
  <div class="rechner">
    <label :for="inputId">{{ anchorLabel }}</label>
    <input :id="inputId" v-model="anchorDate" type="date" />

    <p v-if="!result" class="empty">
      <CalendarDays :size="16" aria-hidden="true" />
      Datum eintragen, dann steht hier die Frist.
    </p>
    <template v-else>
      <p class="out">
        <span class="k">{{
          task.direction === "before" ? "Erledigt bis" : "Frist endet am"
        }}</span>
        <span class="v" :class="{ late }">{{
          formatDate(result.date!)
        }}</span>
      </p>
      <p v-if="late" class="warn">Dieser Termin liegt schon in der Vergangenheit.</p>
      <p v-if="differing.length" class="hint">
        Gerechnet mit den bundesweiten Feiertagen. In {{ differingLabel }} liegt
        ein Feiertag dazwischen, dort gilt ein anderer Tag.
      </p>
      <a
        v-if="planSlug"
        class="cta"
        :href="`/${planSlug}/?date=${anchorDate}`"
      >
        {{ planLabel ?? "Plan" }} ab diesem Termin planen
        <ArrowRight :size="16" />
      </a>
      <details v-if="result.derivation?.length" class="steps">
        <summary>Wie wird das gerechnet?</summary>
        <ol>
          <li v-for="step in result.derivation" :key="step.step">
            {{ step.label }}
          </li>
        </ol>
      </details>
    </template>
  </div>
</template>

<style scoped>
.rechner {
  max-width: 32rem;
  margin: 1.5rem 0;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper-raised);
}
label {
  display: block;
  margin-bottom: 0.25rem;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
input {
  width: 100%;
  max-width: 11rem;
  padding: 0.5rem 0.75rem;
  font-size: var(--fs-md);
}
/* The island always says something, even before it has a date to work with. */
.empty {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0.9rem 0 0;
  color: var(--muted);
  font-size: var(--fs-sm);
}
.out {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.2rem 0.6rem;
  margin: 0.9rem 0 0;
}
.k {
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.v {
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--accent);
}
.v.late {
  color: var(--warn);
}
.warn {
  margin: 0.3rem 0 0;
  color: var(--warn);
  font-size: var(--fs-sm);
}
/* Only ever rendered when a Bundesland really does land on another day. */
.hint {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: var(--fs-sm);
}
.cta {
  margin-top: 1rem;
  font-size: var(--fs-sm);
  padding: 0.45rem 0.9rem;
}
.steps {
  margin-top: 0.7rem;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.steps summary {
  cursor: pointer;
  padding: 0.3rem 0;
}
.steps ol {
  margin: 0.3rem 0 0;
  padding-left: 1.2rem;
}
</style>
