<template>
  <div class="wom-start">
    <TransitionGroup name="plan" tag="div" class="plans" appear>
      <SavedPlanCard
        v-for="card in planCards"
        :key="card.plan.slug"
        :plan="card.plan"
        :v="card.v"
        @forget="savedPlans = forgetPlan($event)"
      />
    </TransitionGroup>

    <section class="intro">
      <h1 v-if="planCards.length === 0">
        Die Checkliste, die deine Termine kennt.
      </h1>
      <p class="lede">
        Wann-O-Meter rechnet jede Frist rückwärts von deinem Termin: mit dem
        Datum, bis wann sie erledigt sein muss, <strong>mit Paragraf</strong>,
        und mit den Feiertagen deines Bundeslands schon eingerechnet.
      </p>
    </section>

    <section class="step">
      <h2 class="q" id="q1">
        {{
          planCards.length > 0
            ? "Noch etwas planen?"
            : "Was möchtest du planen?"
        }}
      </h2>
      <div class="choices" role="group" aria-labelledby="q1">
        <button
          v-for="v in vorhaben"
          :key="v.slug"
          type="button"
          class="choice key"
          :aria-pressed="v.slug === selectedSlug"
          @click="pick(v.slug)"
        >
          {{ v.label }}<small>{{ v.teaser }}</small>
        </button>
      </div>
    </section>

    <Transition name="reveal">
      <section v-if="selected" class="step">
        <h2 class="q">Wann und wo?</h2>
        <div class="fields">
          <div class="field">
            <label for="anchor">{{ selected.anchorLabel }}</label>
            <input
              id="anchor"
              type="date"
              :value="anchorDate"
              :min="minDate"
              :max="maxDate"
              @change="anchorDate = ($event.target as HTMLInputElement).value"
            />
          </div>
          <div class="field ac">
            <label for="ort">Ort</label>
            <div class="ac-input" :class="{ picked: ort }">
              <Search v-if="!ort" :size="16" aria-hidden="true" />
              <Check v-else :size="16" class="ok" aria-hidden="true" />
              <input
                id="ort"
                v-model="ortQuery"
                type="text"
                autocomplete="off"
                placeholder="Gemeinde suchen und auswählen"
                role="combobox"
                aria-controls="aclist"
                :aria-expanded="suggestions.length > 0"
                @input="ort = null"
                @blur="closeSuggestions"
                @keydown.esc="closeSuggestions"
              />
            </div>
            <Transition name="drop">
              <ul v-if="suggestions.length > 0" id="aclist" role="listbox">
                <li
                  v-for="g in suggestions"
                  :key="g.name"
                  role="option"
                  :aria-selected="g.name === ort?.name"
                  @mousedown.prevent="chooseOrt(g)"
                >
                  <span>{{ g.name }}</span>
                  <span v-if="variantFor(g)" class="tag covered">
                    <Check :size="13" aria-hidden="true" /> örtliche Fristen
                    hinterlegt
                  </span>
                  <span v-else class="tag">{{ stateName(g) }}</span>
                </li>
              </ul>
            </Transition>
          </div>
        </div>

        <div class="chips">
          <button
            v-for="p in presets"
            :key="p.label"
            type="button"
            class="chip key"
            :aria-pressed="anchorDate === p.iso()"
            @click="anchorDate = p.iso()"
          >
            {{ p.label }}
          </button>
        </div>

        <p v-if="ort" class="coverage">
          <Check v-if="localVariant" :size="15" class="ok" aria-hidden="true" />
          <Info v-else :size="15" class="thin" aria-hidden="true" />
          <span>
            <b>{{ ort.name }}: </b>
            <template v-if="localVariant">
              {{ localSteps }} sind als eigene Fristen hinterlegt, dazu die
              Feiertage in {{ stateName(ort) }}. Liegt dein Termin in den
              Schulferien, sagen wir es darunter.
            </template>
            <template v-else>
              Die Feiertage in {{ stateName(ort) }} sind eingerechnet, und liegt
              dein Termin in den Schulferien, sagen wir es darunter.
              <template v-if="hasLocalVariants">
                Örtliche Fristen wie Halteverbotszone oder Sperrmüll haben wir
                hier noch nicht, der Plan zeigt die bundesweiten Schritte.
              </template>
            </template>
          </span>
        </p>

        <p v-if="ferien" class="ferien">
          <Info :size="15" aria-hidden="true" />
          <span>
            Der <span>{{ shortDate(anchorDate) }}</span> liegt in den
            {{ ferien.name }} ({{ shortDate(ferien.from) }} bis
            {{ shortDate(ferien.to) }}).
          </span>
        </p>
      </section>
    </Transition>

    <Transition name="reveal">
      <section v-if="preview" class="step">
        <div class="card">
          <p class="eyebrow" :class="{ late: overdue }">
            <AlertTriangle v-if="overdue" :size="14" aria-hidden="true" />
            {{
              overdue ? "Diese Frist ist bereits verstrichen" : "Als Nächstes"
            }}
          </p>
          <p class="first-task">{{ preview.first.label }}</p>
          <template v-if="span">
            <p class="first-date mono" :class="{ late: overdue }">
              {{ shortDate(preview.first.date!) }}
            </p>
            <p class="countdown" :class="{ late: overdue }">
              <template v-if="overdue">
                <span>{{ span.n }}</span> {{ span.unit }} überfällig
              </template>
              <template v-else-if="span.days === 0">heute fällig</template>
              <template v-else>
                in <span>{{ span.n }}</span> {{ span.unit }}
              </template>
            </p>
          </template>
          <p v-else class="first-date">Termin erfragen</p>

          <p v-if="preview.first.rescue" class="rescue">
            <b>Ausweg:</b> kündige bis
            <b>{{ shortDate(preview.first.rescue.date) }}</b
            >. {{ preview.first.rescue.label }}. Für den
            <span>{{ shortDate(anchorDate) }}</span> als
            {{ selected!.anchorLabel }} ist die Frist nicht mehr zu halten.
          </p>

          <p v-if="basis" class="basis">
            <template v-if="basis.label"
              >Grundlage: <b>{{ basis.label }}</b
              ><template v-if="basis.rule">, </template></template
            >{{ basis.rule }}.
            <a
              v-if="basis.url"
              class="source"
              :href="basis.url"
              target="_blank"
              rel="noopener"
              >Quelle</a
            >
          </p>

          <ol class="rest">
            <li v-for="t in preview.rest" :key="t.id">
              <span>{{ t.label }}</span>
              <span v-if="t.date" class="dt mono">{{ dayMonth(t.date) }}</span>
              <span v-else class="dt none">Termin erfragen</span>
            </li>
          </ol>
          <p v-if="preview.more > 0" class="more">
            und <span>{{ preview.more }}</span> weitere Fristen im vollständigen
            Plan.
          </p>

          <p v-if="savedForSelected" class="replaces">
            Du hast schon einen Plan für {{ selected!.label }} vom
            <span>{{ shortDate(savedForSelected.date) }}</span
            >. Dieses Formular legt einen neuen an und ersetzt ihn.
          </p>

          <a class="cta" :href="planHref">
            Plan öffnen <ArrowRight :size="16" />
          </a>
          <p class="after-cta">
            Im Plan: abhaken, Aufgaben ergänzen und alles als Kalender
            exportieren.
          </p>
        </div>
      </section>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Info,
  Search,
} from "lucide-vue-next";
import gemeinden from "../../data/gemeinden.json";
import { appliesTo } from "../../lib/facets";
import {
  dayMonth,
  daysUntil,
  shortDate,
  spanParts,
} from "../../lib/date-display";
import { STATES } from "../../lib/states";
import { isoToday } from "../../lib/today";
import { addDays, isoOf, utcDay } from "../../lib/timeline-geometry";
import SavedPlanCard from "./SavedPlanCard.vue";
import { usePlannerSchedule } from "./deadline-planner/usePlannerSchedule";
import { forgetPlan, loadSavedPlans } from "../../lib/saved-plans";
import type { SavedPlan } from "../../lib/saved-plans";
import type { VorhabenData, VorhabenVariant } from "../../lib/vorhaben-data";

