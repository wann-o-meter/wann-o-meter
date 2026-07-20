<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { ChevronLeft, ChevronRight, X } from "lucide-vue-next";
import { MONTH_NAMES, WEEKDAY_NAMES_LONG, isoWeekNumber } from "../../lib/date-display";

// Overlay mode (PLAN.md 4.2): layers render stacked, no set operations
// (intersections are explicitly NOT V1). The component has no knowledge of
// content categories at all - every selectable thing (a country's Feiertage,
// a Bundesland x Ferientyp combination, a fruit's season, a scraped page
// with dates) is just a CatalogEntry from /api/v1/calendar.json. Adding a
// new content type to the calendar means extending lib/calendar-sources.ts
// server-side; nothing here needs to change.

const WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

// Muted "ink" colors instead of bright marker colors - matches the site's
// paper/document tone (see src/styles/global.css).
const COLORS = [
  "#3c5a80", "#6b7d3d", "#8a5a2b", "#5c4a72", "#2f7565",
  "#9c4f3c", "#4a5a6b", "#7d5a3c", "#3c6b6b", "#6b3c52",
];

// ponytail: no data-driven lower bound is known (holiday/vacation data goes
// back further than any constant here could track) - 1900 is just a sane
// floor so the typed-year input below has something to validate against.
const YEAR_MIN = 1900;
const YEAR_MAX = new Date().getFullYear() + 5;
const GROUP_DEFAULT_LIMIT = 8;

interface TimeWindow {
  start: string;
  end: string;
  description: string;
}

interface Layer {
  id: string;
  group: string;
  label: string;
  color: string;
  visible: boolean;
  url: string;
  feedUrl: string;
  windows: TimeWindow[];
}

// Mirrors lib/calendar-sources.ts's CatalogEntry/CalendarEntry - kept as a
// local type instead of importing across the server/client boundary.
interface CatalogEntry {
  id: string;
  group: string;
  label: string;
  url: string;
  feedUrl: string;
}

interface CalendarEntryResponse {
  windows: { from: string; to: string; description: string }[];
}

// "graph" is a year-wide second lens over the same layer data (PLAN.md 4.2
// stays true/false per day; this aggregates that into a per-month density
// count per layer instead of drilling into a single day) - not tied to
// month/week navigation the way those two are.
type View = "year" | "month" | "week" | "graph";

// Set by src/pages/kalender/embed.astro (the standalone iframe-embeddable
// page, no header/footer/nav chrome) - hides the "Einbetten" button there,
// since offering to embed a page that's already an embed is pointless.
const props = defineProps<{ embed?: boolean }>();

const today = new Date();
const todayIso = isoFromDate(today);

const year = ref(today.getFullYear());
const layers = ref<Layer[]>([]);
const loading = ref(true);

const view = ref<View>("year");
const activeMonth = ref(today.getMonth());
const weekStart = ref(isoFromDate(mondayOf(today)));
const selectedDay = ref<string | null>(null);

const editingYear = ref(false);
const yearDraft = ref("");
const yearInputEl = ref<HTMLInputElement | null>(null);

const catalog = ref<CatalogEntry[]>([]);
const layerSearch = ref("");
const expandedGroups = ref<Set<string>>(new Set());

const showEmbed = ref(false);
const copied = ref(false);

const availableOptions = computed<CatalogEntry[]>(() => {
  const activeIds = new Set(layers.value.map((l) => l.id));
  return catalog.value.filter((entry) => !activeIds.has(entry.id));
});

// Grouped the same way the homepage clusters its cards (lib/all-content.ts):
// one heading per group with a count, only the first N shown by default,
// the rest behind "show more" - a search always reaches every match
// regardless of collapse state.
interface OptionGroup {
  group: string;
  total: number;
  visible: CatalogEntry[];
  more: number;
}

const groupedOptions = computed<OptionGroup[]>(() => {
  const q = layerSearch.value.trim().toLowerCase();
  const matches = q
    ? availableOptions.value.filter((o) => `${o.group} ${o.label}`.toLowerCase().includes(q))
    : availableOptions.value;

  const byGroup = new Map<string, CatalogEntry[]>();
  for (const o of matches) {
    if (!byGroup.has(o.group)) byGroup.set(o.group, []);
    byGroup.get(o.group)!.push(o);
  }

  return [...byGroup.entries()].map(([group, entries]) => {
    const expanded = q.length > 0 || expandedGroups.value.has(group);
    const visible = expanded ? entries : entries.slice(0, GROUP_DEFAULT_LIMIT);
    return { group, total: entries.length, visible, more: entries.length - visible.length };
  });
});

function expandGroup(group: string) {
  expandedGroups.value = new Set([...expandedGroups.value, group]);
}

// Same grouping as groupedOptions, but over the layers already added - the
// sidebar otherwise loses the category headings the moment a layer is
// selected, which reads fine with one or two layers but turns into an
// unlabelled wall of checkboxes once someone picks entries from several
// categories.
interface LayerGroup {
  group: string;
  layers: Layer[];
}

const groupedLayers = computed<LayerGroup[]>(() => {
  const byGroup = new Map<string, Layer[]>();
  for (const l of layers.value) {
    if (!byGroup.has(l.group)) byGroup.set(l.group, []);
    byGroup.get(l.group)!.push(l);
  }
  return [...byGroup.entries()].map(([group, groupLayers]) => ({ group, layers: groupLayers }));
});

