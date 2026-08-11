<template>
  <div class="wom-timeline" ref="rootEl">
    <section v-show="!showPlanner">
      <header>
        <h1>Was hast du vor?</h1>
        <p class="lede">
          Wähl dein Datum, alle Fristen werden rückwärts berechnet.
        </p>
        <div class="shelf">
          <button
            v-for="v in vorhaben"
            :key="v.slug"
            type="button"
            class="chip"
            :aria-pressed="v.slug === selectedSlug"
            @click="pick(v.slug)"
          >
            {{ v.label }}
          </button>
        </div>
      </header>

      <ol class="how">
        <li>Datum wählen</li>
        <li>Fristen sehen</li>
        <li>Als Kalender exportieren</li>
      </ol>

      <div class="stage">
        <div class="pickers">
          <label class="date-field">
            <span>{{ selected.anchorLabel }}</span>
            <input
              type="date"
              :value="anchorDate"
              :min="minDate"
              :max="maxDate"
              @change="onPlace(($event.target as HTMLInputElement).value)"
            />
          </label>
          <label v-if="selected.variants.length > 1" class="place">
            <span>{{ selected.variantLabel }}</span>
            <select v-model="variantSlug">
              <option
                v-for="v in selected.variants"
                :key="v.slug"
                :value="v.slug"
              >
                {{ v.label }}
              </option>
            </select>
          </label>
          <div class="presets">
            <button
              v-for="p in presets"
              :key="p.label"
              type="button"
              class="chip small"
              :aria-pressed="anchorDate === p.iso()"
              @click="onPlace(p.iso())"
            >
              {{ p.label }}
            </button>
          </div>
        </div>

        <p class="hint">{{ hintText }}</p>
        <Timeline
          :tasks="tasks"
          :anchor-date="anchorDate"
          :anchor-name="selected.anchorName"
          :region-code="previewVariant?.regionCode"
          :show-legend="false"
          clickable
          keyed
          @place="onPlace"
          @preview="previewIso = $event"
        />

        <p class="summary">{{ summaryText }}</p>

        <a class="btn primary" :href="planHref" @click.prevent="openPlan"
          >Zeitplan öffnen <ArrowRight :size="14"
        /></a>
      </div>
    </section>

    <section v-if="showPlanner" class="planner-wrap">
      <button class="back" type="button" @click="backToRail">
        &larr; Zurück zur Startseite
      </button>
      <DeadlinePlanner
        :key="selected.slug"
        :vorhaben="selected.vorhaben"
        :anchor-label="selected.anchorLabel"
        :variant-label="selected.variantLabel"
        :variants="selected.variants"
        :default-slug="variantSlug"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  useTemplateRef,
} from "vue";
import { appliesTo } from "../../lib/facets";
import { formatDateWithWeekday, toDate } from "../../lib/format-date";
import {
  addDays,
  daysBetween,
  isoOf,
  utcDay,
} from "../../lib/timeline-geometry";
import DeadlinePlanner from "./DeadlinePlanner.vue";
import Timeline from "./deadline-planner/Timeline.vue";
import { usePlannerSchedule } from "./deadline-planner/usePlannerSchedule";
import { ArrowRight } from "lucide-vue-next";
import type { VorhabenData } from "../../lib/vorhaben-data";

const props = defineProps<{
  vorhaben: VorhabenData[];
}>();

const rootEl = useTemplateRef<HTMLElement>("rootEl");

const selectedSlug = ref(props.vorhaben[0]?.slug);
const selected = computed(
  () =>
    props.vorhaben.find((v) => v.slug === selectedSlug.value) ??
    props.vorhaben[0],
);

function pick(slug: string) {
  if (slug === selectedSlug.value) return;
  selectedSlug.value = slug;
  variantSlug.value = defaultVariantSlug();
}

const TODAY = utcDay(new Date());
const minDate = isoOf(addDays(TODAY, -14));
const maxDate = isoOf(addDays(TODAY, 365));
const anchorDate = ref(isoOf(addDays(TODAY, 90)));
const previewIso = ref<string | null>(null);

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
const doneIds = reactive<Record<string, boolean>>({});
const showPlanner = ref(false);

