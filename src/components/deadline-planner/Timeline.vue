<template>
  <div
    class="timeline"
    :class="{ armed: clickable, compact }"
    :style="rootVars"
  >
    <div v-if="showLegend" class="legend">
      <label class="legend-item">
        <input type="checkbox" v-model="showFeiertage" />
        <span class="swatch feiertage"></span>
        Feiertage
      </label>
      <label class="legend-item">
        <input type="checkbox" v-model="showSchulferien" />
        <span class="swatch schulferien"></span>
        Schulferien
      </label>
    </div>

    <div
      class="scroller"
      ref="scrollerEl"
      @mousemove="onScrollerMove"
      @mouseleave="ghost = null"
      @click="onScrollerClick"
    >
      <div class="track" ref="trackEl" :style="{ width: trackWidth + 'px' }">
        <div class="axis"></div>

        <!-- Day ruler as a single repeating gradient instead of ~470 divs.
          Dropped once the scale is tight enough that the lines would read as
          moire rather than as days. -->
        <div v-if="showDayTicks" class="days"></div>

        <div
          v-for="x in weekTicks"
          :key="'wt' + x"
          class="wtick"
          :style="{ left: x + 'px' }"
        ></div>
        <div
          v-for="t in monthTicks"
          :key="'mt' + t.x"
          class="mtick"
          :style="{ left: t.x + 'px' }"
        ></div>
        <div
          v-for="t in monthTicks"
          v-show="t.labelled"
          :key="'ml' + t.x"
          class="mlabel"
          :style="{ left: t.x + 'px' }"
        >
          {{ t.label }}
        </div>

        <!-- Feiertage/Schulferien live in their own strip below the ruler, so
          calendar context can never be mistaken for a ruler tick and the
          area above the axis belongs entirely to the task nodes. -->
        <template v-if="showSchulferien">
          <div
            v-for="w in schulferienBands"
            :key="'sf' + w.from"
            class="band schulferien"
            :title="w.description"
            :style="{ left: w.x + 'px', width: w.width + 'px' }"
          ></div>
        </template>
        <template v-if="showFeiertage">
          <div
            v-for="h in holidayTicks"
            :key="h.date"
            class="htick"
            :title="h.name"
            :style="{ left: h.x + 'px' }"
          ></div>
        </template>

        <div class="today" :style="{ left: todayX + 'px' }">
          <b>HEUTE</b>
        </div>

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
            :class="{
              warn: t.weekend || t.collision,
              current: t.date === highlightDate,
              hovered: t.id === hoverId,
              impossible: t.impossible,
              done: doneIds[t.id],
              span: barWidth(t) > 0,
            }"
            :style="{
              left: nodeLeft(t) + 'px',
              width: nodeWidth(t) + 'px',
              '--lane': taskLane.get(t.id) ?? 0,
            }"
            :data-node-key="keyed ? t.id : null"
            :data-label="nodeLabel(t)"
            :aria-label="nodeLabel(t)"
            :title="
              compact ? `${nodeLabel(t)} - zur Aufgabe springen` : undefined
            "
            @click="onNodeClick(t.id, $event)"
            @mouseenter="emit('hover', t.id)"
            @mouseleave="emit('hover', null)"
          >
            <span
              v-if="t.startByDate !== t.date"
              class="start-by"
              :style="{ left: pxIso(t.startByDate!) - nodeLeft(t) + 'px' }"
            ></span>
          </button>
          <div
            class="pin"
            :class="{
              hovered: hoverId === ANCHOR_ID,
              done: doneIds[ANCHOR_ID],
              flip: pinFlipped,
            }"
            :style="{ left: pxIso(anchorDate) + 'px' }"
            :data-node-key="keyed ? ANCHOR_ID : null"
            :title="compact ? 'Zur Aufgabe springen' : undefined"
            @click="onNodeClick(ANCHOR_ID, $event)"
            @mouseenter="emit('hover', ANCHOR_ID)"
            @mouseleave="emit('hover', null)"
          >
            <b>{{ anchorName }}</b
            ><i>{{ pinLabel }}</i>
            <slot name="pin-extra" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  useTemplateRef,
  watch,
} from "vue";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { MONTH_NAMES, WEEKDAY_NAMES_SHORT } from "../../../lib/date-display";
import { toDate } from "../../../lib/format-date";
import { holidaysFor } from "../../../lib/holidays";
import {
  addDays,
  daysBetween,
  fitPpd,
  fitWindow,
  isoOf,
  laneCount,
  makeScale,
  mondays,
  monthStarts,
  packLanes,
  scrollTargetFor,
  utcDay,
} from "../../../lib/timeline-geometry";
import { ANCHOR_ID, COUNTRY_CODE } from "./usePlannerSchedule";