function groupVisibility(grp: LayerGroup): "all" | "none" | "some" {
  const visibleCount = grp.layers.filter((l) => l.visible).length;
  if (visibleCount === 0) return "none";
  if (visibleCount === grp.layers.length) return "all";
  return "some";
}

function toggleGroup(grp: LayerGroup) {
  const nextVisible = groupVisibility(grp) !== "all";
  for (const l of grp.layers) l.visible = nextVisible;
}

function selectOption(entry: CatalogEntry) {
  addLayer(entry);
  layerSearch.value = "";
}

const layerDataCache = new Map<string, Promise<CalendarEntryResponse>>();

function fetchLayerData(id: string): Promise<CalendarEntryResponse> {
  if (!layerDataCache.has(id)) {
    layerDataCache.set(id, fetch(`/api/v1/calendar/${id}.json`).then((r) => r.json()));
  }
  return layerDataCache.get(id)!;
}

function nextColor(): string {
  return COLORS[layers.value.length % COLORS.length];
}

async function addLayer(entry: CatalogEntry) {
  if (layers.value.some((l) => l.id === entry.id)) return;
  layers.value.push({
    id: entry.id,
    group: entry.group,
    label: entry.label,
    color: nextColor(),
    visible: true,
    url: entry.url,
    feedUrl: entry.feedUrl,
    windows: [],
  });
  const data = await fetchLayerData(entry.id);
  // Look the layer back up from the reactive array instead of holding the
  // object built above - Vue only proxies it once it's read back through
  // `layers.value`, so mutating the pre-push reference never triggers a
  // re-render (only an unrelated array mutation, e.g. adding another layer,
  // would incidentally pick up the already-updated raw data on its next
  // render pass).
  const layer = layers.value.find((l) => l.id === entry.id);
  if (layer) layer.windows = data.windows.map((w) => ({ start: w.from, end: w.to, description: w.description }));
}

function removeLayer(id: string) {
  layers.value = layers.value.filter((l) => l.id !== id);
}

function resetLayers() {
  layers.value = [];
}

// Set right before a "drill into a more specific view" mutation (openMonth,
// openWeek, the breadcrumbs' "go up a level" clicks) so the resulting
// writeUrl() call pushes a real history entry instead of replacing - without
// this, the whole calendar session was one single history entry, and the
// browser's back button skipped straight past every view the user had
// navigated through, out of the calendar entirely.  Left false for
// lateral/continuous changes (prev/next month or week, year +/-, layer
// search) - each of those becoming its own back-button stop would be far
// more annoying than helpful.
let pushNextUrlWrite = false;

// Shared by writeUrl() (this page's own address bar) and embedUrl below (a
// link to the standalone /kalender/embed/ page with the same state) - both
// need the same "what does the current view look like" query string, just
// with `live` toggling whether year/month/weekstart are the concrete
// current values (the page's own URL, a link to exactly this moment) or the
// literal string "current" (the embed link - loadFromUrlOrDefault() below
// already falls back to today's actual year/month/weekstart for any value
// that doesn't parse as a real one, e.g. Number("current") is NaN, so this
// needs no special-casing there: an embedded widget just always shows
// "now" instead of freezing at whatever date the embed link was copied on).
function buildParams(live: boolean): URLSearchParams {
  const params = new URLSearchParams();
  params.set("year", live ? "current" : String(year.value));
  if (view.value !== "year") params.set("view", view.value);
  // 1-indexed in the URL (month=3 -> March) even though activeMonth is
  // 0-indexed internally (JS Date convention) - a raw 0-index would read as
  // April to anyone reading/writing the URL by hand.
  if (view.value === "month" || view.value === "week") {
    params.set("month", live ? "current" : String(activeMonth.value + 1));
  }
  if (view.value === "week") params.set("weekstart", live ? "current" : weekStart.value);
  if (layers.value.length) params.set("layers", layers.value.map((l) => l.id).join(","));
  return params;
}

function writeUrl() {
  const url = `${window.location.pathname}?${buildParams(false)}`;
  if (pushNextUrlWrite) {
    window.history.pushState(null, "", url);
    pushNextUrlWrite = false;
  } else {
    window.history.replaceState(null, "", url);
  }
}

// Points at the standalone embed page instead of wherever /kalender/ is
// currently mounted - so an embed made from a preset landing page still
// links to /kalender/embed/, not e.g. /presets/foo/embed/.
const embedUrl = computed(() => {
  if (typeof window === "undefined") return "";
  return `${window.location.origin}/kalender/embed/?${buildParams(true)}`;
});

function toggleEmbedPanel() {
  showEmbed.value = !showEmbed.value;
}

async function copyEmbedUrl() {
  await navigator.clipboard.writeText(embedUrl.value);
  copied.value = true;
  setTimeout(() => {
    copied.value = false;
  }, 1500);
}

function selectEmbedUrl(e: Event) {
  (e.target as HTMLInputElement).select();
}

