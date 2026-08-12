<template>
  <div
    class="timeline"
    :class="{ armed: clickable }"
    :style="{ '--tl-t': shrink }"
  >
    <div v-if="showLegend" class="legend">
      <div class="keys">
        <span class="item"><span class="capsule"></span> möglich ab – Frist</span>
        <span class="item"><span class="ring"></span> offen</span>
        <span class="item"
          ><span class="ring late"></span> überfällig</span
        >
        <span class="item"><span class="dot"></span> erledigt</span>
      </div>
      <div class="filters" role="group" aria-label="Bänder einblenden">
        <span class="item"><span class="swatch werktag"></span> Werktag</span>
        <span class="item"
          ><span class="swatch wochenende"></span> Wochenende</span
        >
        <label class="item">
          <input v-model="showFeiertage" type="checkbox" />
          <span class="swatch feiertag"></span> Feiertage
        </label>
        <label class="item">
          <input v-model="showSchulferien" type="checkbox" />
          <span class="swatch ferien"></span> Schulferien
        </label>
      </div>
      <p v-if="L.laneCount > 1" class="lanes-note">
        Termine stehen in mehreren Zeilen, damit sich nahe Fristen nicht
        überdecken. Die Zeile hat keine Bedeutung.
      </p>
    </div>

    <figure ref="figureEl" class="figure">
      <svg
        :viewBox="`0 0 ${L.w} ${L.height}`"
        :width="L.w"
        :height="L.height"
        role="img"
        :aria-label="`Zeitstrahl mit allen Fristen bis zum ${anchorName}`"
        @mousemove="onMove"
        @mouseleave="clearGhost"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerCancel"
      >
        <g>
          <rect
            v-for="r in L.bandRuns"
            :key="'b' + r.x"
            :x="r.x"
            :y="L.bandTop"
            :width="r.width"
            :height="L.m.bandH"
            :class="'band ' + r.type"
          />
          <rect
            class="band-frame"
            :x="L.xLeft(L.from)"
            :y="L.bandTop"
            :width="L.xLeft(L.to + 1) - L.xLeft(L.from)"
            :height="L.m.bandH"
          />
        </g>

        <g class="ticks">
          <line
            v-for="x in L.weekTicks"
            :key="'w' + x"
            :x1="x"
            :y1="L.axisY"
            :x2="x"
            :y2="L.axisY + L.m.tickH"
          />
          <line
            v-for="m in L.months.slice(1)"
            :key="'mt' + m.x"
            :x1="m.x"
            :y1="L.axisY - 5"
            :x2="m.x"
            :y2="L.bandTop + L.m.bandH"
          />
        </g>

        <line
          class="axis"
          :x1="L.m.padX"
          :y1="L.axisY"
          :x2="L.w - L.m.padX"
          :y2="L.axisY"
        />

        <g>
          <template v-for="it in L.items" :key="'c' + it.id">
            <rect
              v-if="it.x0 !== null"
              class="window"
              :class="it.status"
              :x="it.x0"
              :y="it.cy - L.m.markerR"
              :width="Math.max(L.m.markerR * 2, it.cx - it.x0)"
              :height="L.m.markerR * 2"
              :rx="L.m.markerR"
            />
          </template>
        </g>

        <g class="anchors">
          <line
            class="rule today"
            :x1="L.todayX"
            :y1="L.m.headTop"
            :x2="L.todayX"
            :y2="L.bandTop + L.m.bandH"
          />
          <line
            class="rule event"
            :x1="L.eventX"
            :y1="L.m.headTop"
            :x2="L.eventX"
            :y2="L.bandTop + L.m.bandH"
          />
          <path class="flag" :d="flagPath(L.eventX)" />
          <line
            v-if="ghost"
            class="rule ghost"
            :x1="ghost.x"
            :y1="L.m.headTop"
            :x2="ghost.x"
            :y2="L.bandTop + L.m.bandH"
          />
        </g>

        <g class="labels">
          <text
            v-for="m in L.months"
            :key="'ml' + m.x"
            class="axis-label"
            :x="m.mid"
            :y="L.monthTop + 18 - 5 * shrink"
            text-anchor="middle"
          >
            {{ m.label }}
          </text>
          <text class="anchor-label today" :x="L.todayX + 8" :y="L.m.labelY">
            HEUTE
          </text>
          <text
            v-if="todayDateLabel"
            class="axis-label today"
            :x="L.todayX + 8"
            :y="L.m.labelY + 16"
            :opacity="Math.max(0, 1 - shrink * 2)"
          >
            {{ todayDateLabel }}
          </text>
          <text
            class="anchor-label event"
            :x="L.eventFlip ? L.eventX - 8 : L.eventX + 32"
            :y="L.m.labelY"
            :text-anchor="L.eventFlip ? 'end' : 'start'"
          >
            {{ anchorName.toUpperCase() }}
          </text>
          <text
            class="axis-label event"
            :x="L.eventFlip ? L.eventX - 8 : L.eventX + 32"
            :y="L.m.labelY + 16"
            :text-anchor="L.eventFlip ? 'end' : 'start'"
            :opacity="Math.max(0, 1 - shrink * 2)"
          >
            {{ anchorDateLabel }}
          </text>
          <text
            v-if="ghost"
            class="anchor-label ghost"
            :x="ghost.x + 8"
            :y="L.m.labelY + 32"
          >
            {{ ghost.label }}
          </text>
        </g>

        <g class="markers">
          <g
            v-for="it in L.items"
            :key="'m' + it.id"
            class="marker"
            tabindex="0"
            role="button"
            :data-node-key="keyed ? it.id : null"
            :aria-label="`${it.label}. Frist ${dayShort(it.deadline)}. ${STATE_WORD[it.status]}.`"
            @click.stop="emit('select', it.id)"
            @keydown.enter.prevent="emit('select', it.id)"
            @keydown.space.prevent="emit('select', it.id)"
            @mouseenter="onMarkerEnter(it)"
            @focus="onMarkerEnter(it)"
            @mouseleave="onMarkerLeave"
            @blur="onMarkerLeave"
          >
            <circle class="hit" :cx="it.cx" :cy="it.cy" :r="L.m.markerR + 9" />
            <circle
              v-if="it.id === hoverId"
              class="halo"
              :class="it.status"
              :cx="it.cx"
              :cy="it.cy"
              :r="L.m.markerR + 4"
            />
            <circle
              class="marker-dot"
              :class="it.status"
              :cx="it.cx"
              :cy="it.cy"
              :r="L.m.markerR"
            />
          </g>
        </g>

        <g
          v-if="movable"
          class="grip"
          tabindex="0"
          role="slider"
          :aria-label="`${anchorName} wählen`"
          :aria-valuemin="MIN_DAY"
          :aria-valuemax="MAX_DAY"
          :aria-valuenow="anchorDay"
          :aria-valuetext="dayLong(anchorDay)"
          :data-node-key="keyed ? ANCHOR_ID : null"
          @keydown="onKey"
        >
          <title>{{ dragHint }}</title>
          <circle :cx="L.eventX" :cy="L.axisY" :r="L.m.markerR + 2" />
        </g>
      </svg>

      <div
        v-if="tip"
        class="tip"
        :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
      >
        <strong>{{ tip.title }}</strong>
        <span class="tip-date">{{ tip.sub }}</span>
      </div>
    </figure>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  useTemplateRef,
  watch,
} from "vue";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { MONTH_NAMES, longDate, shortDate } from "../../../lib/date-display";
import { holidaysFor } from "../../../lib/holidays";
import {
  dateOfDay,
  dayNum,
  dow,
  isWeekend,
  isoOfDay,
  monthFirsts,
  monthWindow,
  packLanes,
} from "../../../lib/timeline-geometry";
import { ANCHOR_ID, COUNTRY_CODE } from "./usePlannerSchedule";

