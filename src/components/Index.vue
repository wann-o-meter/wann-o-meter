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
            type="button"
            class="chip"
            :aria-pressed="armed"
            @click="armed = !armed"
          >
            Umzug
          </button>
          <button
            v-for="s in SOON"
            :key="s"
            type="button"
            class="chip"
            disabled
          >
            {{ s }} &middot; bald
          </button>
        </div>
      </header>

      <div class="stage">
        <p class="hint" :class="{ armed }">{{ hintText }}</p>
        <div
          class="scroller"
          :class="{ armed }"
          ref="scrollerEl"
          @mousemove="onScrollerMove"
          @mouseleave="ghost = null"
          @click="onScrollerClick"
        >
          <div class="track" ref="trackEl" :style="{ width: trackWidth + 'px' }">
            <div class="axis"></div>

            <div
              v-for="t in monthTicks"
              :key="'mt' + t.x"
              class="mtick"
              :style="{ left: t.x + 'px' }"
            ></div>
            <div
              v-for="t in monthTicks"
              :key="'ml' + t.x"
              class="mlabel"
              :style="{ left: t.x + 'px' }"
            >
              {{ t.label }}
            </div>

            <div
              v-for="h in holidayTicks"
              :key="h.date"
              class="htick"
              :title="h.name"
              :style="{ left: h.x + 'px' }"
            ></div>

            <div class="today" :style="{ left: todayX + 'px' }"><b>HEUTE</b></div>

            <div v-if="ghost" class="ghost" :style="{ left: ghost.x + 'px' }">
              <b>{{ ghost.label }}</b>
            </div>

            <template v-if="placed">
              <div class="thread" :style="threadStyle"></div>
              <button
                v-for="t in visibleTasks"
                :key="t.id"
                type="button"
                class="node"
                :class="{ warn: t.weekend || t.collision }"
                :style="{ left: pxIso(t.date) + 'px' }"
                :data-node-key="t.id"
                :data-label="nodeLabel(t)"
                :aria-label="nodeLabel(t)"
              ></button>
              <div class="pin" :style="{ left: pxIso(anchorDate) + 'px' }" :data-node-key="ANCHOR_ID">
                <b>Umzug</b><i>{{ pinLabel }}</i>
              </div>
            </template>
          </div>
        </div>

        <section v-if="placed" class="result on">
          <div class="rhead">
            <h2>Umzug am {{ langDate(toDate(anchorDate)) }}</h2>
            <span
              >{{ tasks.length }} Fristen<template v-if="stats.warnings">
                &middot; {{ stats.warnings }} Kollisionen</template
              ></span
            >
          </div>
          <div class="list">
            <div
              v-for="t in previewTasks"
              :key="t.id"
              class="row"
              :class="{ warn: t.weekend || t.collision }"
            >
              <div class="d">{{ weekdayLong(toDate(t.date)) }}, {{ shortDate(toDate(t.date)) }}</div>
              <h3>{{ t.label }}</h3>
              <a v-if="t.source_url" class="badge stamp" :href="t.source_url" target="_blank" rel="noopener">{{
                t.source_label ?? "Quelle"
              }}</a>
              <span v-else class="badge missing">Quelle fehlt</span>
            </div>
            <div v-if="hiddenTaskCount > 0" class="row more">
              + {{ hiddenTaskCount }} weitere im Zeitplan
            </div>
          </div>
          <div class="acts">
            <a class="btn primary" :href="planHref" @click.prevent="openPlan">Zeitplan öffnen</a>
            <button class="reset" type="button" @click="resetPlaced">
              anderes Datum
            </button>
          </div>
        </section>
      </div>
    </section>

    <section v-if="showPlanner" class="planner-wrap">
      <button class="back" type="button" @click="backToRail">
        &larr; zurück zum Zeitstrahl
      </button>
      <DeadlinePlanner
        vorhaben="Umzug innerhalb Deutschlands"
        anchor-label="Umzugstag"
        variant-label="Ort"
        :variants="variants"
        :default-slug="defaultSlug"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, useTemplateRef } from "vue";