const props = withDefaults(
  defineProps<{
    tasks: ScheduleEntry[]; // schedule entries, anchor excluded, date may be null
    anchorDate: string; // ISO day, "" until placed
    anchorName: string; // bold pin label, e.g. "Umzug"
    regionCode?: string;
    clickable?: boolean; // click-to-place a new anchor date
    keyed?: boolean; // tag nodes with data-node-key (only one instance per page)
    compact?: boolean; // smaller strip, for use as an overview above the task list
    highlightDate?: string | null; // task date to mark as current and center on
    hoverId?: string | null; // task id (or ANCHOR_ID) to mark as hovered, set from outside
    showLegend?: boolean; // Feiertage/Schulferien toggle row
    doneIds?: Record<string, boolean>; // task id (or ANCHOR_ID) -> done, for the green "done" node fill
  }>(),
  {
    clickable: false,
    keyed: false,
    compact: false,
    highlightDate: null,
    hoverId: null,
    showLegend: true,
    doneIds: () => ({}),
  },
);

const emit = defineEmits<{
  place: [iso: string];
  select: [id: string];
  hover: [id: string | null];
}>();

// Two scales, one component. The full rail is a fixed 6px per day canvas the
// user scrolls and clicks a date on. The compact strip instead fits its own
// container, so when the overview widens on scroll the plan spreads out into
// the new width rather than unfolding further to the right.
const RAIL_PPD = 6;
const FIT_MIN_PPD = 2.2; // under this a dense plan is unreadable, so it scrolls instead
const EDGE_PX = 30; // px kept free at both ends for the first and last cap

// Node diameter lives here, not in CSS, because the lane packer needs the
// exact rendered geometry - it is handed to CSS as --node so the two can't
// drift apart.
const NODE_PX = computed(() => (props.compact ? 24 : 13));

const scrollerEl = useTemplateRef<HTMLElement>("scrollerEl");
const trackEl = useTemplateRef<HTMLElement>("trackEl");

const ghost = ref<{ x: number; label: string } | null>(null);
const showFeiertage = ref(true);
const showSchulferien = ref(true);

const placed = computed(() => props.anchorDate !== "");

// All internal days are UTC midnight (see lib/timeline-geometry). Mixing in
// locally-constructed dates made isoOf() and every ghost/pin label fall a day
// short of the clicked day in CET/CEST.
const today = utcDay(new Date());
const START = addDays(today, -14);
const END = addDays(START, Math.round(15 * 30.4));

// Measured, not guessed: the compact scale is a function of it.
const containerWidth = ref(0);
let resizeObserver: ResizeObserver | undefined;
onMounted(() => {
  const el = scrollerEl.value;
  if (!el) return;
  containerWidth.value = el.clientWidth;
  resizeObserver = new ResizeObserver(() => {
    containerWidth.value = el.clientWidth;
  });
  resizeObserver.observe(el);
});
onBeforeUnmount(() => resizeObserver?.disconnect());

