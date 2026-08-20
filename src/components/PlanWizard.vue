<template>
  <section class="wizard" :aria-label="`Plan für ${vorhaben}`">
    <ol class="steps" aria-label="Fortschritt">
      <li
        v-for="n in stepCount"
        :key="n"
        :class="{ on: n <= shownStep }"
        :aria-current="n === shownStep ? 'step' : undefined"
      >
        <span class="sr">Schritt {{ n }} von {{ stepCount }}</span>
      </li>
    </ol>

    <div v-show="step === 1" ref="pane1" class="pane" tabindex="-1">
      <h2>Wann und wo?</h2>
      <div class="fields">
        <div class="field">
          <label :for="dateId">{{ anchorLabel }}</label>
          <input
            :id="dateId"
            v-model="anchorDate"
            type="date"
            :min="minDate"
            :max="maxDate"
          />
        </div>
        <div v-if="variants.length > 1" class="field">
          <span class="label">{{ variantLabel }}</span>
          <OrtPicker
            :label="ortLabel"
            :variant-label="variantLabel"
            :variants="variants"
            bundesweit-slug="bundesweit"
            @pick="pickOrt"
          />
        </div>
      </div>
      <div class="chips">
        <button
          v-for="p in presets"
          :key="p.label"
          type="button"
          class="chip"
          :aria-pressed="anchorDate === p.iso()"
          @click="anchorDate = p.iso()"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="nav">
        <button type="button" class="btn-primary" @click="go(hasFacets ? 2 : 3)">
          Weiter
        </button>
      </div>
    </div>

    <div v-show="step === 2" ref="pane2" class="pane" tabindex="-1">
      <h2>Was trifft auf dich zu?</h2>
      <p class="lede">
        Nichts davon ist Pflicht. Was du stehen lässt, bleibt auf der
        Standardannahme, und Weiter überspringt die Frage.
      </p>
      <ul class="questions">
        <li v-for="f in facetOptions" :key="f">
          <label class="chip">
            <input v-model="activeFacets" type="checkbox" :value="f" />
            {{ facetLabel(f) }}
          </label>
        </li>
      </ul>
      <div class="nav">
        <button type="button" class="btn-tertiary" @click="back">Zurück</button>
        <button type="button" class="btn-primary" @click="go(3)">Weiter</button>
      </div>
    </div>

    <div v-show="step === 3" ref="pane3" class="pane" tabindex="-1">
      <h2>Dein Plan</h2>
      <dl class="stats">
        <div>
          <dt class="t-label">Zeitraum</dt>
          <dd class="t-title">{{ summary.span }}</dd>
        </div>
        <div>
          <dt class="t-label">Fristen</dt>
          <dd class="t-title tnum">{{ summary.count }}</dd>
        </div>
        <div>
          <dt class="t-label">Erste Frist</dt>
          <dd class="t-title tnum">{{ summary.first }}</dd>
        </div>
        <div>
          <dt class="t-label">Mit Amtstermin</dt>
          <dd class="t-title tnum">{{ summary.office }}</dd>
        </div>
      </dl>
      <div class="nav">
        <button type="button" class="btn-tertiary" @click="back">Zurück</button>
        <a class="btn-primary" :href="href">Plan öffnen</a>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from "vue";
import OrtPicker from "./deadline-planner/OrtPicker.vue";
import { FACET_LABELS, appliesTo, facetLabel, facetsUsedBy } from "../../lib/facets";
import { computeSchedule } from "../../lib/deadline-plan";
import { daysUntil, shortDate, spanParts } from "../../lib/date-display";
import { planHref } from "../../lib/plan-url";
import { addDays, isoOf, utcDay } from "../../lib/timeline-geometry";
import type { Gemeinde } from "../../lib/gemeinde-search";
import type { PlanVariant } from "./deadline-planner/types";

const props = defineProps<{
  slug: string;
  vorhaben: string;
  anchorLabel: string;
  variantLabel: string;
  variantPreposition?: string;
  variants: PlanVariant[];
  defaultSlug?: string;
}>();

const BUNDESWEIT = "bundesweit";
const dateId = useId();

const TODAY = utcDay(new Date());
const minDate = isoOf(addDays(TODAY, -14));
const maxDate = isoOf(addDays(TODAY, 365));

function endOfMonthFromNow(n: number): string {
  const d = new Date(TODAY);
  d.setUTCMonth(d.getUTCMonth() + n + 1, 0);
  return isoOf(d);
}
function firstOfMonthFromNow(n: number): string {
  const d = new Date(TODAY);
  d.setUTCMonth(d.getUTCMonth() + n, 1);
  return isoOf(d);
}
// Three months out, so the first thing anybody sees is a plan they can still
// keep and not a Frist that already passed.
const presets = [
  { label: "In 3 Monaten", iso: () => isoOf(addDays(TODAY, 90)) },
  { label: "Zum Monatsende", iso: () => endOfMonthFromNow(0) },
  { label: "Nächster Monatserste", iso: () => firstOfMonthFromNow(1) },
];