// Reads the current URL and resets EVERY piece of state to match - not just
// the params that happen to be present - so this is safe to call both on
// initial mount and again on popstate (the browser back/forward buttons),
// when a previous, differently-shaped URL needs to fully replace the
// current state rather than merely patch it.
async function loadFromUrlOrDefault() {
  const params = new URLSearchParams(window.location.search);

  const y = Number(params.get("year"));
  year.value = y >= YEAR_MIN && y <= YEAR_MAX ? y : today.getFullYear();

  const viewParam = params.get("view");
  view.value =
    viewParam === "month" || viewParam === "week" || viewParam === "graph" ? viewParam : "year";

  const monthParam = Number(params.get("month"));
  activeMonth.value = monthParam >= 1 && monthParam <= 12 ? monthParam - 1 : today.getMonth();

  const weekStartParam = params.get("weekstart");
  const parsedWeekStart =
    weekStartParam && /^\d{4}-\d{2}-\d{2}$/.test(weekStartParam) ? new Date(`${weekStartParam}T00:00:00`) : null;
  const validWeekStart = parsedWeekStart !== null && !Number.isNaN(parsedWeekStart.getTime());
  // Snapped to its own Monday rather than taken verbatim - a hand-edited URL
  // can put any date here, including one that isn't a Monday at all.
  weekStart.value = validWeekStart ? isoFromDate(mondayOf(parsedWeekStart)) : isoFromDate(mondayOf(today));

  // weekstart is the only value week view actually renders from, so once
  // it's the active view it's treated as the sole source of truth for
  // year/month too, overriding whatever they say - otherwise a hand-edited
  // URL with a mismatched month= (or year=) produces a breadcrumb that
  // contradicts the days actually shown.
  if (view.value === "week" && validWeekStart) {
    const monday = mondayOf(parsedWeekStart);
    year.value = monday.getFullYear();
    activeMonth.value = monday.getMonth();
  }

  // A data page's date link ("open the calendar on this exact day") - takes
  // priority over year/view/weekstart above, which is why it's applied
  // after them instead of merged into their fallback logic.
  const dayParam = params.get("day");
  if (dayParam && /^\d{4}-\d{2}-\d{2}$/.test(dayParam)) {
    const d = new Date(`${dayParam}T00:00:00`);
    selectedDay.value = dayParam;
    view.value = "week";
    weekStart.value = isoFromDate(mondayOf(d));
    year.value = d.getFullYear();
    activeMonth.value = mondayOf(d).getMonth();
  } else {
    selectedDay.value = null;
  }

  // No baked-in defaults (no preferred Bundesland/variety) - the user builds
  // their own selection through search, see the empty-layers hint below.
  // Synced in both directions (not just "add what's missing") so navigating
  // back to a state with fewer layers actually drops the extra ones.
  const layerIds = new Set(params.get("layers")?.split(",").filter(Boolean) ?? []);
  layers.value = layers.value.filter((l) => layerIds.has(l.id));
  await Promise.all(
    [...layerIds]
      .filter((id) => !layers.value.some((l) => l.id === id))
      .map((id) => catalog.value.find((entry) => entry.id === id))
      .filter((entry): entry is CatalogEntry => entry !== undefined)
      .map((entry) => addLayer(entry)),
  );
}

function daysInMonth(monthIndex0: number): number {
  return new Date(year.value, monthIndex0 + 1, 0).getDate();
}

function isoDate(monthIndex0: number, day: number): string {
  return `${year.value}-${String(monthIndex0 + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function isoFromDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function mondayOf(d: Date): Date {
  const copy = new Date(d);
  const weekday = (copy.getDay() + 6) % 7; // Mon=0
  copy.setDate(copy.getDate() - weekday);
  return copy;
}

function formatShort(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}.`;
}

function openMonth(monthIndex0: number) {
  pushNextUrlWrite = true;
  activeMonth.value = monthIndex0;
  view.value = "month";
}

function openWeek(mondayIso: string) {
  pushNextUrlWrite = true;
  selectedDay.value = null;
  weekStart.value = mondayIso;
  activeMonth.value = Number(mondayIso.slice(5, 7)) - 1;
  view.value = "week";
}

function goToYearView() {
  pushNextUrlWrite = true;
  view.value = "year";
}

function goToMonthView() {
  pushNextUrlWrite = true;
  view.value = "month";
}

function toggleGraphView() {
  pushNextUrlWrite = true;
  view.value = view.value === "graph" ? "year" : "graph";
}

function openWeekForDay(dayIso: string) {
  openWeek(isoFromDate(mondayOf(new Date(`${dayIso}T00:00:00`))));
}

function changeMonth(delta: number) {
  let m = activeMonth.value + delta;
  let y = year.value;
  if (m < 0) {
    m = 11;
    y -= 1;
  } else if (m > 11) {
    m = 0;
    y += 1;
  }
  if (y < YEAR_MIN || y > YEAR_MAX) return;
  year.value = y;
  activeMonth.value = m;
}

// Navigating weeks across a year/month boundary only approximates `year`
// and `activeMonth` from the Monday - a week can straddle New Year's or a
// month end, which doesn't matter for display purposes. `activeMonth` still
// has to track along (it drives the "back to month" breadcrumb and the
// month= URL param) or it goes stale after enough next/prev-week clicks.
function changeWeek(delta: number) {
  const d = new Date(`${weekStart.value}T00:00:00`);
  d.setDate(d.getDate() + delta * 7);
  if (d.getFullYear() < YEAR_MIN || d.getFullYear() > YEAR_MAX) return;
  selectedDay.value = null;
  weekStart.value = isoFromDate(d);
  year.value = d.getFullYear();
  activeMonth.value = d.getMonth();
}

async function startEditYear() {
  yearDraft.value = String(year.value);
  editingYear.value = true;
  await nextTick();
  yearInputEl.value?.focus();
  yearInputEl.value?.select();
}

function commitYear() {
  const y = Number(yearDraft.value);
  if (Number.isInteger(y) && y >= YEAR_MIN && y <= YEAR_MAX) year.value = y;
  editingYear.value = false;
}

