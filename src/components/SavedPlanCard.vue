<template>
  <article class="plan">
    <p class="meta">
      {{ v.possessive }} {{ v.label }}
      <template v-if="place"> · {{ place }}</template> ·
      <span class="mono">{{ shortDate(plan.date) }}</span>
    </p>

    <h2 v-if="!next">Alle Fristen erledigt</h2>
    <h2 v-else-if="span!.days < 0" class="late">
      <AlertTriangle :size="20" aria-hidden="true" />
      <span><span class="mono">{{ span!.n }}</span> {{ span!.unit }} überfällig</span>
    </h2>
    <h2 v-else-if="span!.days === 0">Nächste Frist heute</h2>
    <h2 v-else>
      Nächste Frist in <span class="mono">{{ span!.n }}</span> {{ span!.unit }}
    </h2>

    <div v-if="next" class="next">
      <p class="t">Als Nächstes: {{ next.label }}</p>
      <p class="dt">
        bis <b class="mono">{{ shortDate(next.date!) }}</b>
      </p>
      <p v-if="next.rescue" class="rescue">
        Ausweg: kündigen bis
        <b class="mono">{{ shortDate(next.rescue.date) }}</b
        >. {{ next.rescue.label }}.
      </p>
    </div>

    <div v-if="doneCount > 0" class="bar" aria-hidden="true">
      <i :style="{ width: pct + '%' }"></i>
    </div>
    <p class="tally">
      <span class="mono">{{ doneCount }}</span> von
      <span class="mono">{{ total }}</span> Fristen erledigt
    </p>

    <p class="links">
      <a :href="href">{{ v.label }} bearbeiten</a>
      <button type="button" @click="exportIcs">Als Kalender exportieren</button>
      <button type="button" class="remove" @click="$emit('forget', plan.slug)">
        Entfernen
      </button>
    </p>
    <p class="storage">
      Nur in diesem Browser gespeichert, ohne Konto. In einem anderen Browser
      oder nach dem Löschen der Websitedaten ist der Plan weg.
    </p>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle } from "lucide-vue-next";
import { computeSchedule } from "../../lib/deadline-plan";
import { appliesTo } from "../../lib/facets";
import { daysUntil, shortDate, spanParts } from "../../lib/date-display";
import { downloadIcs } from "../../lib/ics-download";
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
// Without a local variant only the Bundesland of the plan is known, not its Ort.
const place = computed(() =>
  local.value ? variant.value.label : (STATES[props.plan.region ?? ""] ?? ""),
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
const pct = computed(() =>
  total.value === 0 ? 0 : Math.round((doneCount.value / total.value) * 100),
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

const href = computed(
  () =>
    `/${props.v.slug}/${local.value ? `${variant.value.slug}/` : ""}?date=${props.plan.date}` +
    (props.plan.region ? `&region=${props.plan.region}` : ""),
);

function exportIcs() {
  downloadIcs(
    entries.value,
    `${props.v.vorhaben} - ${place.value || "Bundesweit"}`,
    props.v.slug,
    props.plan.date,
  );
}
</script>

<style scoped>
.plan {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-left: 3px solid var(--anchor);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  padding: 1.2rem 1.4rem;
  margin-bottom: 1rem;
}
.meta {
  margin: 0 0 0.2rem;
  font-size: var(--fs-sm);
  color: var(--muted);
}
h2 {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0 0 0.9rem;
  border: 0;
  padding: 0;
  font-size: var(--fs-lg);
}
h2.late {
  color: var(--warn);
}
/* Monospace marks hard dates and every derived number. */
.mono {
  font-family: var(--font-mono);
}

.next {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  border-radius: var(--radius-sm);
  padding: 0.7rem 0.9rem;
}
.next .t {
  margin: 0;
  font-weight: 600;
}
.next .dt {
  margin: 0.15rem 0 0;
  font-size: var(--fs-sm);
}
.rescue {
  margin: 0.4rem 0 0;
  font-size: var(--fs-sm);
}

.bar {
  height: 0.35rem;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--ink) 14%, var(--paper));
  overflow: hidden;
  margin-top: 0.9rem;
}
.bar i {
  display: block;
  height: 100%;
  background: var(--done-color);
}
.tally {
  margin: 0.4rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}

.links {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 1.1rem;
  margin: 0.9rem 0 0;
  font-size: var(--fs-sm);
}
.links button {
  border: 0;
  background: none;
  padding: 0;
  color: var(--accent);
  font-size: inherit;
  text-decoration: underline;
  cursor: pointer;
}
/* Destructive action sits apart from the two everyday ones. */
.links .remove {
  margin-left: auto;
  color: var(--muted);
  font-size: var(--fs-xs);
  text-decoration: none;
}
.links .remove:hover {
  color: var(--warn);
  text-decoration: underline;
}
.storage {
  margin: 0.6rem 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
</style>