interface Gemeinde {
  name: string;
  state: string;
}

interface Ferien {
  from: string;
  to: string;
  name: string;
}

const props = defineProps<{
  vorhaben: VorhabenData[];
  schulferien: Record<string, Ferien[]>;
}>();

const BUNDESWEIT = "bundesweit";

const savedPlans = ref<SavedPlan[]>([]);
const planCards = computed(() =>
  savedPlans.value.flatMap((plan) => {
    const v = props.vorhaben.find((x) => x.slug === plan.slug);
    return v ? [{ plan, v }] : [];
  }),
);

const selectedSlug = ref<string | null>(null);
const selected = computed(
  () => props.vorhaben.find((v) => v.slug === selectedSlug.value) ?? null,
);
// The form always starts empty and always creates a new plan, the saved card
// above is the only place that edits one.
const savedForSelected = computed(
  () => savedPlans.value.find((p) => p.slug === selectedSlug.value) ?? null,
);

const TODAY = utcDay(new Date());
const minDate = isoOf(addDays(TODAY, -14));
const maxDate = isoOf(addDays(TODAY, 365));
const anchorDate = ref("");

function endOfMonth(n: number): string {
  const d = new Date(TODAY);
  d.setUTCMonth(d.getUTCMonth() + n + 1, 0);
  return isoOf(d);
}
function firstOfMonth(n: number): string {
  const d = new Date(TODAY);
  d.setUTCMonth(d.getUTCMonth() + n, 1);
  return isoOf(d);
}
const presets = [
  { label: "In 3 Monaten", iso: () => isoOf(addDays(TODAY, 90)) },
  { label: "Zum Monatsende", iso: () => endOfMonth(0) },
  { label: "Nächster Monatserste", iso: () => firstOfMonth(1) },
];