import type { ScheduleEntry } from "../../lib/deadline-plan";
import { MONTH_NAMES, WEEKDAY_NAMES_LONG, WEEKDAY_NAMES_SHORT } from "../../lib/date-display";
import { toDate } from "../../lib/format-date";
import { holidaysFor } from "../../lib/holidays";
import DeadlinePlanner from "./DeadlinePlanner.vue";
import type { PlanVariant } from "./deadline-planner/types";
import { ANCHOR_ID, COUNTRY_CODE, usePlannerSchedule } from "./deadline-planner/usePlannerSchedule";

const props = defineProps<{
  variants: PlanVariant[];
  defaultSlug: string;
}>();

// Mockups for everything else on the pivot doc's "später prüfen" list
// (section 6) - disabled chips, nothing behind them yet.
const SOON = ["Geburt", "Hochzeit", "Jobwechsel", "Todesfall"];
const PPD = 6; // rail pixels per day

const rootEl = useTemplateRef<HTMLElement>("rootEl");
const trackEl = useTemplateRef<HTMLElement>("trackEl");
const scrollerEl = useTemplateRef<HTMLElement>("scrollerEl");

const armed = ref(false);
const anchorDate = ref(""); // ISO day, "" until placed
const ghost = ref<{ x: number; label: string } | null>(null);
// usePlannerSchedule's stats need a doneIds map, but this teaser has no
// checkboxes - nothing ever writes to it, so stats.done stays 0.
const doneIds = reactive<Record<string, boolean>>({});
// True once the real DeadlinePlanner is mounted in place of the rail.
const showPlanner = ref(false);

const placed = computed(() => anchorDate.value !== "");

const previewVariant = computed(
  () => props.variants.find((v) => v.slug === props.defaultSlug) ?? props.variants[0],
);
const workingDeadlines = computed(() => previewVariant.value?.deadlines ?? []);

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
function isoOf(d: Date): string {
  return d.toISOString().slice(0, 10);
}

const today = new Date();
today.setHours(0, 0, 0, 0);
const START = addDays(today, -14);
const END = addDays(START, Math.round(15 * 30.4));
const trackWidth = px(START.getTime() === END.getTime() ? START : END);

function px(d: Date): number {
  return Math.round(((d.getTime() - START.getTime()) / 86400000) * PPD);
}
function pxIso(iso: string): number {
  return px(toDate(iso));
}
function dateAtX(x: number): Date {
  return addDays(START, Math.round(x / PPD));
}
const todayX = px(today);