const props = withDefaults(
  defineProps<{
    tasks: ScheduleEntry[];
    anchorDate: string;
    anchorName: string;
    regionCode?: string;
    clickable?: boolean;
    draggable?: boolean;
    keyed?: boolean;
    compact?: boolean;
    hoverId?: string | null;
    dragHint?: string;
    showLegend?: boolean;
    doneIds?: Record<string, boolean>;
  }>(),
  {
    clickable: false,
    draggable: false,
    keyed: false,
    compact: false,
    hoverId: null,
    dragHint: "",
    showLegend: true,
    doneIds: () => ({}),
  },
);

const emit = defineEmits<{
  place: [iso: string];
  select: [id: string];
  hover: [id: string | null];
  preview: [iso: string | null];
}>();

const FULL = {
  padX: 14,
  headTop: 22,
  labelY: 16,
  headroom: 54,
  laneH: 30,
  markerR: 7,
  axisGap: 12,
  bandH: 16,
  monthH: 26,
  minGap: 8,
  tickH: 6,
};
const COMPACT = {
  ...FULL,
  headTop: 14,
  labelY: 11,
  headroom: 30,
  laneH: 22,
  markerR: 5.5,
  axisGap: 8,
  bandH: 11,
  monthH: 18,
  minGap: 6,
  tickH: 4,
};