/* ---------- Ort ---------- */
const ortQuery = ref("");
const ort = ref<Gemeinde | null>(null);
const suggestionsOpen = ref(true);

const suggestions = computed(() => {
  const q = ortQuery.value.trim().toLowerCase();
  if (!suggestionsOpen.value || q.length < 2 || ort.value) return [];
  return gemeinden.filter((g) => g.name.toLowerCase().includes(q)).slice(0, 6);
});
function chooseOrt(g: Gemeinde) {
  ort.value = g;
  ortQuery.value = g.name;
}
function closeSuggestions() {
  suggestionsOpen.value = false;
}
watch(ortQuery, () => (suggestionsOpen.value = true));

const stateName = (g: Gemeinde) => STATES[g.state] ?? g.state;

// A Gemeinde is covered when the Vorhaben has a variant file naming it, the
// yaml `name:` is what data/gemeinden.json has to match.
function variantFor(g: Gemeinde): VorhabenVariant | undefined {
  return selected.value?.variants.find((v) => v.label === g.name);
}
const localVariant = computed(() =>
  ort.value ? variantFor(ort.value) : undefined,
);
const hasLocalVariants = computed(
  () => (selected.value?.variants.length ?? 0) > 1,
);
const baseVariant = computed(() =>
  selected.value?.variants.find((v) => v.slug === BUNDESWEIT),
);

// Name the local steps instead of promising "örtliche Schritte".
// ponytail: the first word of the label is the step's name in every Kommune
// file so far, add a short label to the schema if that ever reads wrong.
const localSteps = computed(() => {
  const base = new Set(baseVariant.value?.deadlines.map((d) => d.id) ?? []);
  const names = (localVariant.value?.deadlines ?? [])
    .filter((d) => !base.has(d.id))
    .map((d) => d.label.split(" ")[0]);
  if (names.length < 2) return names[0] ?? "Örtliche Fristen";
  return `${names.slice(0, -1).join(", ")} und ${names[names.length - 1]}`;
});

// Schulferien do not move a Frist, they only warn about the Termin itself.
const ferien = computed(() => {
  const iso = anchorDate.value;
  if (!ort.value || !iso) return null;
  return (
    (props.schulferien[ort.value.state] ?? []).find(
      (w) => w.from <= iso && iso <= w.to,
    ) ?? null
  );
});

// Without a local variant the plan is the bundesweite one, only the Feiertage
// follow the Bundesland of the Ort.
const previewVariant = computed<VorhabenVariant | undefined>(() => {
  if (!selected.value) return undefined;
  if (localVariant.value) return localVariant.value;
  const base = baseVariant.value ?? selected.value.variants[0];
  return base && ort.value ? { ...base, regionCode: ort.value.state } : base;
});