function shortDate(d: Date): string {
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()].slice(0, 3)}`;
}
function langDate(d: Date): string {
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
function weekdayLong(d: Date): string {
  return WEEKDAY_NAMES_LONG[(d.getUTCDay() + 6) % 7];
}
function weekdayShort(d: Date): string {
  return WEEKDAY_NAMES_SHORT[(d.getUTCDay() + 6) % 7];
}
function nodeLabel(t: ScheduleEntry & { date: string }): string {
  return `${shortDate(toDate(t.date))} · ${t.label}`;
}

const { tasks, stats } = usePlannerSchedule(
  anchorDate,
  previewVariant,
  workingDeadlines,
  () => "Umzugstag",
  doneIds,
);

const datedTasks = computed(() =>
  tasks.value.filter((t): t is ScheduleEntry & { date: string } => t.date !== null),
);
// Only tasks inside the printed [START, END] window get a dot on the rail -
// far-out ones (e.g. Rundfunkbeitrag, +1400 days) still count in the totals.
const visibleTasks = computed(() =>
  datedTasks.value.filter((t) => {
    const d = toDate(t.date);
    return d >= START && d <= END;
  }),
);
const hiddenTaskCount = computed(() => datedTasks.value.length - visibleTasks.value.length);
const previewTasks = computed(() => datedTasks.value.slice(0, 4));

const threadStyle = computed(() => {
  if (!visibleTasks.value.length) return {};
  const left = pxIso(visibleTasks.value[0].date);
  const right = pxIso(visibleTasks.value[visibleTasks.value.length - 1].date);
  return { left: left + "px", width: Math.max(0, right - left) + "px" };
});

const pinLabel = computed(() =>
  placed.value ? `${weekdayShort(toDate(anchorDate.value))}, ${langDate(toDate(anchorDate.value))}` : "",
);

// Feeds the mounted DeadlinePlanner's own ?date=/?variant= handling (see
// usePlannerSchedule), and keeps the address bar honest with no real nav.
const planHref = computed(() => {
  const params = new URLSearchParams();
  if (anchorDate.value) params.set("date", anchorDate.value);
  if (previewVariant.value) params.set("variant", previewVariant.value.slug);
  return `/umzug/?${params.toString()}`;
});

const monthTicks = computed(() => {
  const out: { x: number; label: string }[] = [];
  let m = new Date(START.getFullYear(), START.getMonth(), 1);
  while (m < END) {
    if (m >= START) {
      out.push({
        x: px(m),
        label: MONTH_NAMES[m.getMonth()].slice(0, 3) + (m.getMonth() === 0 ? " " + m.getFullYear() : ""),
      });
    }
    m = new Date(m.getFullYear(), m.getMonth() + 1, 1);
  }
  return out;
});

const holidayTicks = computed(() => {
  const years = new Set([START.getFullYear(), END.getFullYear()]);
  return [...years]
    .flatMap((y) => holidaysFor(y, COUNTRY_CODE, previewVariant.value?.regionCode))
    .map((h) => ({ ...h, x: px(toDate(h.date)) }))
    .filter((h) => h.x >= 0 && h.x <= trackWidth);
});

const hintText = computed(() => {
  if (armed.value) return "Klick auf den Zeitstrahl - wann ist es soweit?";
  if (placed.value) return "Vorhaben gesetzt · anderes wählen zum Verschieben";
  return "Wähle oben ein Vorhaben";
});

function onScrollerMove(e: MouseEvent) {
  if (!armed.value || !trackEl.value) return;
  const r = trackEl.value.getBoundingClientRect();
  const x = e.clientX - r.left;
  ghost.value = { x, label: `${weekdayShort(dateAtX(x))}, ${langDate(dateAtX(x))}` };
}
function onScrollerClick(e: MouseEvent) {
  if (!armed.value || !trackEl.value) return;
  const r = trackEl.value.getBoundingClientRect();
  place(dateAtX(e.clientX - r.left));
}
function place(d: Date) {
  anchorDate.value = isoOf(d);
  armed.value = false;
  ghost.value = null;
  nextTick(() => {
    scrollerEl.value?.scrollTo({ left: Math.max(0, px(d) - 120), behavior: "smooth" });
  });
}
function resetPlaced() {
  anchorDate.value = "";
  armed.value = true;
}

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
        { transform: `translate(${l.left - f.left}px,${l.top - (f.top + dy)}px) scale(1)` },
      ],
      { duration: 560, delay: i++ * 32, easing: "cubic-bezier(.6,.02,.2,1)", fill: "forwards" },
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
  await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
}

async function openPlan() {
  const canAnimate = !!rootEl.value && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const first = canAnimate ? measureKeyed("data-node-key") : null;
  const dy = window.scrollY;
  history.pushState({}, "", planHref.value);
  showPlanner.value = true;
  window.scrollTo({ top: 0 });
  if (!first) return;
  await settle();
  flyDots(first, "data-dot-key", dy);
  rootEl.value!.querySelectorAll<HTMLElement>(".item .card, .item .when").forEach((el, n) =>
    el.animate(
      [
        { opacity: 0, transform: "translateX(18px)" },
        { opacity: 1, transform: "none" },
      ],
      { duration: 420, delay: 180 + n * 26, easing: "cubic-bezier(.2,.8,.3,1)", fill: "backwards" },
    ),
  );
}

async function collapseToRail() {
  const canAnimate = !!rootEl.value && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const first = canAnimate ? measureKeyed("data-dot-key") : null;
  const dy = window.scrollY;
  showPlanner.value = false;
  window.scrollTo({ top: 0 });
  if (!first) return;
  await settle();
  flyDots(first, "data-node-key", dy);
  rootEl.value!.querySelectorAll<HTMLElement>(".row").forEach((el, n) =>
    el.animate(
      [
        { opacity: 0, transform: "translateY(10px)" },
        { opacity: 1, transform: "none" },
      ],
      { duration: 420, delay: 180 + n * 26, easing: "cubic-bezier(.2,.8,.3,1)", fill: "backwards" },
    ),
  );
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
.scroller {
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 0.85rem;
  cursor: crosshair;
}
.scroller.armed {
  cursor: copy;
}
.track {
  position: relative;
  height: 15.5rem;
}
.axis {
  position: absolute;
  left: 0;
  right: 0;
  top: 7.1rem;
  height: 1px;
  background: var(--line);
}
.mtick {
  position: absolute;
  top: 6.25rem;
  width: 1px;
  height: 0.9rem;
  background: var(--line);
}
.mlabel {
  position: absolute;
  top: 7.6rem;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.04em;
  color: var(--muted);
  white-space: nowrap;
  padding-left: 0.4rem;
}
.htick {
  position: absolute;
  top: 6.75rem;
  width: 2px;
  height: 0.45rem;
  background: var(--warn);
}
.today {
  position: absolute;
  top: 2.75rem;
  bottom: 4.9rem;
  width: 1px;
  background: var(--ink);
}
.today b {
  position: absolute;
  top: -1.25rem;
  left: -0.65rem;
  font-family: var(--font-mono);
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  background: var(--paper);
  padding: 0 0.25rem;
}
.pin {
  position: absolute;
  top: 1.5rem;
  bottom: 5.6rem;
  width: 2px;
  background: var(--accent);
}
.pin b {
  position: absolute;
  top: -0.25rem;
  left: 0.6rem;
  font-weight: 600;
  font-size: 0.95rem;
  white-space: nowrap;
  color: var(--accent);
}
.pin i {
  position: absolute;
  top: 1.1rem;
  left: 0.6rem;
  font-style: normal;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--muted);
  white-space: nowrap;
}
.thread {
  position: absolute;
  top: 7.1rem;
  height: 2px;
  background: var(--accent);
  opacity: 0.3;
}
.node {
  position: absolute;
  top: 6.75rem;
  width: 0.8rem;
  height: 0.8rem;
  margin-left: -0.4rem;
  border-radius: 50%;
  background: var(--paper-raised);
  border: 2px solid var(--accent);
  padding: 0;
}
.node.warn {
  border-color: var(--warn);
}
.node::after {
  content: attr(data-label);
  position: absolute;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  background: var(--ink);
  color: var(--paper);
  font-size: 0.7rem;
  white-space: nowrap;
  padding: 0.25rem 0.55rem;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s;
}
.node:hover::after,
.node:focus-visible::after {
  opacity: 1;
}
.ghost {
  position: absolute;
  top: 1.5rem;
  bottom: 5.6rem;
  width: 2px;
  background: var(--accent);
  opacity: 0.25;
  pointer-events: none;
}
.ghost b {
  position: absolute;
  top: -0.1rem;
  left: 0.5rem;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--accent);
  white-space: nowrap;
}

.result {
  margin-top: 1.6rem;
  border-top: 1px solid var(--line);
  padding-top: 1.5rem;
}
.rhead {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.4rem;
  align-items: baseline;
  margin-bottom: 1.1rem;
}
.rhead h2 {
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 1.2rem;
}
.rhead span {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14.5rem, 1fr));
  gap: 0.75rem;
}
.row {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 0.75rem 0.9rem;
  border-left: 2px solid var(--accent);
}
.row.warn {
  border-left-color: var(--warn);
  background: color-mix(in srgb, var(--warn) 10%, var(--paper-raised));
}
.row.more {
  border-left-color: var(--line);
  display: flex;
  align-items: center;
  color: var(--muted);
  font-size: 0.85rem;
}
.row .d {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.row h3 {
  margin: 0 0 0.45rem;
  border: 0;
  padding: 0;
  font-size: 0.95rem;
  line-height: 1.25;
}
.acts {
  margin-top: 1.4rem;
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  align-items: center;
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
.reset {
  background: none;
  border: 0;
  color: var(--muted);
  text-decoration: underline;
  font-size: 0.86rem;
  padding: 0;
}

.badge {
  border-color: var(--line);
}
.badge.stamp {
  border-color: var(--accent);
  color: var(--accent);
}
.badge.missing {
  color: var(--muted);
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