// Everything the wizard knows sits in the fragment, so a refresh lands on the
// same step with the same answers and every crawler still sees one address.
const url = () =>
  new URLSearchParams(
    typeof window === "undefined"
      ? ""
      : window.location.hash.replace(/^#/, ""),
  );
const initial = url();

const anchorDate = ref(initial.get("date") || presets[0].iso());
const selectedSlug = ref(
  pickVariant(initial.get("variant") ?? props.defaultSlug),
);
const ortName = ref(initial.get("ort") ?? "");
const region = ref(initial.get("region") ?? "");
const activeFacets = ref(
  (initial.get("facets") ?? "").split(",").filter((f) => f in FACET_LABELS),
);

// A Vorhaben without questions has no second step, so the plan is two steps
// and the address can never point at a pane that would render empty.
function clampStep(n: number): number {
  if (n === 3) return 3;
  if (n === 2) return hasFacets.value ? 2 : 3;
  return 1;
}
function pickVariant(slug: string | null | undefined): string {
  return slug && props.variants.some((v) => v.slug === slug)
    ? slug
    : BUNDESWEIT;
}

const selected = computed(
  () =>
    props.variants.find((v) => v.slug === selectedSlug.value) ??
    props.variants[0],
);
const ortLabel = computed(
  () => ortName.value || selected.value?.label || "ganz Deutschland",
);
const facetOptions = computed(() => facetsUsedBy(selected.value?.deadlines ?? []));
const hasFacets = computed(() => facetOptions.value.length > 0);

const step = ref(clampStep(Number(initial.get("schritt"))));
const stepCount = computed(() => (hasFacets.value ? 3 : 2));
// What the dots count, which is not the pane number once step 2 is gone.
const shownStep = computed(() =>
  hasFacets.value ? step.value : step.value === 1 ? 1 : 2,
);

function pickOrt(g: Gemeinde | null) {
  const own = props.variants.find((v) => v.label === g?.name);
  selectedSlug.value = own?.slug ?? BUNDESWEIT;
  ortName.value = own ? "" : (g?.name ?? "");
  region.value = own ? "" : (g?.state ?? "");
}

const params = computed(() => ({
  date: anchorDate.value,
  variant: selectedSlug.value === BUNDESWEIT ? null : selectedSlug.value,
  region: region.value || null,
  ort: ortName.value || null,
  facets: activeFacets.value.length > 0 ? activeFacets.value.join(",") : null,
}));

const href = computed(() => planHref(props.slug, params.value));

const schedule = computed(() => {
  const v = selected.value;
  if (!v) return [];
  return computeSchedule(
    anchorDate.value,
    v.deadlines.filter((d) => appliesTo(d, activeFacets.value)),
    "DE",
    v.regionCode || region.value || undefined,
  );
});

const summary = computed(() => {
  const dated = schedule.value
    .filter((e) => e.date !== null)
    .sort((a, b) => a.date!.localeCompare(b.date!));
  const office = schedule.value.filter((e) => e.needs_office).length;
  // The plan page says every date. Here the numbers say how big the plan is,
  // and only the first Frist gets a day, because that one is the appointment
  // somebody has to make now.
  const days =
    dated.length > 0
      ? daysUntil(dated[dated.length - 1].date!, dated[0].date!)
      : 0;
  const span = spanParts(days);
  return {
    span: dated.length > 0 ? `${span.n} ${span.unit}` : "—",
    count: String(schedule.value.length),
    first: dated.length > 0 ? shortDate(dated[0].date!) : "—",
    office: String(office),
  };
});

/* ---------- steps ---------- */

const pane1 = ref<HTMLElement>();
const pane2 = ref<HTMLElement>();
const pane3 = ref<HTMLElement>();

// pushState, so Zurück walks back through the wizard instead of leaving the
// page. Answers use replaceState: editing a date is not a step.
function writeUrl(push: boolean) {
  if (typeof window === "undefined") return;
  const next = new URLSearchParams();
  for (const [key, value] of Object.entries(params.value))
    if (value) next.set(key, value);
  if (step.value > 1) next.set("schritt", String(step.value));
  const fragment = next.toString();
  const to = fragment ? `${location.pathname}#${fragment}` : location.pathname;
  if (push) history.pushState({ schritt: step.value }, "", to);
  else history.replaceState({ schritt: step.value }, "", to);
}

function go(n: number) {
  step.value = clampStep(n);
  writeUrl(true);
  focusPane();
}

// A step, not history.back(): somebody who arrived on step 2 by link has no
// previous step to pop, and the browser would take them off the page.
function back() {
  go(step.value === 3 && hasFacets.value ? 2 : 1);
}

function focusPane() {
  nextTick(() => {
    const pane = [pane1, pane2, pane3][step.value - 1];
    pane.value?.focus();
  });
}

function onPop() {
  step.value = clampStep(Number(url().get("schritt")));
  focusPane();
}

watch(params, () => writeUrl(false), { deep: true });
// No write on arrival: an untouched Vorhaben-Seite keeps the clean address a
// crawler and a shared link should see.
onMounted(() => window.addEventListener("popstate", onPop));
onUnmounted(() => window.removeEventListener("popstate", onPop));
</script>

<style scoped>
.wizard {
  margin: var(--s-3) 0 var(--section-gap);
  padding: var(--s-3);
  border-radius: var(--r-lg);
  background: var(--paper-raised);
  box-shadow: var(--shadow-card);
}
h2 {
  margin-top: 0;
}
.lede {
  color: var(--muted);
  font-size: var(--t-meta);
}

.steps {
  display: flex;
  gap: var(--s-1);
  margin: 0 0 var(--s-2);
  padding: 0;
  list-style: none;
}
.steps li {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: var(--r-sm);
  background: color-mix(in srgb, var(--ink) 18%, var(--paper-raised));
}
.steps li.on {
  background: var(--accent);
}
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.pane:focus {
  outline: none;
}

.fields {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.field {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  min-width: 0;
}
.field label,
.field .label {
  font-size: var(--t-meta);
  color: var(--muted);
}

.chips,
.questions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
  margin: var(--s-2) 0 0;
  padding: 0;
  list-style: none;
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: var(--s-2);
  margin: 0;
}
.stats dd {
  margin: 0;
}

.nav {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
</style>