// Full Monday-Sunday weeks covering a month (including the leading/trailing
// days of adjacent months a week straddles) - shared by month view (its own
// month) and the year view (every month's mini-grid, so week numbers show
// up there too instead of just in month view).
function weeksOfMonth(monthIndex0: number): { mondayIso: string; number: number; days: string[] }[] {
  const lastDay = new Date(year.value, monthIndex0 + 1, 0);
  let monday = mondayOf(new Date(year.value, monthIndex0, 1));
  const weeks: { mondayIso: string; number: number; days: string[] }[] = [];
  while (monday <= lastDay) {
    const days = Array.from({ length: 7 }, (_, i) => {
      const day = new Date(monday);
      day.setDate(day.getDate() + i);
      return isoFromDate(day);
    });
    weeks.push({ mondayIso: isoFromDate(monday), number: isoWeekNumber(monday), days });
    monday = new Date(monday);
    monday.setDate(monday.getDate() + 7);
  }
  return weeks;
}

const monthWeeks = computed(() => weeksOfMonth(activeMonth.value));

const currentWeekDays = computed(() => {
  const start = new Date(`${weekStart.value}T00:00:00`);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return isoFromDate(d);
  });
});

const currentWeekNumber = computed(() => isoWeekNumber(new Date(`${weekStart.value}T00:00:00`)));

const weekRangeText = computed(() => {
  const days = currentWeekDays.value;
  return `${formatShort(days[0])}–${formatShort(days[6])} ${days[6].slice(0, 4)}`;
});

interface Match {
  color: string;
  title: string;
  url: string;
}

function matchesForDay(iso: string): Match[] {
  const matches: Match[] = [];
  for (const layer of layers.value) {
    if (!layer.visible) continue;
    for (const w of layer.windows) {
      if (w.start <= iso && iso <= w.end) {
        // Fragment points at the matching row on the target page (see the
        // :target highlight in the detail pages).
        matches.push({ color: layer.color, title: `${layer.label}: ${w.description}`, url: `${layer.url}#${w.start}` });
      }
    }
  }
  return matches;
}

// The "graph" view's data: no numeric value/unit is populated on any window
// yet (checked across data/**/*.yaml - lib/schema.ts's MaterializedWindow
// already has the fields for when that lands), so the only honest thing to
// plot today is density - how many days per bucket a layer is active - which
// still surfaces seasonality/clustering that the true/false calendar marks
// don't make visible at a glance. Bucket size is user-chosen (month/week/day)
// via graphGranularity - the underlying windows are already day-precision
// (see Layer.windows), so this is just a different grouping of the same data.
type Granularity = "month" | "week" | "day";
const graphGranularity = ref<Granularity>("month");

function isActiveDay(layer: Layer, iso: string): boolean {
  return layer.windows.some((w) => w.start <= iso && iso <= w.end);
}

function activeDaysInMonth(layer: Layer, monthIndex0: number): number {
  const total = daysInMonth(monthIndex0);
  let count = 0;
  for (let day = 1; day <= total; day++) {
    if (isActiveDay(layer, isoDate(monthIndex0, day))) count++;
  }
  return count;
}

interface GraphBucket {
  label: string;
  count: number;
  total: number;
}