function defaultVariantSlug() {
  const v = selected.value;
  return (
    v.variants.find((x) => x.slug === v.defaultVariant)?.slug ??
    v.variants[0]?.slug
  );
}
const variantSlug = ref(defaultVariantSlug());
const previewVariant = computed(
  () =>
    selected.value.variants.find((v) => v.slug === variantSlug.value) ??
    selected.value.variants[0],
);
const workingDeadlines = computed(() =>
  (previewVariant.value?.deadlines ?? []).filter((d) => appliesTo(d, [])),
);

const { tasks } = usePlannerSchedule(
  anchorDate,
  previewVariant,
  workingDeadlines,
  () => selected.value.anchorLabel,
  doneIds,
);

function onPlace(iso: string) {
  anchorDate.value = iso;
}

const planHref = computed(() => {
  const params = new URLSearchParams();
  if (anchorDate.value) params.set("date", anchorDate.value);
  if (previewVariant.value) params.set("variant", previewVariant.value.slug);
  return `/${selected.value.slug}/?${params.toString()}`;
});

const hintText =
  "Zieh den Griff, tippe auf den Zeitstrahl oder nutz die Pfeiltasten.";

const summaryText = computed(() => {
  const iso = previewIso.value ?? anchorDate.value;
  const dated = tasks.value.filter((t) => t.date !== null);
  const first = dated.reduce<string | null>(
    (min, t) => (min === null || t.date! < min ? t.date! : min),
    null,
  );
  if (!first) return `${dated.length} Fristen`;
  const shift = daysBetween(toDate(anchorDate.value), toDate(iso));
  const firstShown = isoOf(addDays(toDate(first), shift));
  return `${dated.length} Fristen · erste am ${formatDateWithWeekday(firstShown)}`;
});

function measureKeyed(attr: string): Map<string, DOMRect> {
  const map = new Map<string, DOMRect>();
  rootEl.value?.querySelectorAll<HTMLElement>(`[${attr}]`).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width) map.set(el.getAttribute(attr)!, r);
  });
  return map;
}

function flyDots(first: Map<string, DOMRect>, toAttr: string, dy: number) {
  const targets = rootEl.value?.querySelectorAll<HTMLElement>(`[${toAttr}]`);
  if (!targets) return;
  const last = new Map<string, DOMRect>();
  targets.forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width) last.set(el.getAttribute(toAttr)!, r);
  });
  targets.forEach((el) => (el.style.opacity = "0"));
  let i = 0;
  targets.forEach((el) => {
    const key = el.getAttribute(toAttr)!;
    const f = first.get(key);
    const l = last.get(key);
    if (!f || !l) {
      el.style.opacity = "1";
      return;
    }
    const fly = document.createElement("div");
    fly.className = "wom-flier";
    if (el.closest(".warn")) fly.dataset.warn = "1";
    fly.style.left = f.left + "px";
    fly.style.top = f.top + dy + "px";
    document.body.appendChild(fly);
    const anim = fly.animate(
      [
        { transform: "translate(0,0) scale(1)" },
        {
          transform: `translate(${(l.left - f.left) * 0.55}px,${(l.top - (f.top + dy)) * 0.75}px) scale(1.25)`,
          offset: 0.55,
        },
        {
          transform: `translate(${l.left - f.left}px,${l.top - (f.top + dy)}px) scale(1)`,
        },
      ],
      {
        duration: 560,
        delay: i++ * 32,
        easing: "cubic-bezier(.6,.02,.2,1)",
        fill: "forwards",
      },
    );
    anim.addEventListener("finish", () => {
      el.style.opacity = "1";
      fly.remove();
    });
  });
}