// The compact strip drops the empty months at the ends of the 15 month canvas
// and shows exactly the days the plan occupies. Same tasks either way: the
// window is derived from the task dates themselves, so nothing that used to
// be on the rail can fall outside it. relevantDates is declared further down,
// which is fine, a computed only reads it once it is asked for a value.
const scale = computed(() => {
  if (!props.compact) return makeScale(START, END, RAIL_PPD);
  const window = fitWindow(today, relevantDates.value, START, END, 3, 45);
  // Server-rendered, before any element exists to measure: the fixed rail
  // scale is a far better first paint than the minimum.
  const ppd =
    containerWidth.value > 0
      ? fitPpd(
          daysBetween(window.start, window.end),
          containerWidth.value,
          FIT_MIN_PPD,
          EDGE_PX,
        )
      : RAIL_PPD;
  return makeScale(window.start, window.end, ppd, EDGE_PX);
});

function px(d: Date): number {
  return scale.value.x(d);
}
function pxIso(iso: string): number {
  return px(toDate(iso));
}
const trackWidth = computed(() => scale.value.width);
const todayX = computed(() => px(today));
// Day lines closer together than this read as moire, not as days.
const showDayTicks = computed(() => scale.value.ppd >= 4);

function shortDate(d: Date): string {
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()].slice(0, 3)}`;
}
function langDate(d: Date): string {
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
function weekdayShort(d: Date): string {
  return WEEKDAY_NAMES_SHORT[(d.getUTCDay() + 6) % 7];
}
function nodeLabel(t: ScheduleEntry & { date: string }): string {
  return `${shortDate(toDate(t.date))} · ${t.label}`;
}

// A node is a capsule from earliest-possible to the deadline. Both caps are
// centred on their day, so a task with no researched earliest day collapses
// to a single dot centred on its deadline - same formula, no min-width and
// no negative margin, which is what used to make wide bars start half a node
// too early and the lane packer disagree with what was on screen.
function barLeft(t: ScheduleEntry & { date: string }): number {
  return pxIso(t.earliestDate ?? t.date);
}
function barWidth(t: ScheduleEntry & { date: string }): number {
  return Math.max(0, pxIso(t.date) - barLeft(t));
}
function nodeLeft(t: ScheduleEntry & { date: string }): number {
  return barLeft(t) - NODE_PX.value / 2;
}
function nodeWidth(t: ScheduleEntry & { date: string }): number {
  return barWidth(t) + NODE_PX.value;
}

const datedTasks = computed(() =>
  props.tasks.filter(
    (t): t is ScheduleEntry & { date: string } => t.date !== null,
  ),
);
// Only tasks inside the printed [START, END] window get a dot on the rail -
// far-out ones (e.g. Rundfunkbeitrag, +1400 days) still count in the totals.
const visibleTasks = computed(() =>
  datedTasks.value.filter((t) => {
    const d = toDate(t.date);
    return d >= START && d <= END;
  }),
);

// Both ends of every task window plus the anchor - what the compact scale has
// to keep on screen. today is added by fitWindow itself.
const relevantDates = computed(() => {
  const out: Date[] = [];
  for (const t of visibleTasks.value) {
    out.push(toDate(t.date));
    if (t.earliestDate) out.push(toDate(t.earliestDate));
  }
  if (placed.value) out.push(toDate(props.anchorDate));
  return out;
});

// Waterfall packing on the rendered pixel spans, so two capsules share a lane
// exactly when they don't touch on screen (see lib/timeline-geometry).
const taskLane = computed(() =>
  packLanes(
    visibleTasks.value.map((t) => ({
      id: t.id,
      left: nodeLeft(t),
      width: nodeWidth(t),
    })),
    props.compact ? 3 : 4,
  ),
);
// The strip is only as tall as the deepest cluster actually needs. A plan
// with no overlaps gets a single-lane rail instead of always reserving room
// for three.
const usedLanes = computed(() => laneCount(taskLane.value));

// One source of truth for node size and lane count; every vertical offset in
// the stylesheet is derived from these two plus the tokens in .timeline.
const rootVars = computed(() => ({
  "--node": NODE_PX.value + "px",
  "--ppd": scale.value.ppd + "px",
  "--lanes": String(usedLanes.value),
}));

const threadStyle = computed(() => {
  if (!visibleTasks.value.length) return {};
  // min/max, not first/last - visibleTasks follows the props order, which is
  // not necessarily chronological.
  const xs = visibleTasks.value.map((t) => pxIso(t.date));
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  return { left: left + "px", width: Math.max(0, right - left) + "px" };
});

const pinLabel = computed(() =>
  placed.value
    ? `${weekdayShort(toDate(props.anchorDate))}, ${langDate(toDate(props.anchorDate))}`
    : "",
);
// The pin label reads to the right of its line. On the fitted strip an anchor
// near the end would push it past the track and clip it, so it mirrors.
const pinFlipped = computed(
  () =>
    props.compact &&
    placed.value &&
    trackWidth.value - pxIso(props.anchorDate) < 180,
);

// Week ticks (Monday-aligned) stay real elements so they keep their hover
// affordance; days are the gradient in .days.
const weekTicks = computed(() =>
  mondays(scale.value.start, scale.value.end).map(px),
);

const monthTicks = computed(() => {
  // A label needs roughly 3rem of clear space, so on a tight scale only every
  // nth month gets one. The ticks themselves always stay.
  const step = Math.max(1, Math.ceil(48 / (scale.value.ppd * 30.4)));
  return monthStarts(scale.value.start, scale.value.end).map((m, i) => ({
    x: px(m),
    labelled: i % step === 0,
    label:
      MONTH_NAMES[m.getUTCMonth()].slice(0, 3) +
      (m.getUTCMonth() === 0 ? " " + m.getUTCFullYear() : ""),
  }));
});

const holidayTicks = computed(() => {
  // Every year the window touches, not just its first and last - a 15-month
  // window starting in December spans three calendar years and used to drop
  // the middle one entirely.
  const years: number[] = [];
  for (
    let y = scale.value.start.getUTCFullYear();
    y <= scale.value.end.getUTCFullYear();
    y++
  ) {
    years.push(y);
  }
  return years
    .flatMap((y) => holidaysFor(y, COUNTRY_CODE, props.regionCode))
    .map((h) => ({ ...h, x: px(toDate(h.date)) }))
    .filter((h) => h.x >= 0 && h.x <= trackWidth.value);
});

// Schulferien has no npm package like date-holidays - it's fetched from the
// prebuilt /api/v1/calendar/schulferien--<code>.json (same static endpoint
// the sitewide Kalender uses), keyed by Bundesland and refetched on change.
const schulferienWindows = ref<
  { from: string; to: string; description: string }[]
>([]);
watch(
  () => props.regionCode,
  async (code) => {
    schulferienWindows.value = [];
    if (!code) return;
    try {
      const res = await fetch(
        `/api/v1/calendar/schulferien--${code.toLowerCase()}.json`,
      );
      if (!res.ok) return;
      const entry = await res.json();
      schulferienWindows.value = Array.isArray(entry?.windows)
        ? entry.windows
        : [];
    } catch {
      // best-effort - the strip just shows no school-holiday bands
    }
  },
  { immediate: true },
);
const schulferienBands = computed(() =>
  schulferienWindows.value
    .map((w) => ({
      ...w,
      x: px(toDate(w.from)),
      width: Math.max(2, px(toDate(w.to)) - px(toDate(w.from))),
    }))
    .filter((w) => w.x + w.width >= 0 && w.x <= trackWidth.value),
);

function onScrollerMove(e: MouseEvent) {
  if (!props.clickable || !trackEl.value) return;
  const r = trackEl.value.getBoundingClientRect();
  const x = e.clientX - r.left;
  const d = scale.value.dateAt(x);
  ghost.value = { x, label: `${weekdayShort(d)}, ${langDate(d)}` };
}
function onScrollerClick(e: MouseEvent) {
  if (!props.clickable || !trackEl.value) return;
  const r = trackEl.value.getBoundingClientRect();
  const d = scale.value.dateAt(e.clientX - r.left);
  ghost.value = null;
  emit("place", isoOf(d));
  nextTick(() => {
    scrollerEl.value?.scrollTo({
      left: Math.max(0, px(d) - 400),
      behavior: "smooth",
    });
  });
}

// The compact strip normally fits, so there is nothing to centre. Only a plan
// too dense for FIT_MIN_PPD scrolls, and then the current task is brought
// into view without pushing today off the strip. Debounced: while the page is
// actively scrolling, highlightDate can change every frame, and centering on
// each of those would make the strip visibly fight itself.
function centerOn(iso: string) {
  const el = scrollerEl.value;
  if (!el || trackWidth.value <= el.clientWidth) return;
  const target = scrollTargetFor(
    pxIso(iso),
    todayX.value,
    el.clientWidth,
    trackWidth.value,
  );
  if (Math.abs(el.scrollLeft - target) < 4) return;
  el.scrollTo({ left: target, behavior: "smooth" });
}
let centerTimer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.highlightDate,
  (d) => {
    if (!d) return;
    clearTimeout(centerTimer);
    centerTimer = setTimeout(() => centerOn(d), 120);
  },
);
onBeforeUnmount(() => clearTimeout(centerTimer));

// The reverse direction: clicking a node/pin jumps the task list to it - a
// deliberate click rather than a live scroll-position mirror, so it can't
// fight the page's own scrolling the way a scroll-linked sync would. Keyed by
// task id, not date - several tasks can share the same day.
function onNodeClick(id: string, e: MouseEvent) {
  if (props.clickable) return; // let it bubble to onScrollerClick (place a new date)
  e.stopPropagation();
  emit("select", id);
}
</script>

<style scoped>
/* Vertical rhythm is a token set, not a table of hand-tuned offsets: the axis
  sits at --axis-y and everything else is expressed as a distance from it, so
  .compact only overrides sizes and the whole stack re-flows. --lanes comes
  from the packer, which is why the strip grows exactly as much as the
  densest cluster demands and no more. */
.timeline {
  /* Schulferien has no sitewide color of its own - blended from the two
    tokens that already exist rather than inventing a new raw hex, so it
    still flips correctly in dark mode. */
  --school: color-mix(in srgb, var(--warn) 45%, var(--accent) 55%);

  --lane-h: 1.1rem; /* must stay > --node, or stacked lanes touch */
  --head-pad: 4.2rem; /* clearance above the top lane: pin labels + tooltips */
  --tick-day: 0.25rem;
  --tick-week: 0.55rem;
  --tick-month: 0.95rem;
  --ctx-y: 1.2rem; /* Feiertage/Schulferien strip, below the ruler */
  --ctx-h: 0.55rem;
  --mlabel-y: 2.05rem;
  --mlabel-size: 0.7rem;
  --pin-title: 0.95rem;
  --pin-sub: 0.7rem;
  --today-top: 2.7rem;

  --axis-y: calc(var(--lanes, 1) * var(--lane-h) + var(--head-pad));
  --below: calc(
    var(--ctx-y) + var(--ctx-h)
  ); /* rail bottom, above the labels */
  --foot: calc(var(--mlabel-y) + 1.5rem);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.5rem 0 0.7rem;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  letter-spacing: 0.02em;
  color: var(--muted);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
}
.legend-item input {
  margin: 0;
  cursor: pointer;
}
.swatch {
  display: inline-block;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 2px;
}
.swatch.feiertage {
  background: var(--warn);
}
.swatch.schulferien {
  background: var(--school);
}
.scroller {
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 0.6rem;
  cursor: crosshair;
}
.armed .scroller {
  cursor: copy;
}
.track {
  position: relative;
  height: calc(var(--axis-y) + var(--foot));
}
.axis {
  position: absolute;
  left: 0;
  right: 0;
  top: var(--axis-y);
  height: 1px;
  background: var(--line);
}
.days {
  position: absolute;
  left: 0;
  right: 0;
  top: var(--axis-y);
  height: var(--tick-day);
  background-image: linear-gradient(
    90deg,
    var(--line) 0 1px,
    transparent 1px 100%
  );
  background-size: var(--ppd) 100%;
  opacity: 0.5;
  pointer-events: none;
}
.wtick {
  position: absolute;
  top: var(--axis-y);
  width: 1px;
  height: var(--tick-week);
  background: var(--muted);
  opacity: 0.6;
  transition:
    transform 0.1s,
    opacity 0.1s,
    background-color 0.1s;
  transform-origin: top;
}
.wtick:hover {
  transform: scaleY(1.6);
  opacity: 1;
  background: var(--accent);
}
.mtick {
  position: absolute;
  top: var(--axis-y);
  width: 1px;
  height: var(--tick-month);
  background: var(--line);
}
.mlabel {
  position: absolute;
  top: calc(var(--axis-y) + var(--mlabel-y));
  font-family: var(--font-mono);
  font-size: var(--mlabel-size);
  letter-spacing: 0.04em;
  color: var(--muted);
  white-space: nowrap;
  padding-left: 0.4rem;
}
.htick {
  position: absolute;
  top: calc(var(--axis-y) + var(--ctx-y));
  width: 2px;
  height: var(--ctx-h);
  background: var(--warn);
}
.band {
  position: absolute;
  top: calc(var(--axis-y) + var(--ctx-y));
  height: var(--ctx-h);
  border-radius: 2px;
}
.band.schulferien {
  background: color-mix(in srgb, var(--school) 30%, transparent);
  border-top: 2px solid var(--school);
}
.today {
  position: absolute;
  top: var(--today-top);
  height: calc(var(--axis-y) + var(--below) - var(--today-top));
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
.pin,
.ghost {
  position: absolute;
  top: 0.2rem;
  height: calc(var(--axis-y) + var(--below) - 0.2rem);
  width: 2px;
}
.pin {
  background: var(--accent);
  cursor: pointer;
}
/* A width change reads as "hovered" without a glow - a filter: drop-shadow
  here looked fine in light mode but far too bright against a dark background. */
.pin.hovered {
  width: 4px;
  margin-left: -1px;
}
.pin b {
  position: absolute;
  top: -0.25rem;
  left: 0.6rem;
  font-weight: 600;
  font-size: var(--pin-title);
  white-space: nowrap;
  color: var(--accent);
}
.pin i {
  position: absolute;
  top: calc(var(--pin-title) + 0.35rem);
  left: 0.6rem;
  font-style: normal;
  font-family: var(--font-mono);
  font-size: var(--pin-sub);
  color: var(--muted);
  white-space: nowrap;
}
.pin :deep(a) {
  position: absolute;
  top: calc(var(--pin-title) + var(--pin-sub) + 0.85rem);
  left: 0.6rem;
  white-space: nowrap;
}
/* Anchor near the right end: same offsets, mirrored. */
.pin.flip b,
.pin.flip i,
.pin.flip :deep(a) {
  left: auto;
  right: 0.6rem;
  text-align: right;
}
.thread {
  position: absolute;
  top: var(--axis-y);
  height: 2px;
  background: var(--accent);
  opacity: 0.3;
}
.node {
  position: absolute;
  /* --lane (set inline, see taskLane) staggers capsules whose spans touch on
    screen into separate rows. Upward, not downward - below the axis is the
    ruler and the Feiertage strip, lanes stacking into those would just move
    the collision instead of fixing it. Lane 0 is centred on the axis. */
  top: calc(var(--axis-y) - var(--node) / 2 - var(--lane, 0) * var(--lane-h));
  /* left/width come from the template and already include the caps - no
    min-width, no negative margin, so what the packer measured is what the
    browser draws. */
  height: var(--node);
  border-radius: 999px;
  background: var(--paper-raised);
  border: 2px solid var(--accent);
  padding: 0;
  transition:
    box-shadow 0.12s,
    background-color 0.12s,
    border-color 0.12s;
}
.node.warn {
  border-color: var(--warn);
}
.node.current,
.node.hovered {
  border-color: var(--accent);
  background: var(--accent);
  /* A ring, not a scale() - scaling a multi-week capsule stretched it
    sideways and made it point at the wrong days. */
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 30%, transparent);
}
.node.impossible {
  border-color: var(--warn);
  background: var(--warn);
}
.node.done {
  border-color: var(--done-color);
  background: var(--done-color);
}
.node:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
.pin.done {
  background: var(--done-color);
}
.node .start-by {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--ink);
}
.node::after {
  content: attr(data-label);
  position: absolute;
  bottom: calc(var(--node) + 0.45rem);
  left: 50%;
  transform: translateX(-50%);
  background: var(--ink);
  color: var(--paper);
  font-size: 0.7rem;
  /* Wraps instead of one unclipped nowrap line - a long label on a narrow
    strip used to blow out sideways into whatever else was nearby (the
    Umzugstag pin, most often). z-index wins it against .pin's own text too,
    which has no z-index of its own and otherwise paints on top since it's
    later in the DOM. --head-pad guarantees the room it needs above the top
    lane, so overflow-y: hidden can't clip it. */
  white-space: normal;
  max-width: 11rem;
  text-align: center;
  z-index: 5;
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

/* Compact: same layout, larger type and ticks, one lane fewer. Nothing here
  repositions anything - it only retunes the tokens. */
.compact {
  --lane-h: 1.85rem;
  --head-pad: 4.6rem;
  --tick-day: 0.5rem;
  --tick-week: 1.1rem;
  --tick-month: 1.45rem;
  --ctx-y: 1.7rem;
  --ctx-h: 1.1rem;
  --mlabel-y: 2.9rem;
  --mlabel-size: 0.95rem;
  --pin-title: 1.3rem;
  --pin-sub: 1rem;
  --today-top: 2.9rem;
}
.compact .scroller {
  padding-bottom: 0.8rem;
  cursor: default;
}
.compact .today b {
  font-size: 0.95rem;
  top: -1.5rem;
  left: -0.75rem;
}
.compact .node,
.compact .pin {
  cursor: pointer;
}
.compact .node::after {
  font-size: 0.85rem;
}

@media (prefers-reduced-motion: reduce) {
  .wtick,
  .node,
  .node::after {
    transition: none;
  }
}

/* Phones: only type and tick sizes shrink. The scale itself already adapts
  to the width, so the strip needs no separate mobile layout. */
@media (max-width: 36rem) {
  .timeline:not(.compact) {
    --lane-h: 0.9rem;
    --head-pad: 3.1rem;
    --tick-day: 0.18rem;
    --tick-week: 0.4rem;
    --tick-month: 0.7rem;
    --ctx-y: 0.9rem;
    --ctx-h: 0.4rem;
    --mlabel-y: 1.5rem;
    --mlabel-size: 0.62rem;
    --pin-title: 0.85rem;
    --pin-sub: 0.62rem;
    --today-top: 2rem;
  }
  /* --lane-h has to stay above --node, or stacked lanes touch. */
  .compact {
    --lane-h: 1.5rem;
    --head-pad: 3.6rem;
    --tick-day: 0.35rem;
    --tick-week: 0.75rem;
    --tick-month: 1.05rem;
    --ctx-y: 1.15rem;
    --ctx-h: 0.7rem;
    --mlabel-y: 2rem;
    --mlabel-size: 0.72rem;
    --pin-title: 1rem;
    --pin-sub: 0.75rem;
    --today-top: 2.3rem;
  }
  .compact .node::after {
    font-size: 0.75rem;
  }
  .legend {
    font-size: 0.7rem;
    gap: 0.6rem;
  }
  .node::after {
    max-width: min(11rem, 70vw);
  }
}
/* Dots are hard to tap - grow the hit area, not the dot, via a transparent
  pseudo-element, so the lane packing math is untouched. */
@media (hover: none) {
  .node::before {
    content: "";
    position: absolute;
    inset: -8px;
  }
}
</style>
