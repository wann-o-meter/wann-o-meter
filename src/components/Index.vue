<template>
  <div class="wom-timeline" ref="rootEl">
    <!-- Ansicht A: Zeitstrahl -->
    <section v-show="view === 'rail'">
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
            <div class="axis" ref="axisEl"></div>

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
              <div class="pin" :style="{ left: pxIso(anchorDate) + 'px' }">
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
            <button class="btn primary" type="button" @click="openPlan">
              Zeitplan öffnen
            </button>
            <button class="reset" type="button" @click="resetPlaced">
              anderes Datum
            </button>
          </div>
        </section>
      </div>
    </section>

    <!-- Ansicht B: Zeitplan -->
    <section v-show="view === 'plan'" class="plan-view">
      <button class="back" type="button" @click="backToRail">
        &larr; zurück zum Zeitstrahl
      </button>
      <h1>Umzug am {{ placed ? langDate(toDate(anchorDate)) : "-" }}</h1>
      <p class="meta">{{ ort }}</p>
      <p class="summary">
        <b>{{ stats.open }}</b> offen &middot; <b>{{ stats.done }}</b> erledigt<template
          v-if="stats.warnings"
        >
          &middot; <b class="warn-count">{{ stats.warnings }}</b> Kollisionen</template
        >
      </p>

      <div class="vrail">
        <div class="vaxis" ref="vaxisEl"></div>
        <template v-for="node in railNodes" :key="node.kind === 'item' ? node.entry.id : node.id">
          <div v-if="node.kind === 'gap'" class="pause" :style="{ height: node.heightPx + 'px' }">
            <span v-if="node.beforeOffset - node.afterOffset >= 14">
              {{ Math.round((node.beforeOffset - node.afterOffset) / 7) }} Wochen Pause
            </span>
          </div>
          <div
            v-else
            class="vitem"
            :class="{
              done: doneIds[node.entry.id],
              warn: !doneIds[node.entry.id] && (node.entry.weekend || node.entry.collision),
            }"
          >
            <button
              v-if="node.entry.id !== ANCHOR_ID"
              class="vcheck"
              type="button"
              :aria-pressed="!!doneIds[node.entry.id]"
              aria-label="Erledigt"
              @click="toggleDone(node.entry.id)"
            >{{ doneIds[node.entry.id] ? "✓" : "" }}</button>
            <div class="vdot" :data-dot-key="node.entry.id"></div>
            <div class="vwhen">
              <b>{{ shortDate(toDate(node.entry.date)) }} {{ toDate(node.entry.date).getUTCFullYear() }}</b>
              <span>{{ weekdayLong(toDate(node.entry.date)) }} &middot; {{ offsetLabel(node.entry.offset_days) }}</span>
            </div>
            <div class="vcard">
              <h3>{{ node.entry.label }}</h3>
              <p v-if="node.entry.note">{{ node.entry.note }}</p>
              <a
                v-if="node.entry.source_url"
                class="badge stamp"
                :href="node.entry.source_url"
                target="_blank"
                rel="noopener"
                >{{ node.entry.source_label ?? "Quelle" }}</a
              >
              <span v-else-if="node.entry.id !== ANCHOR_ID" class="badge missing">Quelle fehlt</span>
              <p v-if="!doneIds[node.entry.id] && node.entry.collision" class="flag">
                Fällt auf {{ node.entry.collision }} - Ämter geschlossen.
              </p>
              <p v-else-if="!doneIds[node.entry.id] && node.entry.weekend" class="flag">
                Fällt auf ein Wochenende.
              </p>
            </div>
          </div>
        </template>
      </div>

      <div class="acts">
        <a class="btn primary" href="/umzug/">Vollständigen Zeitplan öffnen</a>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, useTemplateRef } from "vue";
import type { Deadline, ScheduleEntry } from "../../lib/deadline-plan";
import { MONTH_NAMES, WEEKDAY_NAMES_LONG, WEEKDAY_NAMES_SHORT } from "../../lib/date-display";
import { toDate } from "../../lib/format-date";
import { holidaysFor } from "../../lib/holidays";
import type { PlanVariant } from "./deadline-planner/types";
import { ANCHOR_ID, COUNTRY_CODE, usePlannerSchedule } from "./deadline-planner/usePlannerSchedule";

const props = defineProps<{
  ort: string;
  regionCode?: string;
  deadlines: Deadline[];
}>();

// Mockups for everything else on the pivot doc's "später prüfen" list
// (section 6) - disabled chips, nothing behind them yet.
const SOON = ["Geburt", "Hochzeit", "Jobwechsel", "Todesfall"];
const PPD = 6; // rail pixels per day