async function settle() {
  await nextTick();
  await new Promise<void>((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
  );
}

async function openPlan() {
  const canAnimate =
    !!rootEl.value && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const first = canAnimate ? measureKeyed("data-node-key") : null;
  const dy = window.scrollY;
  history.pushState({}, "", planHref.value);
  showPlanner.value = true;
  window.scrollTo({ top: 0 });
  if (!first) return;
  await settle();
  flyDots(first, "data-dot-key", dy);
  rootEl
    .value!.querySelectorAll<HTMLElement>(".item .card, .item .when")
    .forEach((el, n) =>
      el.animate(
        [
          { opacity: 0, transform: "translateX(18px)" },
          { opacity: 1, transform: "none" },
        ],
        {
          duration: 420,
          delay: 180 + n * 26,
          easing: "cubic-bezier(.2,.8,.3,1)",
          fill: "backwards",
        },
      ),
    );
}

async function collapseToRail() {
  const canAnimate =
    !!rootEl.value && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const first = canAnimate ? measureKeyed("data-dot-key") : null;
  const dy = window.scrollY;
  showPlanner.value = false;
  window.scrollTo({ top: 0 });
  if (!first) return;
  await settle();
  flyDots(first, "data-node-key", dy);
}

function onPopState() {
  if (showPlanner.value) collapseToRail();
}
function backToRail() {
  history.back();
}
onMounted(() => window.addEventListener("popstate", onPopState));
onBeforeUnmount(() => window.removeEventListener("popstate", onPopState));
</script>

<style scoped>
header {
  padding: 0.5rem 0 1.5rem;
}
h1 {
  font-size: clamp(1.8rem, 4.5vw, 2.6rem);
  max-width: 16ch;
  letter-spacing: -0.01em;
  margin-top: 0;
}
.lede {
  color: var(--muted);
  max-width: 44ch;
}

.shelf {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.chip {
  border-radius: var(--radius-pill);
  padding: 0.5rem 1rem;
  font-size: var(--fs-sm);
}
.chip.small {
  padding: 0.25rem 0.75rem;
  font-size: var(--fs-xs);
}
.chip[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.chip:disabled {
  opacity: 0.5;
  cursor: default;
}

.place select {
  border-radius: var(--radius-pill);
  padding: 0.5rem 1rem;
  font-size: var(--fs-sm);
}

.stage {
  margin-top: 2rem;
  position: relative;
}
@media (max-width: 36rem) {
  header {
    padding: 0 0 0.75rem;
  }
  .lede {
    margin-bottom: 0.75rem;
  }
  .stage {
    margin-top: 1rem;
  }
}
.hint {
  font-size: var(--fs-sm);
  color: var(--muted);
  margin: 0 0 0.5rem;
}

.pickers {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 0.8rem;
  margin-bottom: 1rem;
}
.date-field span,
.place span {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.date-field input {
  font-size: var(--fs-md);
  font-family: var(--font-mono);
  padding: 0.5rem 0.75rem;
}
.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding-bottom: 0.25rem;
}
.summary {
  margin: 0.75rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
  min-height: 1.5rem;
}
.how {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1.6rem;
  margin: 0;
  padding: 0 0 1rem;
  list-style: none;
  counter-reset: step;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.how li {
  counter-increment: step;
}
.how li::before {
  content: counter(step) ". ";
  color: var(--accent);
  font-weight: 600;
}

.btn {
  border-radius: var(--radius);
  font-weight: 600;
  font-size: var(--fs-xs);
  padding: 0.25rem 0.75rem;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  white-space: nowrap;
}
.btn.primary {
  margin-top: 1rem;
  padding: 0.5rem 1rem;
  font-size: var(--fs-sm);
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}

.planner-wrap {
  padding-top: 0.5rem;
}
.back {
  background: none;
  border: 0;
  color: var(--accent);
  font-size: var(--fs-sm);
  padding: 0;
  margin-bottom: 1rem;
  cursor: pointer;
}

:global(.wom-flier) {
  position: fixed;
  width: 0.8rem;
  height: 0.8rem;
  border-radius: 50%;
  background: var(--paper-raised);
  border: 2px solid var(--accent);
  z-index: 60;
  pointer-events: none;
}
:global(.wom-flier[data-warn="1"]) {
  border-color: var(--warn);
}
</style>
