<script setup lang="ts">
// Homepage hero "show, don't tell" teaser (src/pages/index.astro) - a
// standalone, single-month grid, not a reuse of MonthGrid.vue: this has no
// week/day clicks, no week-number buttons, none of the interactive plumbing
// the real /kalender/ page needs, and the one thing it adds (background
// shaded by how many layers overlap a day) is a different visual model than
// MonthGrid's dot marks. Forking keeps that off a shared, untested
// component instead of adding a third template branch to it. Grid geometry
// (weeksOfMonth/matchesForDay) is still shared via lib/date-grid.ts - only
// the rendering is new.
//
// Synced to the H1 rotator (index.astro's own vanilla-JS script, kept
// separate so the static SSR H1 stays the no-JS/SEO fallback and the
// prefers-reduced-motion gate stays intact) via a "homepage-rotate"
// CustomEvent instead of a shared Vue parent - the rotator already owns
// text swapping; this just also listens for which layers that sentence
// is about.
import { computed, onMounted, onUnmounted, ref } from "vue";
import { type DayLayer, matchesForDay, weeksOfMonth } from "../../lib/date-grid";
import { COLORS } from "../../lib/calendar-colors";

const WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

const props = defineProps<{ initialLayerIds: string[] }>();

// A ref, not a one-off `new Date()` at setup - this component is a
// long-lived Vue island (mounted once per page view), so a plain constant
// would freeze "today" at whatever it was when the tab was opened and
// silently go stale across a real midnight (a tab left open overnight
// would keep highlighting yesterday). Re-read on visibilitychange instead
// of polling - cheap, and the standard way to catch a wall-clock jump
// while the tab was backgrounded/asleep.
const now = ref(new Date());
const year = computed(() => now.value.getFullYear());
const monthIndex0 = computed(() => now.value.getMonth());
const todayIso = computed(
  () => `${year.value}-${String(monthIndex0.value + 1).padStart(2, "0")}-${String(now.value.getDate()).padStart(2, "0")}`,
);
const weeks = computed(() => weeksOfMonth(year.value, monthIndex0.value));

const layerIds = ref<string[]>(props.initialLayerIds);
const layers = ref<DayLayer[]>([]);
const href = ref(`/kalender/?layers=${layerIds.value.join(",")}`);

interface EntryResponse {
  label: string;
  url: string;
  windows: { from: string; to: string; description: string }[];
}

// Same per-id endpoint Kalender.vue uses, same "fetch once, keep forever"
// cache - the rotator revisits the same handful of ids repeatedly over a
// session, so only the first hit of each id ever costs a request.
const entryCache = new Map<string, Promise<EntryResponse>>();
function fetchEntry(id: string): Promise<EntryResponse> {
  if (!entryCache.has(id)) {
    entryCache.set(id, fetch(`/api/v1/calendar/${id}.json`).then((r) => r.json()));
  }
  return entryCache.get(id)!;
}

async function loadLayers(ids: string[]) {
  href.value = `/kalender/?layers=${ids.join(",")}`;
  const entries = await Promise.all(ids.map(fetchEntry));
  // Bail if the rotator already moved on while this fetch was in flight.
  if (layerIds.value !== ids) return;
  layers.value = entries.map((entry, i) => ({
    color: COLORS[i % COLORS.length],
    label: entry.label,
    url: entry.url,
    visible: true,
    windows: entry.windows.map((w) => ({ start: w.from, end: w.to, description: w.description })),
  }));
}

function onRotate(e: Event) {
  const ids = (e as CustomEvent<{ layerIds: string[] }>).detail?.layerIds;
  if (!ids?.length) return;
  layerIds.value = ids;
  loadLayers(ids);
}

function onVisibilityChange() {
  if (document.visibilityState === "visible") now.value = new Date();
}

onMounted(() => {
  loadLayers(layerIds.value);
  window.addEventListener("homepage-rotate", onRotate);
  document.addEventListener("visibilitychange", onVisibilityChange);
});
onUnmounted(() => {
  window.removeEventListener("homepage-rotate", onRotate);
  document.removeEventListener("visibilitychange", onVisibilityChange);
});

function isOtherMonth(dayIso: string): boolean {
  return Number(dayIso.slice(5, 7)) - 1 !== monthIndex0.value;
}

// Background shade scales with how many layers hit this day - a day two
// layers agree on (e.g. a Feiertag inside Schulferien) reads as more
// "highlighted" than one only a single layer marks, without needing a
// legend to explain it.
function cellStyle(dayIso: string): Record<string, string> | undefined {
  const matches = matchesForDay(dayIso, layers.value);
  if (matches.length === 0) return undefined;
  const strength = Math.min(0.22 * matches.length + 0.14, 0.75);
  return { background: `color-mix(in srgb, ${matches[0].color} ${Math.round(strength * 100)}%, var(--paper))` };
}
</script>

<template>
  <a class="preview" :href="href" title="Im Ebenen-Kalender öffnen">
    <div class="grid-header">
      <span class="kw">KW</span>
      <span v-for="wd in WEEKDAY_NAMES" :key="wd">{{ wd }}</span>
    </div>
    <div v-for="week in weeks" :key="week.mondayIso" class="week-row">
      <span class="week-number">{{ week.number }}</span>
      <span
        v-for="dayIso in week.days"
        :key="dayIso"
        class="day-cell"
        :class="{ today: dayIso === todayIso, 'other-month': isOtherMonth(dayIso) }"
        :style="cellStyle(dayIso)"
      >
        {{ Number(dayIso.slice(8)) }}
      </span>
    </div>
  </a>
</template>

<style scoped>
.preview {
  display: block;
  font-size: 0.95rem;
  width: 34rem;
  max-width: 100%;
  flex-shrink: 0;
  color: inherit;
  text-decoration: none;
  cursor: pointer;
}
.preview:hover {
  opacity: 0.9;
}
.grid-header,
.week-row {
  display: grid;
  grid-template-columns: 2.2rem repeat(7, 1fr);
  gap: 3px;
}
.grid-header {
  margin-bottom: 3px;
}
.grid-header span {
  text-align: center;
  color: var(--muted);
  font-size: 0.7rem;
}
.kw {
  font-family: var(--font-mono);
}
.week-row {
  margin-bottom: 3px;
}
.week-number {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.day-cell {
  aspect-ratio: 1;
  display: flex;
  justify-content: flex-end;
  padding: 0.35rem;
  background: var(--paper);
  border: 1px solid var(--line);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  transition: background 0.4s ease;
}
.day-cell.other-month {
  color: var(--muted);
  opacity: 0.5;
}
.day-cell.today {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
  font-weight: 600;
}
</style>