const STATE_WORD = {
  offen: "offen",
  erledigt: "erledigt",
  ueberfaellig: "überfällig",
} as const;
type Status = keyof typeof STATE_WORD;

const shrink = ref(0);
let tween = 0;
watch(
  () => props.compact,
  (to) => {
    const from = shrink.value;
    const target = to ? 1 : 0;
    if (typeof requestAnimationFrame === "undefined") {
      shrink.value = target;
      return;
    }
    cancelAnimationFrame(tween);
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      shrink.value = target;
      return;
    }
    const t0 = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / 220);
      const eased = p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2;
      shrink.value = from + (target - from) * eased;
      if (p < 1) tween = requestAnimationFrame(step);
    };
    tween = requestAnimationFrame(step);
  },
  { immediate: true },
);
onBeforeUnmount(() => cancelAnimationFrame(tween));

const metrics = computed(() => {
  const out = { ...FULL };
  for (const key of Object.keys(FULL) as (keyof typeof FULL)[])
    out[key] = FULL[key] + (COMPACT[key] - FULL[key]) * shrink.value;
  return out;
});

const today = dayNum(new Date().toISOString().slice(0, 10));
const MIN_DAY = today - 14;
const MAX_DAY = today + 365;

const figureEl = useTemplateRef<HTMLElement>("figureEl");
const width = ref(900);
let resizeObserver: ResizeObserver | undefined;
onMounted(() => {
  const el = figureEl.value;
  if (!el) return;
  width.value = el.clientWidth || 900;
  resizeObserver = new ResizeObserver(() => {
    width.value = el.clientWidth || width.value;
  });
  resizeObserver.observe(el);
});
onBeforeUnmount(() => resizeObserver?.disconnect());

const showFeiertage = ref(true);
const showSchulferien = ref(true);
const ghost = ref<{ x: number; label: string } | null>(null);
const tip = ref<{ x: number; y: number; title: string; sub: string } | null>(
  null,
);

const anchorDay = computed(() =>
  props.anchorDate ? dayNum(props.anchorDate) : today,
);
const movable = computed(() => props.clickable || props.draggable);

function dayShort(n: number): string {
  return shortDate(isoOfDay(n));
}
function dayLong(n: number): string {
  return longDate(isoOfDay(n));
}

function labelW(text: string): number {
  return text.length * (13 - 2 * shrink.value) * 0.6;
}

const anchorDateLabel = computed(() => {
  const l = L.value;
  const room = l.eventFlip
    ? l.eventX - 8 - (l.todayX + 8 + labelW(dayShort(today)) + 12)
    : l.w - (l.eventX + 32);
  const long = dayLong(anchorDay.value);
  return labelW(long) < room ? long : dayShort(anchorDay.value);
});

const todayDateLabel = computed(() => {
  const l = L.value;
  const text = dayShort(today);
  const anchorLeft = l.eventFlip
    ? l.eventX - 8 - labelW(anchorDateLabel.value)
    : l.eventX + 32;
  return l.todayX + 8 + labelW(text) + 8 < anchorLeft ? text : "";
});

const dated = computed(() =>
  props.tasks
    .filter((t): t is ScheduleEntry & { date: string } => t.date !== null)
    .map((t) => {
      const deadline = dayNum(t.date);
      const earliest = t.earliestDate ? dayNum(t.earliestDate) : deadline;
      const status: Status = props.doneIds[t.id]
        ? "erledigt"
        : deadline < today
          ? "ueberfaellig"
          : "offen";
      return {
        id: t.id,
        label: t.label,
        deadline,
        start: earliest < deadline ? earliest : null,
        status,
      };
    })
    .filter((t) => t.deadline >= MIN_DAY - 60 && t.deadline <= MAX_DAY + 60)
    .sort((a, b) => a.deadline - b.deadline),
);