// All ISO dates in the given year, in order - the shared base that week/day
// buckets group differently. Not used for month buckets, which already have
// a cheap dedicated path (activeDaysInMonth) that doesn't need this array.
function isoDatesOfYear(y: number): string[] {
  const dates: string[] = [];
  for (let m = 0; m < 12; m++) {
    const total = new Date(y, m + 1, 0).getDate();
    for (let day = 1; day <= total; day++) {
      dates.push(`${y}-${String(m + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
    }
  }
  return dates;
}

function weekBuckets(layer: Layer, dates: string[]): GraphBucket[] {
  // Grouped by the ISO week's Monday - a year's first/last week can be
  // partial (fewer than 7 days actually fall in `dates`), which is fine:
  // the bar's height is count/total of that bucket, not count/7.
  const byMonday = new Map<string, string[]>();
  for (const iso of dates) {
    const monday = isoFromDate(mondayOf(new Date(`${iso}T00:00:00`)));
    if (!byMonday.has(monday)) byMonday.set(monday, []);
    byMonday.get(monday)!.push(iso);
  }
  return [...byMonday.entries()].map(([monday, days]) => ({
    label: `KW ${isoWeekNumber(new Date(`${monday}T00:00:00`))}`,
    count: days.filter((iso) => isActiveDay(layer, iso)).length,
    total: days.length,
  }));
}

function dayBuckets(layer: Layer, dates: string[]): GraphBucket[] {
  return dates.map((iso) => ({ label: iso, count: isActiveDay(layer, iso) ? 1 : 0, total: 1 }));
}

const graphRows = computed(() => {
  const dates = graphGranularity.value === "month" ? [] : isoDatesOfYear(year.value);
  return layers.value
    .filter((l) => l.visible)
    .map((l) => {
      const buckets: GraphBucket[] =
        graphGranularity.value === "month"
          ? MONTH_NAMES.map((name, monthIndex0) => ({
              label: name.slice(0, 3),
              count: activeDaysInMonth(l, monthIndex0),
              total: daysInMonth(monthIndex0),
            }))
          : graphGranularity.value === "week"
            ? weekBuckets(l, dates)
            : dayBuckets(l, dates);
      return { layer: l, buckets };
    });
});

// Grid columns for the bar rows, shared by every row (bucket count is the
// same across layers) - a plain 1fr split for month's fixed 12 columns, a
// floor width for week/day so a sparse year doesn't squeeze hundreds of
// bars into invisible slivers (the container scrolls horizontally instead).
const graphBarsColumns = computed(() => {
  const n = graphRows.value[0]?.buckets.length ?? 12;
  const minPx = graphGranularity.value === "day" ? 2 : graphGranularity.value === "week" ? 5 : 0;
  return minPx > 0 ? `repeat(${n}, minmax(${minPx}px, 1fr))` : `repeat(${n}, 1fr)`;
});

onMounted(async () => {
  const res = await fetch("/api/v1/calendar.json");
  catalog.value = await res.json();
  await loadFromUrlOrDefault();
  // Canonicalizes the address bar to the state just derived above - without
  // this, a forged/malformed URL (mismatched month=, a non-Monday
  // weekstart, an out-of-range year=) renders correctly but keeps showing
  // its wrong values until the next click, so copying the link would just
  // hand the bad URL to someone else. replaceState (pushNextUrlWrite is
  // false here), so this doesn't add a spurious history entry.
  writeUrl();
  loading.value = false;
  watch([year, layers, view, activeMonth, weekStart], writeUrl, { deep: true });
  // Re-syncs state from the URL the browser just navigated to - without
  // this, clicking back/forward changed the address bar (via the pushState
  // calls above) but left the calendar itself showing whatever it was
  // showing before, since nothing was listening for the user's own
  // back/forward navigation.
  window.addEventListener("popstate", loadFromUrlOrDefault);
});
</script>

<template>
  <div class="calendar">
    <div class="calendar-layout">
    <div class="main-area">
      <p v-if="loading">Lädt…</p>

      <template v-else>
        <nav class="breadcrumbs">
          <button type="button" @click="goToYearView">{{ year }}</button>
          <template v-if="view === 'month' || view === 'week'">
            <ChevronRight :size="14" />
            <button type="button" @click="goToMonthView">{{ MONTH_NAMES[activeMonth] }}</button>
          </template>
          <template v-if="view === 'week'">
            <ChevronRight :size="14" />
            <span>KW {{ currentWeekNumber }}</span>
          </template>
          <button type="button" class="graph-toggle" @click="toggleGraphView">
            {{ view === "graph" ? "← Kalender" : "Verteilung ansehen" }}
          </button>
        </nav>

        <div v-if="view === 'year'" class="months">
          <div v-for="(name, monthIndex0) in MONTH_NAMES" :key="name" class="month">
            <h3 role="button" tabindex="0" @click="openMonth(monthIndex0)" @keydown.enter="openMonth(monthIndex0)">
              {{ name }}
            </h3>
            <div class="weekdays">
              <span class="week-col-header">KW</span>
              <span v-for="wd in WEEKDAY_NAMES" :key="wd">{{ wd }}</span>
            </div>
            <div v-for="week in weeksOfMonth(monthIndex0)" :key="week.mondayIso" class="day-week">
              <button type="button" class="week-number mini" title="Woche öffnen" @click="openWeek(week.mondayIso)">
                {{ week.number }}
              </button>
              <span
                v-for="dayIso in week.days"
                :key="dayIso"
                class="day"
                :class="{ today: dayIso === todayIso, 'other-month': Number(dayIso.slice(5, 7)) - 1 !== monthIndex0 }"
                role="button"
                tabindex="0"
                :title="[...matchesForDay(dayIso).map((m) => m.title), 'Woche öffnen'].join(', ')"
                @click="openWeekForDay(dayIso)"
                @keydown.enter="openWeekForDay(dayIso)"
              >
                {{ Number(dayIso.slice(8)) }}
                <span class="marks">
                  <a
                    v-for="(match, i) in matchesForDay(dayIso)"
                    :key="i"
                    class="mark"
                    :href="match.url"
                    :title="match.title"
                    :style="{ background: match.color }"
                  />
                </span>
              </span>
            </div>
          </div>
        </div>

        <div v-else-if="view === 'month'" class="month-view">
          <div class="view-nav">
            <button type="button" :disabled="year <= YEAR_MIN && activeMonth === 0" @click="changeMonth(-1)">
              <ChevronLeft :size="18" />
            </button>
            <h2>{{ MONTH_NAMES[activeMonth] }} {{ year }}</h2>
            <button type="button" :disabled="year >= YEAR_MAX && activeMonth === 11" @click="changeMonth(1)">
              <ChevronRight :size="18" />
            </button>
          </div>
          <div class="month-grid-header">
            <span class="week-number-header">KW</span>
            <span v-for="wd in WEEKDAY_NAMES" :key="wd">{{ wd }}</span>
          </div>
          <div
            v-for="week in monthWeeks"
            :key="week.mondayIso"
            class="week-row"
            role="button"
            tabindex="0"
            title="Diese Woche öffnen"
            @click="openWeek(week.mondayIso)"
            @keydown.enter="openWeek(week.mondayIso)"
          >
            <button type="button" class="week-number" title="Diese Woche öffnen" @click.stop="openWeek(week.mondayIso)">
              {{ week.number }}
            </button>
            <span
              v-for="dayIso in week.days"
              :key="dayIso"
              class="day-cell"
              :class="{ 'other-month': Number(dayIso.slice(5, 7)) - 1 !== activeMonth, today: dayIso === todayIso }"
              :title="matchesForDay(dayIso).map((m) => m.title).join(', ')"
            >
              <span class="day-number">{{ Number(dayIso.slice(8)) }}</span>
              <span class="marks">
                <a
                  v-for="(match, i) in matchesForDay(dayIso)"
                  :key="i"
                  class="mark"
                  :href="match.url"
                  :title="match.title"
                  :style="{ background: match.color }"
                />
              </span>
            </span>
          </div>
        </div>

        <div v-else-if="view === 'week'" class="week-view">
          <div class="view-nav">
            <button type="button" :disabled="year <= YEAR_MIN" @click="changeWeek(-1)">
              <ChevronLeft :size="18" />
            </button>
            <h2>KW {{ currentWeekNumber }} · {{ weekRangeText }}</h2>
            <button type="button" :disabled="year >= YEAR_MAX" @click="changeWeek(1)">
              <ChevronRight :size="18" />
            </button>
          </div>
          <div class="week-days">
            <div v-for="(dayIso, i) in currentWeekDays" :key="dayIso" class="day-column" :class="{ today: dayIso === todayIso, selected: dayIso === selectedDay }">
              <h4>{{ WEEKDAY_NAMES_LONG[i] }} <span class="day-number">{{ Number(dayIso.slice(8)) }}</span></h4>
              <ul class="event-list">
                <li v-for="(match, j) in matchesForDay(dayIso)" :key="j">
                  <a :href="match.url" class="event-link">
                    <span class="dot" :style="{ background: match.color }" />
                    {{ match.title }}
                  </a>
                </li>
                <li v-if="matchesForDay(dayIso).length === 0" class="no-events">–</li>
              </ul>
            </div>
          </div>
        </div>

        <div v-else class="graph-view">
          <div class="view-nav">
            <button type="button" :disabled="year <= YEAR_MIN" @click="year--">
              <ChevronLeft :size="18" />
            </button>
            <h2>Verteilung {{ year }}</h2>
            <button type="button" :disabled="year >= YEAR_MAX" @click="year++">
              <ChevronRight :size="18" />
            </button>
          </div>
          <div class="granularity-toggle">
            <button type="button" :class="{ active: graphGranularity === 'month' }" @click="graphGranularity = 'month'">Monat</button>
            <button type="button" :class="{ active: graphGranularity === 'week' }" @click="graphGranularity = 'week'">Woche</button>
            <button type="button" :class="{ active: graphGranularity === 'day' }" @click="graphGranularity = 'day'">Tag</button>
          </div>
          <p v-if="graphRows.length === 0" class="no-layers">Keine sichtbaren Ebenen ausgewählt.</p>
          <template v-else>
            <div class="graph-rows">
              <div v-for="row in graphRows" :key="row.layer.id" class="graph-row">
                <span class="graph-row-label" :title="row.layer.label">
                  <span class="dot" :style="{ background: row.layer.color }" />
                  <span class="layer-label-text">{{ row.layer.label }}</span>
                </span>
                <div class="graph-bars" :style="{ gridTemplateColumns: graphBarsColumns }">
                  <div
                    v-for="(bucket, i) in row.buckets"
                    :key="i"
                    class="graph-bar-slot"
                    :title="`${bucket.label}: ${bucket.count}/${bucket.total} Tag(e)`"
                  >
                    <div
                      class="graph-bar"
                      :style="{ height: `${(bucket.count / bucket.total) * 100}%`, background: row.layer.color }"
                    />
                  </div>
                </div>
              </div>
            </div>
            <div v-if="graphGranularity === 'month'" class="graph-months-row">
              <span class="graph-row-label-spacer" />
              <div class="graph-months">
                <span v-for="name in MONTH_NAMES" :key="name">{{ name.slice(0, 3) }}</span>
              </div>
            </div>
          </template>
        </div>
      </template>
    </div>

    <aside class="sidebar">
      <div v-if="view === 'year'" class="year-nav">
        <button type="button" :disabled="year <= YEAR_MIN" @click="year--"><ChevronLeft :size="16" /></button>
        <input
          v-if="editingYear"
          ref="yearInputEl"
          v-model="yearDraft"
          type="number"
          :min="YEAR_MIN"
          :max="YEAR_MAX"
          class="year-input"
          @keydown.enter="commitYear"
          @blur="commitYear"
        />
        <span v-else role="button" tabindex="0" title="Jahr eingeben" @click="startEditYear" @keydown.enter="startEditYear">{{ year }}</span>
        <button type="button" :disabled="year >= YEAR_MAX" @click="year++"><ChevronRight :size="16" /></button>
      </div>

      <div v-if="layers.length > 0" class="layer-list-actions">
        <button type="button" class="reset-layers" @click="resetLayers">Alle entfernen</button>
      </div>
      <ul class="layer-list">
        <template v-for="grp in groupedLayers" :key="grp.group">
          <li class="layer-group-header">
            <label>
              <input
                type="checkbox"
                :checked="groupVisibility(grp) === 'all'"
                :indeterminate="groupVisibility(grp) === 'some'"
                @change="toggleGroup(grp)"
              />
              <span class="layer-group-title">{{ grp.group }}</span>
            </label>
          </li>
          <li v-for="layer in grp.layers" :key="layer.id">
            <label :title="layer.label">
              <input v-model="layer.visible" type="checkbox" />
              <span class="dot" :style="{ background: layer.color }" />
              <span class="layer-label-text">{{ layer.label }}</span>
            </label>
            <span class="layer-actions">
              <a :href="layer.feedUrl" title="Diese Ebene als ICS abonnieren">ICS</a>
              <button type="button" title="Ebene entfernen" @click="removeLayer(layer.id)"><X :size="14" /></button>
            </span>
          </li>
        </template>
        <li v-if="layers.length === 0" class="no-layers">Noch keine Ebenen hinzugefügt.</li>
      </ul>

      <div class="add-layer">
        <input
          v-model="layerSearch"
          type="search"
          placeholder='Direkt suchen und hinzufügen ("Bayern", "Sommerferien", "Sonnenfinsternis" …)'
        />
        <div class="search-results">
          <div v-for="grp in groupedOptions" :key="grp.group" class="search-group-block">
            <h4 class="search-group-title">{{ grp.group }} <span class="search-group-count">({{ grp.total }})</span></h4>
            <ul>
              <li v-for="option in grp.visible" :key="option.id">
                <button type="button" @click="selectOption(option)">{{ option.label }}</button>
              </li>
            </ul>
            <button v-if="grp.more > 0" type="button" class="show-more-button" @click="expandGroup(grp.group)">
              +{{ grp.more }} weitere anzeigen
            </button>
          </div>
          <p v-if="groupedOptions.length === 0" class="no-results">Keine Treffer</p>
        </div>
      </div>
    </aside>
    </div>

    <div v-if="!props.embed" class="embed-bar">
      <button type="button" @click="toggleEmbedPanel">Einbetten</button>
      <div v-if="showEmbed" class="embed-panel">
        <label for="embed-url">Link zum Einbetten</label>
        <input id="embed-url" type="text" readonly :value="embedUrl" @click="selectEmbedUrl" />
        <button type="button" @click="copyEmbedUrl">{{ copied ? "Kopiert!" : "Kopieren" }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calendar {
  font-size: 0.9rem;
}

.calendar-layout {
  display: flex;
  align-items: flex-start;
  gap: 2rem;
}
.main-area {
  flex: 1;
  min-width: 0;
}
.sidebar {
  width: 18rem;
  flex-shrink: 0;
  position: sticky;
  top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.breadcrumbs {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 1rem;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.85rem;
}
.breadcrumbs button {
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: inherit;
}
.breadcrumbs button:hover {
  color: var(--accent);
}
.graph-toggle {
  margin-left: auto;
}

.granularity-toggle {
  display: flex;
  justify-content: center;
  gap: 0.4rem;
  margin-bottom: 1rem;
}
.granularity-toggle button {
  font-size: 0.78rem;
  padding: 0.25rem 0.7rem;
}
.granularity-toggle button.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}

.year-nav {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-family: var(--font-mono);
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--line);
}
.year-nav span {
  min-width: 3ch;
  text-align: center;
  cursor: pointer;
}
.year-nav span:hover {
  color: var(--accent);
}
.year-input {
  width: 10ch;
  font: inherit;
  font-family: var(--font-mono);
  text-align: center;
  background: var(--paper);
  border: 1px solid var(--line);
  color: var(--ink);
  /* Native spin buttons eat into the width, clipping the digits - the
     input is still type="number" for the numeric keypad/validation, just
     without the visible steppers. */
  -moz-appearance: textfield;
}
.year-input::-webkit-outer-spin-button,
.year-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.year-nav button,
.view-nav button {
  cursor: pointer;
  background: none;
  border: none;
  color: var(--ink);
  display: inline-flex;
  padding: 0.15rem;
}
.year-nav button:disabled,
.view-nav button:disabled {
  color: var(--muted);
  cursor: default;
  opacity: 0.4;
}
.year-nav button:not(:disabled):hover,
.view-nav button:not(:disabled):hover {
  color: var(--accent);
}

.layer-list-actions {
  display: flex;
  justify-content: flex-end;
}
.reset-layers {
  font-size: 0.75rem;
  padding: 0.2rem 0.5rem;
  color: var(--muted);
}
.reset-layers:hover {
  color: var(--accent);
}

.layer-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
}
.layer-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.5rem 0.1rem;
  border-bottom: 1px solid var(--line);
}
.layer-list label {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
  min-width: 0;
  flex: 1 1 auto;
}
.layer-group-header {
  padding: 0.6rem 0.1rem 0.2rem !important;
  border-bottom: none !important;
}
.layer-group-header:not(:first-child) {
  margin-top: 0.2rem;
}
.layer-group-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
}
.layer-label-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.no-layers {
  color: var(--muted);
  font-size: 0.85rem;
  padding: 0.5rem 0.1rem;
}
.layer-actions {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  font-size: 0.8rem;
  flex-shrink: 0;
}
.layer-actions a {
  font-family: var(--font-mono);
  text-decoration: none;
}
.layer-actions button {
  cursor: pointer;
  background: none;
  border: none;
  display: inline-flex;
  color: var(--muted);
  padding: 0;
}
.layer-actions button:hover {
  color: var(--accent);
}
.dot {
  width: 0.65rem;
  height: 0.65rem;
  display: inline-block;
  flex-shrink: 0;
}

.add-layer {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.5rem;
  position: relative;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
}
.search-results {
  max-height: 22rem;
  overflow-y: auto;
  border: 1px solid var(--line);
}
.search-results:empty {
  border: none;
}
.search-group-block {
  background: var(--paper);
  border-bottom: 1px solid var(--line);
  padding: 0.5rem 0;
}
.search-group-block:last-child {
  border-bottom: none;
}
.search-group-title {
  margin: 0;
  padding: 0.2rem 0.6rem 0.35rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
}
.search-group-count {
  font-weight: 400;
  text-transform: none;
  letter-spacing: normal;
}
.search-group-block ul {
  list-style: none;
  padding: 0;
  margin: 0;
}
.search-group-block button {
  width: 100%;
  text-align: left;
  border: none;
  background: none;
  padding: 0.4rem 0.6rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.search-group-block li button:hover {
  background: var(--paper-raised);
  color: var(--accent);
}
.show-more-button {
  color: var(--muted);
  font-style: italic;
}
.show-more-button:hover {
  color: var(--accent);
  background: none !important;
}
.no-results {
  color: var(--muted);
  padding: 0.4rem 0.6rem;
  font-size: 0.85rem;
  margin: 0;
}

.months {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.month {
  background: var(--paper);
  padding: 0.9rem;
}
.month h3 {
  margin: 0 0 0.6rem;
  font-size: 0.85rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  cursor: pointer;
  width: fit-content;
}
.month h3:hover {
  color: var(--accent);
}
.weekdays,
.day-week {
  display: grid;
  grid-template-columns: 1.4rem repeat(7, 1fr);
  gap: 2px;
}
.day-week {
  margin-bottom: 2px;
}
.weekdays span {
  text-align: center;
  color: var(--muted);
  font-size: 0.68rem;
}
.week-col-header {
  font-family: var(--font-mono);
}
.day {
  text-align: center;
  padding: 0.2rem 0;
  cursor: pointer;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.day:hover {
  background: var(--paper-raised);
}
.day.today {
  background: var(--accent);
  color: var(--accent-ink);
}
.day.other-month {
  color: var(--muted);
  opacity: 0.5;
}
.marks {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 1px;
  min-height: 0.3rem;
  margin-top: 0.15rem;
}
.mark {
  width: 0.3rem;
  height: 0.3rem;
  display: inline-block;
}
.mark:hover {
  outline: 1px solid var(--ink);
  outline-offset: 1px;
}

.view-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-bottom: 1rem;
}
.view-nav h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 500;
  min-width: 14ch;
  text-align: center;
}

.month-grid-header,
.week-row {
  display: grid;
  grid-template-columns: 2.5rem repeat(7, 1fr);
  gap: 2px;
}
.month-grid-header {
  margin-bottom: 2px;
}
.month-grid-header span {
  text-align: center;
  color: var(--muted);
  font-size: 0.7rem;
}
.week-number-header {
  font-family: var(--font-mono);
}
.week-row {
  background: var(--line);
  margin-bottom: 2px;
  cursor: pointer;
}
.week-row:hover .day-cell {
  background: var(--paper-raised);
}
.week-number {
  background: var(--paper);
  border: none;
  cursor: pointer;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.week-number:hover {
  color: var(--accent);
  background: var(--paper-raised);
}
.week-number.mini {
  background: none;
  font-size: 0.62rem;
  padding: 0;
}
.day-cell {
  background: var(--paper);
  min-height: 4rem;
  padding: 0.4rem;
  display: flex;
  flex-direction: column;
  font-family: var(--font-mono);
}
.day-cell.other-month {
  color: var(--muted);
  opacity: 0.5;
}
.day-cell.today {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.day-cell.today .day-number {
  color: var(--accent);
  font-weight: 600;
}
.day-number {
  font-variant-numeric: tabular-nums;
}
.day-cell .marks {
  justify-content: flex-start;
  margin-top: auto;
}

.week-days {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.day-column {
  background: var(--paper);
  padding: 0.7rem;
  min-height: 10rem;
}
.day-column.today {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.day-column.today h4 {
  color: var(--accent);
}
.day-column.selected {
  background: var(--paper-raised);
  outline: 2px dashed var(--accent);
  outline-offset: -2px;
}
.day-column h4 {
  margin: 0 0 0.6rem;
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
}
.day-column .day-number {
  color: var(--ink);
  font-weight: 600;
}
.event-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.78rem;
}
.event-link {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: inherit;
  text-decoration: none;
}
.event-link:hover {
  color: var(--accent);
}
.event-list .dot {
  margin-top: 0.3rem;
  flex-shrink: 0;
}
.no-events {
  color: var(--muted);
}

.graph-rows {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}
.graph-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.graph-row-label,
.graph-row-label-spacer {
  width: 12rem;
  flex-shrink: 0;
}
.graph-row-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  font-size: 0.8rem;
}
.graph-bars {
  flex: 1;
  display: grid;
  gap: 3px;
  height: 3rem;
  overflow-x: auto;
}
.graph-bar-slot {
  height: 100%;
  display: flex;
  align-items: flex-end;
  background: var(--paper-raised);
}
.graph-bar {
  width: 100%;
  min-height: 2px;
}
.graph-months-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.4rem;
}
.graph-months {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 3px;
}
.graph-months span {
  text-align: center;
  font-size: 0.65rem;
  color: var(--muted);
}

.embed-bar {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
}
.embed-panel {
  margin-top: 0.75rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.embed-panel label {
  width: 100%;
  font-size: 0.8rem;
  color: var(--muted);
}
.embed-panel input {
  flex: 1;
  min-width: 14rem;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

@media (max-width: 60rem) {
  .calendar-layout {
    flex-direction: column;
  }
  .sidebar {
    width: 100%;
    position: static;
    order: -1;
  }
  .week-days {
    grid-template-columns: 1fr;
  }
}
</style>
