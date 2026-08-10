<template>
  <div class="wom-timeline" ref="rootEl">
    <section v-show="!showPlanner">
      <header>
        <h1>Was hast du vor?</h1>
        <p class="lede">
          Setz es auf den Zeitstrahl. Alles, was vorher passieren muss, wächst
          rückwärts daraus hervor.
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
      </header>

      <div class="stage">
        <p class="hint" :class="{ armed }">{{ hintText }}</p>
        <Timeline
          :tasks="tasks"
          :anchor-date="anchorDate"
          :anchor-name="selected.anchorName"
          :region-code="previewVariant?.regionCode"
          :clickable="armed"
          keyed
          @place="onPlace"
        >
          <template #pin-extra>
            <a class="btn primary" :href="planHref" @click.prevent="openPlan"
              >Zeitplan öffnen <ArrowRight :size="14"
            /></a>
          </template>
        </Timeline>
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
import DeadlinePlanner from "./DeadlinePlanner.vue";
import Timeline from "./deadline-planner/Timeline.vue";
import { usePlannerSchedule } from "./deadline-planner/usePlannerSchedule";
import { ArrowRight } from "lucide-vue-next";
// Type-only, and it has to stay that way: lib/vorhaben-data.ts reads node:fs.
import type { VorhabenData } from "../../lib/vorhaben-data";

const props = defineProps<{
  vorhaben: VorhabenData[];
}>();

const rootEl = useTemplateRef<HTMLElement>("rootEl");

const armed = ref(false);
const selectedSlug = ref(props.vorhaben[0]?.slug);
const selected = computed(
  () =>
    props.vorhaben.find((v) => v.slug === selectedSlug.value) ??
    props.vorhaben[0],
);

// Clicking the active chip toggles placement mode, clicking another one
// switches Vorhaben and asks for a date right away.
function pick(slug: string) {
  if (slug === selectedSlug.value) {
    armed.value = !armed.value;
    return;
  }
  selectedSlug.value = slug;
  variantSlug.value = defaultVariantSlug();
  armed.value = true;
}

const anchorDate = ref(""); // ISO day, "" until placed
// usePlannerSchedule's stats need a doneIds map, but this teaser has no
// checkboxes - nothing ever writes to it, so stats.done stays 0.
const doneIds = reactive<Record<string, boolean>>({});
// True once the real DeadlinePlanner is mounted in place of the rail.
const showPlanner = ref(false);

const placed = computed(() => anchorDate.value !== "");

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
// No facet chips in the teaser, so it shows what the planner shows with none
// ticked - otherwise nodes would vanish the moment the planner mounts.
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
  armed.value = false;
}

// Feeds the mounted DeadlinePlanner's own ?date=/?variant= handling (see
// usePlannerSchedule), and keeps the address bar honest with no real nav.
const planHref = computed(() => {
  const params = new URLSearchParams();
  if (anchorDate.value) params.set("date", anchorDate.value);
  if (previewVariant.value) params.set("variant", previewVariant.value.slug);
  return `/${selected.value.slug}/?${params.toString()}`;
});

const hintText = computed(() => {
  if (armed.value) return "Zieh über den Zeitstrahl - wann ist es soweit?";
  if (placed.value) return "Vorhaben gesetzt · anderes wählen zum Verschieben";
  return "Wähle oben ein Vorhaben";
});

function measureKeyed(attr: string): Map<string, DOMRect> {
  const map = new Map<string, DOMRect>();
  rootEl.value?.querySelectorAll<HTMLElement>(`[${attr}]`).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width) map.set(el.getAttribute(attr)!, r);
  });
  return map;
}

// Flies a clone of each `[toAttr]` element from its `first`-measured position
// to where it landed after the swap. Callers already filter reduced-motion.
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

// Vue's DOM patch (nextTick) isn't always enough for DeadlinePlanner's own
// onMounted-driven layout to have run - double rAF waits for a real paint.
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

// Both the in-page "back" button and the browser's own Back button route
// through popstate, so they can't drift out of sync with each other.
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
  border-radius: 100px;
  padding: 0.5rem 1rem;
  font-size: 0.94rem;
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

.place {
  display: inline-flex;
  align-items: baseline;
  gap: 0.5rem;
  margin-top: 0.9rem;
}
.place span {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.place select {
  font-size: 0.94rem;
  padding: 0.35rem 0.6rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
}

.stage {
  margin-top: 2rem;
  position: relative;
}
.hint {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.6rem;
  height: 1rem;
}
.hint.armed {
  color: var(--accent);
}

.btn {
  font-weight: 600;
  font-size: 0.9rem;
  padding: 0.65rem 1.2rem;
  text-decoration: none;
  display: inline-block;
}
.btn.primary {
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
  font-size: 0.9rem;
  padding: 0;
  margin-bottom: 0.9rem;
  cursor: pointer;
}

/* Flug-Klone: created outside the component root (document.body), so scoped
  selectors can never match them. */
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