const span = computed(() =>
  monthWindow([
    today,
    anchorDay.value,
    ...dated.value.map((t) => t.deadline),
    ...dated.value.flatMap((t) => (t.start === null ? [] : [t.start])),
  ]),
);

const holidayDays = computed(() => {
  const map = new Map<number, string>();
  for (
    let y = dateOfDay(span.value.from).getUTCFullYear();
    y <= dateOfDay(span.value.to).getUTCFullYear();
    y++
  )
    for (const h of holidaysFor(y, COUNTRY_CODE, props.regionCode))
      map.set(dayNum(h.date), h.name);
  return map;
});

const ferien = ref<{ from: number; to: number }[]>([]);
watch(
  () => props.regionCode,
  async (code) => {
    ferien.value = [];
    if (!code) return;
    try {
      const res = await fetch(
        `/api/v1/calendar/schulferien--${code.toLowerCase()}.json`,
      );
      if (!res.ok) return;
      const entry = await res.json();
      ferien.value = (entry?.windows ?? []).map(
        (w: { from: string; to: string }) => ({
          from: dayNum(w.from),
          to: dayNum(w.to),
        }),
      );
    } catch {
    }
  },
  { immediate: true },
);

function dayType(d: number): string {
  if (showFeiertage.value && holidayDays.value.has(d)) return "feiertag";
  if (
    showSchulferien.value &&
    ferien.value.some((f) => d >= f.from && d <= f.to)
  )
    return "ferien";
  if (isWeekend(d)) return "wochenende";
  return "werktag";
}

const L = computed(() => {
  const m = metrics.value;
  const { from, to } = span.value;
  const w = width.value;
  const unit = (w - m.padX * 2) / (to - from + 1);
  const xLeft = (d: number) => m.padX + (d - from) * unit;
  const xCenter = (d: number) => xLeft(d) + unit / 2;

  const placed = dated.value
    .map((t) => {
      const cx = xCenter(t.deadline);
      const x0 = t.start === null ? null : xLeft(t.start);
      return {
        ...t,
        cx,
        x0,
        left: (x0 ?? cx) - m.markerR,
        right: cx + m.markerR,
      };
    })
    .sort((a, b) => a.left - b.left);
  const lanes = packLanes(placed, m.minGap);
  const laneCount = Math.max(1, ...lanes.map((l) => l + 1));
  const items = placed.map((p, i) => ({
    ...p,
    cy: m.headroom + lanes[i] * m.laneH + m.laneH / 2,
  }));

  const axisY = m.headroom + laneCount * m.laneH + m.axisGap;
  const bandTop = axisY + m.axisGap;
  const monthTop = bandTop + m.bandH;

  const bandRuns: { x: number; width: number; type: string }[] = [];
  let runStart = from;
  let runType = dayType(from);
  for (let d = from + 1; d <= to + 1; d++) {
    const t = d <= to ? dayType(d) : "";
    if (t === runType) continue;
    const x = Math.round(xLeft(runStart));
    bandRuns.push({
      x,
      width: Math.max(1, Math.round(xLeft(d)) - x),
      type: runType,
    });
    runStart = d;
    runType = t;
  }

  const weekTicks: number[] = [];
  for (let d = from; d <= to; d++)
    if (dow(d) === 1) weekTicks.push(Math.round(xLeft(d)) + 0.5);

  const months = monthFirsts(from, to).map((first) => {
    const d = dateOfDay(first);
    const next = dayNum(
      new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))
        .toISOString()
        .slice(0, 10),
    );
    return {
      x: Math.round(xLeft(first)) + 0.5,
      mid: (xLeft(Math.max(first, from)) + xLeft(Math.min(next, to + 1))) / 2,
      label: MONTH_NAMES[d.getUTCMonth()].slice(0, 3),
    };
  });

  const eventX = Math.round(xCenter(anchorDay.value)) + 0.5;
  return {
    m,
    w,
    from,
    to,
    unit,
    xLeft,
    items,
    laneCount,
    axisY,
    bandTop,
    monthTop,
    height: monthTop + m.monthH,
    bandRuns,
    weekTicks,
    months,
    todayX: Math.round(xCenter(today)) + 0.5,
    eventX,
    eventFlip: eventX > w - 170,
  };
});