function pick(slug: string) {
  if (slug === selectedSlug.value) return;
  selectedSlug.value = slug;
}

/* ---------- preview ---------- */
const doneIds = reactive<Record<string, boolean>>({});

const workingDeadlines = computed(() =>
  (previewVariant.value?.deadlines ?? []).filter((d) => appliesTo(d, [])),
);

const { tasks } = usePlannerSchedule(
  anchorDate,
  previewVariant,
  workingDeadlines,
  () => selected.value?.anchorLabel ?? "",
  doneIds,
);

// Tasks arrive sorted by date, undated last.
const preview = computed(() => {
  if (!selected.value || !anchorDate.value || !ort.value) return null;
  const [first, ...others] = tasks.value;
  if (!first) return null;
  return {
    first,
    rest: others.slice(0, 3),
    more: Math.max(0, others.length - 3),
  };
});

const span = computed(() => {
  const date = preview.value?.first.date;
  if (!date) return null;
  const days = daysUntil(date, isoToday());
  return { days, ...spanParts(days) };
});
const overdue = computed(() => (span.value?.days ?? 0) < 0);

// The paragraph alone is a seal, the sentence behind it is the argument.
const basis = computed(() => {
  const first = preview.value?.first;
  if (!first) return null;
  const rule =
    first.derivation?.find((d) => d.step === "notice-month")?.label ?? null;
  const text = (rule ?? first.note ?? "").replace(/\.$/, "");
  if (!first.source_label && !text) return null;
  return {
    label: first.source_label ?? null,
    rule: text || null,
    url: first.source_url,
  };
});

const planHref = computed(() => {
  if (!selected.value) return "/";
  const params = new URLSearchParams({ date: anchorDate.value });
  if (localVariant.value)
    return `/${selected.value.slug}/${localVariant.value.slug}/?${params}`;
  params.set("variant", previewVariant.value?.slug ?? BUNDESWEIT);
  if (ort.value) params.set("region", ort.value.state);
  return `/${selected.value.slug}/?${params}`;
});

onMounted(() => (savedPlans.value = loadSavedPlans()));
</script>

<style scoped>
.intro {
  padding: 1rem 0 0.5rem;
}
h1 {
  max-width: 20ch;
  margin: 0 0 1rem;
}
.lede {
  color: var(--muted);
  max-width: 56ch;
  margin: 0;
}
.lede strong {
  color: var(--ink);
}

/* Two plans fit side by side, four stack into two rows, one fills the row. */
.plans {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(22rem, 1fr));
  gap: 1.25rem;
  margin-bottom: 1rem;
}

/* Saved plans fade in after the storage read and slide out when forgotten. */
.plan-enter-active {
  transition:
    opacity 0.3s ease,
    transform 0.3s cubic-bezier(0.2, 0.8, 0.3, 1);
}
.plan-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.plan-enter-from {
  opacity: 0;
  transform: translateY(0.5rem);
}
.plan-leave-to {
  opacity: 0;
  transform: translateX(-1rem);
}
.plan-move {
  transition: transform 0.3s ease;
}

/* Steps arrive, they do not pop: fade up on enter, fade out on leave. */
.reveal-enter-active {
  transition:
    opacity 0.24s ease,
    transform 0.24s cubic-bezier(0.2, 0.8, 0.3, 1);
}
.reveal-leave-active {
  transition: opacity 0.14s ease;
}
.reveal-enter-from {
  opacity: 0;
  transform: translateY(0.5rem);
}
.reveal-leave-to {
  opacity: 0;
}
.drop-enter-active,
.drop-leave-active {
  transition:
    opacity 0.14s ease,
    transform 0.14s ease;
}
.drop-enter-from,
.drop-leave-to {
  opacity: 0;
  transform: translateY(-0.25rem);
}

/* One rhythm: every block of the page starts the same distance below the last. */
.step {
  margin-top: 4rem;
}
@media (max-width: 40rem) {
  .step {
    margin-top: 2.5rem;
  }
}
.q {
  font-size: var(--fs-lg);
  border: 0;
  padding: 0;
  margin: 0 0 1.25rem;
}