const rootEl = useTemplateRef<HTMLElement>("rootEl");
const trackEl = useTemplateRef<HTMLElement>("trackEl");
const scrollerEl = useTemplateRef<HTMLElement>("scrollerEl");
const axisEl = useTemplateRef<HTMLElement>("axisEl");
const vaxisEl = useTemplateRef<HTMLElement>("vaxisEl");

const armed = ref(false);
const view = ref<"rail" | "plan">("rail");
const anchorDate = ref(""); // ISO day, "" until placed
const ghost = ref<{ x: number; label: string } | null>(null);
const doneIds = reactive<Record<string, boolean>>({});

const placed = computed(() => anchorDate.value !== "");

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
function offsetLabel(offsetDays: number | null): string {
  if (offsetDays === null) return "Frist noch nicht recherchiert";
  if (offsetDays === 0) return "Umzugstag";
  return offsetDays < 0 ? `${Math.abs(offsetDays)} Tage vorher` : `${offsetDays} Tage danach`;
}

const variant = computed<PlanVariant>(() => ({
  slug: "umzug",
  label: "Umzug",
  regionCode: props.regionCode,
  deadlines: props.deadlines,
}));
const workingDeadlines = computed(() => props.deadlines);

const { tasks, railNodes, stats } = usePlannerSchedule(
  anchorDate,
  variant,
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
    .flatMap((y) => holidaysFor(y, COUNTRY_CODE, props.regionCode))
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
  for (const k of Object.keys(doneIds)) delete doneIds[k];
  nextTick(() => {
    scrollerEl.value?.scrollTo({ left: Math.max(0, px(d) - 120), behavior: "smooth" });
  });
}
function resetPlaced() {
  anchorDate.value = "";
  for (const k of Object.keys(doneIds)) delete doneIds[k];
  armed.value = true;
}
function toggleDone(id: string) {
  doneIds[id] = !doneIds[id];
}

/* ---------- Der 90°-Übergang ---------- */
async function morph(toPlan: boolean) {
  if (!rootEl.value) {
    view.value = toPlan ? "plan" : "rail";
    return;
  }
  const fromAttr = toPlan ? "data-node-key" : "data-dot-key";
  const toAttr = toPlan ? "data-dot-key" : "data-node-key";

  const first = new Map<string, DOMRect>();
  rootEl.value.querySelectorAll<HTMLElement>(`[${fromAttr}]`).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width) first.set(el.getAttribute(fromAttr)!, r);
  });
  const fromAxisEl = toPlan ? axisEl.value : vaxisEl.value;
  const axFrom = fromAxisEl?.getBoundingClientRect();
  // scrollTo(top:0) below moves the viewport before "last"/axTo get measured,
  // so "first"/axFrom (still in the pre-scroll frame) need this offset to
  // land in the same frame as the post-scroll measurements - otherwise every
  // fixed-position flier launches off by however far the page had scrolled.
  const dy = window.scrollY;

  view.value = toPlan ? "plan" : "rail";
  window.scrollTo({ top: 0 });
  await nextTick();

  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !axFrom) return;

  const toAxisEl = toPlan ? vaxisEl.value : axisEl.value;
  const axTo = toAxisEl?.getBoundingClientRect();
  if (!axTo) return;

  const last = new Map<string, DOMRect>();
  const targets = rootEl.value.querySelectorAll<HTMLElement>(`[${toAttr}]`);
  targets.forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width) last.set(el.getAttribute(toAttr)!, r);
  });

  const line = document.createElement("div");
  line.className = "wom-flyaxis";
  line.style.left = axFrom.left + "px";
  line.style.top = axFrom.top + dy + "px";
  line.style.width = Math.max(axFrom.width, axFrom.height) + "px";
  line.style.height = "1px";
  const horizFirst = axFrom.width > axFrom.height;
  document.body.appendChild(line);
  line
    .animate(
      [
        { transform: `rotate(${horizFirst ? 0 : 90}deg) scaleX(1)`, opacity: 0.9 },
        {
          transform: `translate(${axTo.left - axFrom.left}px,${axTo.top - (axFrom.top + dy)}px) rotate(${horizFirst ? 90 : 0}deg) scaleX(${Math.max(axTo.width, axTo.height) / Math.max(axFrom.width, axFrom.height)})`,
          opacity: 0,
        },
      ],
      { duration: 620, easing: "cubic-bezier(.65,0,.2,1)" },
    )
    .addEventListener("finish", () => line.remove());

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

  rootEl.value
    .querySelectorAll<HTMLElement>(toPlan ? ".vcard, .vwhen" : ".row")
    .forEach((el, n) =>
      el.animate(
        [
          { opacity: 0, transform: `translate${toPlan ? "X" : "Y"}(${toPlan ? 18 : 10}px)` },
          { opacity: 1, transform: "none" },
        ],
        { duration: 420, delay: 180 + n * 26, easing: "cubic-bezier(.2,.8,.3,1)", fill: "backwards" },
      ),
    );
}
function openPlan() {
  morph(true);
}
function backToRail() {
  morph(false);
}
</script>