function flagPath(x: number): string {
  const top = L.value.m.headTop - (14 - 4 * shrink.value);
  return `M ${x} ${top} h 26 l -6 7 l 6 7 h -26 z`;
}

function dayAt(clientX: number): number {
  const box = figureEl.value?.getBoundingClientRect();
  if (!box) return anchorDay.value;
  const d =
    L.value.from +
    Math.floor((clientX - box.left - L.value.m.padX) / L.value.unit);
  return Math.min(MAX_DAY, Math.max(MIN_DAY, d));
}
function place(d: number) {
  emit("place", isoOfDay(Math.min(MAX_DAY, Math.max(MIN_DAY, d))));
}
function setGhost(d: number) {
  ghost.value = { x: L.value.xLeft(d), label: dayShort(d) };
  emit("preview", isoOfDay(d));
}
function clearGhost() {
  ghost.value = null;
  emit("preview", null);
}

function onMove(e: MouseEvent) {
  if (!props.clickable || dragging) return;
  setGhost(dayAt(e.clientX));
}

let dragging = false;
function onPointerDown(e: PointerEvent) {
  const onGrip = !!(e.target as Element).closest?.(".grip");
  if (!movable.value || (!props.clickable && !onGrip)) return;
  dragging = true;
  (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
  setGhost(dayAt(e.clientX));
  e.preventDefault();
}
function onPointerMove(e: PointerEvent) {
  if (!dragging) return;
  setGhost(dayAt(e.clientX));
}
function onPointerUp(e: PointerEvent) {
  if (!dragging) return;
  dragging = false;
  const d = dayAt(e.clientX);
  clearGhost();
  place(d);
}
function onPointerCancel() {
  dragging = false;
  clearGhost();
}

const KEY_STEPS: Record<string, number> = {
  ArrowLeft: -1,
  ArrowDown: -1,
  ArrowRight: 1,
  ArrowUp: 1,
};
function onKey(e: KeyboardEvent) {
  if (!movable.value) return;
  let next: number | null = null;
  if (e.key === "Home") next = MIN_DAY;
  else if (e.key === "End") next = MAX_DAY;
  else if (e.key === "PageDown") next = anchorDay.value - 30;
  else if (e.key === "PageUp") next = anchorDay.value + 30;
  else if (e.key in KEY_STEPS)
    next = anchorDay.value + KEY_STEPS[e.key] * (e.shiftKey ? 7 : 1);
  if (next === null) return;
  e.preventDefault();
  place(next);
}

function onMarkerEnter(it: {
  id: string;
  cx: number;
  cy: number;
  label: string;
  deadline: number;
  start: number | null;
}) {
  emit("hover", it.id);
  tip.value = {
    x: Math.min(Math.max(it.cx, 135), L.value.w - 135),
    y: it.cy - L.value.m.markerR - 8,
    title: it.label,
    sub:
      `Frist: ${dayShort(it.deadline)}` +
      (it.start === null ? "" : ` · möglich ab ${dayShort(it.start)}`),
  };
}
function onMarkerLeave() {
  emit("hover", null);
  tip.value = null;
}
</script>

<style scoped>
.timeline {
  --d-werktag: var(--paper-raised);
  --d-wochenende: color-mix(in srgb, var(--ink) 22%, var(--paper-raised));
  --d-ferien: color-mix(in srgb, var(--accent) 22%, var(--paper-raised));
  --d-feiertag: color-mix(in srgb, var(--holiday) 45%, var(--paper-raised));
}
.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem 1.1rem;
  font-size: var(--fs-xs);
  color: var(--muted);
  overflow: hidden;
  max-height: calc((1 - var(--tl-t, 0)) * 6rem);
  opacity: calc(1 - var(--tl-t, 0) * 1.6);
  margin-bottom: calc((1 - var(--tl-t, 0)) * 0.7rem);
}
.keys,
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 1.1rem;
}
.filters {
  gap: 0.4rem 0.9rem;
  padding: 0.15rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}