/* Cards, not pills: the pill shape belongs to the date presets below. */
.choices {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.6rem;
}
@media (max-width: 40rem) {
  .choices {
    grid-template-columns: repeat(2, 1fr);
  }
}
.choice {
  text-align: left;
  font-weight: 600;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.9rem 0.8rem;
  color: var(--ink);
  line-height: 1.25;
  cursor: pointer;
}
.choice:hover {
  border-color: var(--accent);
}
.choice small {
  display: block;
  font-weight: 400;
  font-size: var(--fs-xs);
  color: var(--muted);
  margin-top: 0.3rem;
  text-wrap: balance;
}
.choice[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.choice[aria-pressed="true"] small {
  color: var(--accent-ink);
  opacity: 0.8;
}

.fields {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem 1.75rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}
.field > label {
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.field input {
  padding: 0.5rem 0.75rem;
  font-size: var(--fs-md);
}
input[type="date"] {
  width: 11rem;
}
.ac-input {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding-left: 0.6rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--paper-raised);
  color: var(--muted);
  width: 19rem;
}
.ac-input:focus-within {
  border-color: var(--accent);
}
.ac-input.picked {
  border-color: var(--done-color);
}
.ac-input .ok {
  color: var(--done-color);
}
.ac-input input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  padding-left: 0;
}
.ac-input input:focus-visible {
  outline: none;
}
@media (max-width: 40rem) {
  .field,
  .field input,
  .ac-input {
    width: 100%;
  }
}

.ac {
  position: relative;
}
.ac ul {
  position: absolute;
  z-index: 5;
  top: 100%;
  left: 0;
  right: 0;
  margin: 0.25rem 0 0;
  padding: 0.25rem;
  list-style: none;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-md);
  max-height: 15rem;
  overflow: auto;
}
.ac li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.6rem;
  padding: 0.4rem 0.5rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.ac li:hover,
.ac li[aria-selected="true"] {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.ac .tag {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  font-size: var(--fs-xs);
  color: var(--muted);
  white-space: nowrap;
}
.ac .tag.covered {
  color: var(--done-color);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1.25rem;
}
.chip {
  border-radius: var(--radius-pill);
  padding: 0.25rem 0.75rem;
  font-size: var(--fs-xs);
}
.chip[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}

/* Coverage is marked by icon and wording, never by colour alone. */
.coverage {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  margin: 1.25rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
  max-width: 60ch;
}
.coverage .ok {
  flex-shrink: 0;
  color: var(--done-color);
}
.coverage .thin {
  flex-shrink: 0;
  color: var(--holiday);
}
.coverage b {
  color: var(--ink);
}

.ferien {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  margin: 0.5rem 0 0;
  font-size: var(--fs-sm);
  color: var(--holiday);
  max-width: 60ch;
}
.ferien svg {
  flex-shrink: 0;
}

.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  padding: 1.75rem 1.75rem 1.5rem;
}
.eyebrow {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin: 0 0 0.5rem;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.eyebrow.late {
  color: var(--warn);
}
.first-task {
  margin: 0 0 0.2rem;
  font-size: var(--fs-md);
  font-weight: 600;
}
.first-date {
  margin: 0;
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--accent);
}
.first-date.late {
  color: var(--warn);
}
.countdown {
  margin: 0.2rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.countdown.late {
  color: var(--warn);
}
.rescue {
  margin: 0.9rem 0 0;
  padding: 0.6rem 0.8rem;
  border-left: 3px solid var(--warn);
  background: color-mix(in srgb, var(--warn) 8%, transparent);
  font-size: var(--fs-sm);
}
.basis {
  margin: 0.9rem 0 0;
  padding-top: 0.8rem;
  border-top: 1px solid var(--line);
  font-size: var(--fs-sm);
  color: var(--muted);
}
.basis b {
  color: var(--ink);
}
.source {
  margin-left: 0.3rem;
}

.rest {
  list-style: none;
  margin: 1.4rem 0 0;
  padding: 0;
  border-top: 1px solid var(--line);
}
.rest li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--line);
}
.rest .dt {
  flex-shrink: 0;
  font-size: var(--fs-sm);
  color: var(--muted);
  white-space: nowrap;
}
.rest .dt.none {
  color: var(--holiday);
}
.more {
  margin: 0.8rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.replaces {
  margin: 0.8rem 0 0;
  font-size: var(--fs-sm);
  color: var(--holiday);
}
</style>