<style scoped>
.wom-timeline {
  --done-color: #3f7d4a;
}
:global(:root[data-theme="dark"] .wom-timeline) {
  --done-color: #7cc98a;
}

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

/* ============ Ansicht B: Zeitplan ============ */
.plan-view {
  padding-top: 0.5rem;
}
.back {
  background: none;
  border: 0;
  color: var(--accent);
  font-size: 0.9rem;
  padding: 0;
  margin-bottom: 0.9rem;
}
.plan-view h1 {
  font-size: clamp(1.5rem, 4vw, 2rem);
  margin-bottom: 0.3rem;
}
.meta {
  color: var(--muted);
  margin-bottom: 0.5rem;
}
.summary {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.summary b {
  color: var(--ink);
}
.warn-count {
  color: var(--warn);
}

.vrail {
  position: relative;
  padding-left: 8.5rem;
  margin-top: 1.5rem;
}
.vaxis {
  position: absolute;
  left: 6.6rem;
  top: 0.5rem;
  bottom: 0.5rem;
  width: 1px;
  background: var(--line);
}
.vitem {
  position: relative;
}
.vwhen {
  position: absolute;
  left: -8.5rem;
  top: 0.75rem;
  width: 6.6rem;
  text-align: right;
  padding-right: 1.75rem;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.vwhen b {
  display: block;
  font-weight: 600;
  font-size: 0.78rem;
}
.vwhen span {
  color: var(--muted);
  font-size: 0.66rem;
}
.vdot {
  position: absolute;
  left: -2.15rem;
  top: 1.05rem;
  width: 0.8rem;
  height: 0.8rem;
  border-radius: 50%;
  background: var(--paper-raised);
  border: 2px solid var(--accent);
}
.vitem.warn .vdot {
  border-color: var(--warn);
}
.vitem.done .vdot {
  background: var(--done-color);
  border-color: var(--done-color);
}
.vcard {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 0.85rem 1.1rem;
}
.vitem.warn .vcard {
  border-color: var(--warn);
}
.vcard h3 {
  margin: 0 0 0.2rem;
  border: 0;
  padding: 0;
  font-size: 1rem;
  padding-right: 2rem;
}
.vcard p {
  margin: 0.2rem 0 0;
  color: var(--muted);
  font-size: 0.89rem;
}
.vcheck {
  position: absolute;
  left: -4rem;
  top: 0.85rem;
  width: 1.1rem;
  height: 1.1rem;
  color: var(--done-color);
  font-size: 0.75rem;
  line-height: 1;
  padding: 0;
}
.vitem.done .vcheck {
  background: var(--done-color);
  color: var(--accent-ink);
  border-color: var(--done-color);
}
.vitem.done .vcard h3 {
  text-decoration: line-through;
  color: var(--muted);
}
.flag {
  margin-top: 0.6rem;
  padding: 0.4rem 0.7rem;
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  border-left: 2px solid var(--warn);
  color: var(--ink);
  font-size: 0.85rem;
}
.pause {
  position: relative;
  height: 2.1rem;
}
.pause span {
  position: absolute;
  left: 0;
  top: 0.55rem;
  font-family: var(--font-mono);
  font-size: 0.62rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  background: var(--paper);
  padding: 0 0.5rem;
  margin-left: -1.75rem;
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
:global(.wom-flyaxis) {
  position: fixed;
  background: var(--line);
  z-index: 59;
  pointer-events: none;
  transform-origin: 0 0;
}

@media (max-width: 54rem) {
  .vrail {
    padding-left: 0;
  }
  .vaxis {
    left: 0.3rem;
  }
  .vwhen {
    position: static;
    width: auto;
    text-align: left;
    padding: 0 0 0.4rem 1.9rem;
    display: flex;
    gap: 0.5rem;
  }
  .vdot {
    left: 0;
    top: 0.3rem;
  }
  .vcard {
    margin-left: 1.9rem;
  }
  .vcheck {
    position: static;
    margin: 0 0 0.5rem 1.9rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}
</style>