.legend .item {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.legend label {
  cursor: pointer;
}
.legend input {
  accent-color: var(--accent);
  margin: 0;
}
.swatch {
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 2px;
  border: 1px solid var(--line);
}
.swatch.werktag {
  background: var(--d-werktag);
}
.swatch.wochenende {
  background: var(--d-wochenende);
}
.swatch.feiertag {
  background: var(--d-feiertag);
}
.lanes-note {
  flex-basis: 100%;
  margin: 0;
}
.swatch.ferien {
  background: var(--d-ferien);
}
.ring,
.dot {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
}
.ring {
  border: 2.5px solid var(--accent);
  background: var(--paper-raised);
}
.ring.late {
  border-color: var(--warn);
}
.dot {
  background: var(--done-color);
}
.capsule {
  width: 1.9rem;
  height: 0.75rem;
  border-radius: 999px;
  border: 2px solid var(--accent);
  background: var(--paper-raised);
}

.figure {
  position: relative;
  margin: 0;
}
.figure svg {
  display: block;
  width: 100%;
  overflow: visible;
}
.figure svg {
  touch-action: pan-y;
}
.armed .figure svg {
  cursor: copy;
}

.band.werktag {
  fill: var(--d-werktag);
}
.band.wochenende {
  fill: var(--d-wochenende);
}
.band.ferien {
  fill: var(--d-ferien);
}
.band.feiertag {
  fill: var(--d-feiertag);
}
.band-frame {
  fill: none;
  stroke: var(--line);
  stroke-width: 1;
}
.ticks line {
  stroke: var(--line);
  stroke-width: 1;
}
.axis {
  stroke: var(--line);
  stroke-width: 2;
  stroke-linecap: round;
}

.window {
  fill: var(--paper-raised);
  stroke: var(--accent);
  stroke-width: 2;
}
.window.erledigt {
  fill: none;
  stroke: var(--done-color);
  opacity: 0.5;
}
.window.ueberfaellig {
  stroke: var(--warn);
}

.marker {
  cursor: pointer;
}
.marker:focus {
  outline: none;
}
.hit {
  fill: transparent;
}
.marker:focus-visible .hit {
  fill: none;
  stroke: var(--accent);
  stroke-width: 2.5;
}
.marker-dot {
  fill: var(--paper-raised);
  stroke: var(--accent);
  stroke-width: 2.5;
}
.marker-dot.erledigt {
  fill: var(--done-color);
  stroke: var(--done-color);
}
.marker-dot.ueberfaellig {
  stroke: var(--warn);
}
.halo {
  fill: var(--accent);
  opacity: 0.18;
  transform-box: fill-box;
  transform-origin: center;
  animation: halo-pulse 1.6s ease-in-out infinite;
}
.halo.ueberfaellig {
  fill: var(--warn);
}
.halo.erledigt {
  fill: var(--done-color);
}
@keyframes halo-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.18;
  }
  50% {
    transform: scale(1.45);
    opacity: 0.07;
  }
}
@media (prefers-reduced-motion: reduce) {
  .halo {
    animation: none;
  }
}
.halo.erledigt {
  fill: var(--done-color);
}
.halo.ueberfaellig {
  fill: var(--warn);
}

.rule {
  stroke-width: 1.5;
}
.rule.today {
  stroke: var(--today);
  stroke-dasharray: 3 3;
}
.rule.event {
  stroke: var(--anchor);
  stroke-width: 2;
}
.rule.ghost {
  stroke: var(--anchor);
  opacity: 0.45;
}
.flag {
  fill: var(--anchor);
}
.grip circle {
  fill: var(--paper-raised);
  stroke: var(--anchor);
  stroke-width: 3;
  cursor: grab;
  touch-action: none;
}
.grip:focus-visible circle {
  stroke: var(--accent);
}

.axis-label {
  font-family: var(--font-mono);
  font-size: calc(13px - 2px * var(--tl-t, 0));
  fill: var(--muted);
}
.axis-label.event {
  fill: var(--anchor);
  opacity: 0.85;
}
.anchor-label {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: calc(13px - 2px * var(--tl-t, 0));
  letter-spacing: 0.04em;
}
.anchor-label.today {
  fill: var(--today);
}
.anchor-label.event,
.anchor-label.ghost {
  fill: var(--anchor);
}

.tip {
  position: absolute;
  z-index: 5;
  pointer-events: none;
  transform: translate(-50%, -100%);
  background: var(--ink);
  color: var(--paper);
  padding: 0.4rem 0.6rem;
  border-radius: var(--radius-sm);
  font-size: var(--fs-xs);
  line-height: 1.35;
  max-width: 15rem;
}
.tip-date {
  display: block;
  margin-top: 2px;
  font-family: var(--font-mono);
  opacity: 0.75;
}
</style>
