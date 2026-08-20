<template>
  <article class="plan">
    <p class="who t-title">{{ who }}</p>

    <p class="event">
      <span class="t-label">{{ v.anchorLabel }}</span>
      <span class="t-meta tnum">{{ shortDate(plan.date) }}</span>
    </p>

    <h2 v-if="!next" class="t-title">Alle Fristen erledigt</h2>
    <h2 v-else-if="span!.days < 0" class="t-title late">
      <AlertTriangle :size="18" aria-hidden="true" />
      Nächste Frist {{ span!.n }} {{ span!.unit }} überfällig
    </h2>
    <h2 v-else-if="span!.days === 0" class="t-title">
      Nächste Frist heute fällig
    </h2>
    <h2 v-else class="t-title">
      Nächste Frist in {{ span!.n }} {{ dativeUnit(span!.unit) }}
    </h2>

    <p v-if="next" class="next t-meta">
      {{ next.label }} · bis <span class="tnum">{{ shortDate(next.date!) }}</span>
    </p>

    <p v-if="doneCount > 0" class="tally t-meta">
      {{ doneCount }} von {{ total }} Fristen erledigt.
    </p>

    <p class="go">
      <a class="btn-secondary" :href="href">Plan öffnen <ArrowRight :size="14" /></a>
    </p>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, ArrowRight } from "lucide-vue-next";
import { computeSchedule } from "../../lib/deadline-plan";
import { appliesTo } from "../../lib/facets";
import {
  dativeUnit,
  daysUntil,
  shortDate,
  spanParts,
} from "../../lib/date-display";
import {
  planStorageKey,
  readSnapshot,
  snapshotDeadlines,
} from "../../lib/saved-plans";
import { STATES } from "../../lib/states";
import { isoToday } from "../../lib/today";
import type { SavedPlan } from "../../lib/saved-plans";
import type { VorhabenData } from "../../lib/vorhaben-data";

const props = defineProps<{
  plan: SavedPlan;
  v: VorhabenData;
}>();

defineEmits<{ (e: "forget", slug: string): void }>();

const TODAY = isoToday();

const variant = computed(
  () =>
    props.v.variants.find((x) => x.slug === props.plan.variant) ??
    props.v.variants[0],
);
const local = computed(() => variant.value.slug !== "bundesweit");
// Without a local variant the Ort is only known if the visitor picked one,
// otherwise the Bundesland is all the plan says about the place.
const place = computed(() =>
  local.value
    ? variant.value.label
    : (props.plan.ort ?? STATES[props.plan.region ?? ""] ?? ""),
);

const who = computed(() =>
  [props.v.label, place.value].filter(Boolean).join(" · "),
);

const snap = computed(() =>
  readSnapshot(planStorageKey(props.v.vorhaben, variant.value.slug)),
);
// Same facets and edits the plan page applies, otherwise the counts disagree.
const entries = computed(() =>
  computeSchedule(
    props.plan.date,
    snapshotDeadlines(
      variant.value.deadlines.filter((d) => appliesTo(d, props.plan.facets)),
      snap.value,
    ),
    "DE",
    variant.value.regionCode ?? props.plan.region,
  ).filter((e) => e.date !== null),
);

const total = computed(() => entries.value.length);
const doneCount = computed(
  () => entries.value.filter((e) => snap.value.done[e.id]).length,
);
const next = computed(
  () => entries.value.find((e) => !snap.value.done[e.id]) ?? null,
);

// The countdown belongs to the next Frist: the Termin itself never goes wrong.
const span = computed(() => {
  if (!next.value?.date) return null;
  const days = daysUntil(next.value.date, TODAY);
  return { days, ...spanParts(days) };
});

// An Ort with its own file brings its Bundesland along, region is only for the
// bundesweit plan of a place we have no file for.
const href = computed(() =>
  local.value
    ? `/${props.v.slug}/${variant.value.slug}/#date=${props.plan.date}`
    : `/${props.v.slug}/#date=${props.plan.date}` +
      (props.plan.region ? `&region=${props.plan.region}` : "") +
      (props.plan.ort ? `&ort=${encodeURIComponent(props.plan.ort)}` : ""),
);
</script>

<style scoped>
/* One card shape, one elevation, and the same height as its neighbours. */
.plan {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.15rem;
  height: 100%;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-left: 3px solid var(--accent);
  border-radius: var(--r-lg);
  padding: var(--s-2);
  /* Frist labels are long compound nouns, they have to be allowed to break. */
  overflow-wrap: anywhere;
}
.who {
  margin: 0;
  color: var(--muted);
}
.event {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0 0 var(--s-1);
}
h2 {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin: 0;
  border: 0;
  padding: 0;
}
h2.late {
  color: var(--overdue);
}
.next {
  margin: 0;
}
.tally {
  margin: 0.2rem 0 0;
  color: var(--muted);
}
/* Pushed to the bottom, so cards of different length end on one line. */
.go {
  margin: auto 0 0;
  padding-top: var(--s-2);
}
</style>
