<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { CalendarDays, CalendarPlus, ChevronLeft, ChevronRight, Search, Trash2, X } from "lucide-vue-next";
import { MONTH_NAMES, isoWeekNumber } from "../../lib/date-display";
import { isoFromDate, mondayOf } from "../../lib/date-grid";
import {
  type CalendarState,
  type CalendarView,
  YEAR_MAX,
  YEAR_MIN,
  buildCalendarParams,
  isCalendarView,
  parseCalendarUrl,
} from "../../lib/calendar-url";
import { COLORS } from "../../lib/calendar-colors";
import GraphView from "./calendar/GraphView.vue";
import MonthView from "./calendar/MonthView.vue";
import PlannerView from "./calendar/PlannerView.vue";
import WeekView from "./calendar/WeekView.vue";
import YearView from "./calendar/YearView.vue";

// Overlay mode (PLAN.md 4.2): layers render stacked, no set operations
// (intersections are explicitly NOT V1). The component has no knowledge of
// content categories at all - every selectable thing (a country's Feiertage,
// a Bundesland x Ferientyp combination, a fruit's season, a scraped page
// with dates) is just a CatalogEntry from /api/v1/calendar.json. Adding a
// new content type to the calendar means extending lib/calendar-sources.ts
// server-side; nothing here needs to change.
//
// This file owns STATE, not rendering: the layer catalog/sidebar, the
// visible period, the active template, and the URL sync. Every way of
// drawing that state is a component in ./calendar/ that takes props and
// emits navigation intent - so a new template (a Familienplaner with a row
// per day, say) is a new file plus one entry in VIEW_OPTIONS below, not
// another branch in here.
const VIEW_OPTIONS: { id: CalendarView; label: string }[] = [
  { id: "year", label: "Jahr" },
  { id: "month", label: "Monat" },
  { id: "week", label: "Woche" },
  { id: "planner", label: "Planer" },
  { id: "graph", label: "Verteilung" },
];

// Templates that show one month and navigate by month - they share the
// prev/next handlers and the "am I looking at today" check below.
const MONTH_NAV_VIEWS: CalendarView[] = ["month", "planner"];
const VIEW_STORAGE_KEY = "wann:kalender-view";

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

// Set by src/pages/kalender/embed.astro (the standalone iframe-embeddable
// page, no header/footer/nav chrome) - hides the "Einbetten" button there,
// since offering to embed a page that's already an embed is pointless.
const props = defineProps<{ embed?: boolean }>();

const today = new Date();
const todayIso = isoFromDate(today);

const year = ref(today.getFullYear());
const layers = ref<Layer[]>([]);
const loading = ref(true);

const view = ref<CalendarView>("year");
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
// Id of the layer whose feed URL is currently revealed, and the id whose URL
// was just copied - kept separate from `copied` above, which belongs to the
// embed panel's button label.
const revealedFeed = ref<string | null>(null);
const copiedFeed = ref<string | null>(null);

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
// openWeek, the breadcrumbs' "go up a level" clicks, the view switcher) so
// the resulting writeUrl() call pushes a real history entry instead of
// replacing - without this, the whole calendar session was one single
// history entry, and the browser's back button skipped straight past every
// view the user had navigated through, out of the calendar entirely.  Left
// false for lateral/continuous changes (prev/next month or week, year +/-,
// layer search) - each of those becoming its own back-button stop would be
// far more annoying than helpful.
let pushNextUrlWrite = false;

function currentState(): CalendarState {
  return {
    year: year.value,
    view: view.value,
    monthIndex0: activeMonth.value,
    weekStartIso: weekStart.value,
    selectedDay: selectedDay.value,
    layerIds: layers.value.map((l) => l.id),
  };
}

function writeUrl() {
  const url = `${window.location.pathname}?${buildCalendarParams(currentState(), false)}`;
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
  return `${window.location.origin}/kalender/embed/?${buildCalendarParams(currentState(), true)}`;
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

function selectAllOnClick(e: Event) {
  (e.target as HTMLInputElement).select();
}

// layer.feedUrl is a relative path (lib/calendar-sources.ts) - fine as an
// href, useless once pasted into a calendar app, so absolutize it. Same
// SSR guard as embedUrl above: this component is server-rendered before it
// hydrates, and there is no `window` then.
function absoluteFeedUrl(feedUrl: string): string {
  if (typeof window === "undefined") return feedUrl;
  return new URL(feedUrl, window.location.origin).href;
}

function toggleFeed(id: string) {
  revealedFeed.value = revealedFeed.value === id ? null : id;
}

async function copyFeedUrl(layer: { id: string; feedUrl: string }) {
  await navigator.clipboard.writeText(absoluteFeedUrl(layer.feedUrl));
  copiedFeed.value = layer.id;
  setTimeout(() => {
    if (copiedFeed.value === layer.id) copiedFeed.value = null;
  }, 1500);
}

// Only the switcher writes this (see selectView) - a ?day= link from a
// topic page forces week view, and persisting *that* would pin a visitor to
// week view forever after a single date link.
function storedView(): CalendarView {
  try {
    const stored = localStorage.getItem(VIEW_STORAGE_KEY);
    return isCalendarView(stored) ? stored : "year";
  } catch {
    // Safari private mode and strict-cookie setups throw here, and this sits
    // on the only path that initializes the calendar - an escaping throw
    // would leave the skeleton on screen forever.
    return "year";
  }
}

// Resets EVERY piece of state to match the current URL - not just the params
// that happen to be present - so this is safe to call both on initial mount
// and again on popstate (the browser back/forward buttons), when a previous,
// differently-shaped URL needs to fully replace the current state rather
// than merely patch it.
async function loadFromUrlOrDefault() {
  const state = parseCalendarUrl(window.location.search, today, storedView());
  year.value = state.year;
  view.value = state.view;
  activeMonth.value = state.monthIndex0;
  weekStart.value = state.weekStartIso;
  selectedDay.value = state.selectedDay;

  // No baked-in defaults (no preferred Bundesland/variety) - the user builds
  // their own selection through search, see the empty-layers hint below.
  // Synced in both directions (not just "add what's missing") so navigating
  // back to a state with fewer layers actually drops the extra ones.
  const layerIds = new Set(state.layerIds);
  layers.value = layers.value.filter((l) => layerIds.has(l.id));
  await Promise.all(
    [...layerIds]
      .filter((id) => !layers.value.some((l) => l.id === id))
      .map((id) => catalog.value.find((entry) => entry.id === id))
      .filter((entry): entry is CatalogEntry => entry !== undefined)
      .map((entry) => addLayer(entry)),
  );
}

// The no-op guard matters: clicking the already-active switcher button would
// otherwise arm pushNextUrlWrite with nothing to flush it, so the *next*
// lateral change (prev month, year +/-, a layer toggle) would silently
// become a history entry - the exact back-button pollution the flag exists
// to avoid.
function setView(next: CalendarView) {
  if (view.value === next) return;
  pushNextUrlWrite = true;
  view.value = next;
}

// The switcher is the only deliberate "I want this template" signal, so it
// is the only thing that persists a preference - and it persists even on a
// re-click of the active button, which setView() above ignores.
function selectView(next: CalendarView) {
  setView(next);
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, next);
  } catch {
    // See storedView(): storage can throw, and losing the preference is a
    // far better outcome than losing the click.
  }
}

function openMonth(monthIndex0: number) {
  activeMonth.value = monthIndex0;
  setView("month");
}

function openWeek(mondayIso: string) {
  selectedDay.value = null;
  weekStart.value = mondayIso;
  activeMonth.value = Number(mondayIso.slice(5, 7)) - 1;
  setView("week");
}

function openWeekForDay(dayIso: string) {
  openWeek(isoFromDate(mondayOf(new Date(`${dayIso}T00:00:00`))));
}

// Jumps to "now" in whatever unit the active template actually shows - the
// year in year/graph view, the month (+ year) in month view, this week in
// week view. openWeek() already resets a drilled-into selectedDay, so week
// is delegated to it instead of duplicating that reset here.
function goToToday() {
  if (view.value === "week") {
    openWeek(isoFromDate(mondayOf(today)));
    return;
  }
  pushNextUrlWrite = true;
  year.value = today.getFullYear();
  if (MONTH_NAV_VIEWS.includes(view.value)) activeMonth.value = today.getMonth();
}

// Hides the "Heute" button once it would be a no-op - same unit goToToday()
// itself jumps by.
const isAtToday = computed(() => {
  if (view.value === "week") return weekStart.value === isoFromDate(mondayOf(today));
  if (year.value !== today.getFullYear()) return false;
  return !MONTH_NAV_VIEWS.includes(view.value) || activeMonth.value === today.getMonth();
});

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

// One step forwards/backwards in whatever unit the active template shows -
// what the arrow keys drive, sharing the prev/next buttons' own rules rather
// than a second copy of them.
function step(delta: number) {
  if (view.value === "week") {
    changeWeek(delta);
  } else if (MONTH_NAV_VIEWS.includes(view.value)) {
    changeMonth(delta);
  } else {
    const next = year.value + delta;
    if (next >= YEAR_MIN && next <= YEAR_MAX) year.value = next;
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  // A modified arrow is someone else's shortcut (word-wise caret movement,
  // browser history, a screen reader), never ours.
  if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
  const el = document.activeElement;
  if (el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
  e.preventDefault();
  step(e.key === "ArrowRight" ? 1 : -1);
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

const currentWeekNumber = computed(() => isoWeekNumber(new Date(`${weekStart.value}T00:00:00`)));

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
  window.addEventListener("keydown", onKeydown);
});

// Astro's View Transitions tear this island down and build a fresh one on
// every navigation - without the removal, entering the calendar page N times
// leaves N popstate listeners behind, each bound to a destroyed instance.
onUnmounted(() => {
  window.removeEventListener("popstate", loadFromUrlOrDefault);
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="calendar">
    <div class="calendar-layout">
    <div class="main-area">
      <div v-if="loading" class="skeleton" aria-hidden="true">
        <div class="skeleton-bar skeleton-breadcrumbs"></div>
        <div class="skeleton-grid">
          <div v-for="n in 12" :key="n" class="skeleton-cell">
            <div class="skeleton-bar skeleton-month-title"></div>
            <div class="skeleton-bar skeleton-month-body"></div>
          </div>
        </div>
      </div>
      <p v-if="loading" class="sr-only">Kalender lädt…</p>

      <template v-else>
        <nav class="breadcrumbs" aria-label="Brotkrumen">
          <button type="button" class="crumb" @click="setView('year')">{{ year }}</button>
          <template v-if="view === 'week' || MONTH_NAV_VIEWS.includes(view)">
            <ChevronRight :size="14" />
            <button type="button" class="crumb" @click="setView('month')">{{ MONTH_NAMES[activeMonth] }}</button>
          </template>
          <template v-if="view === 'week'">
            <ChevronRight :size="14" />
            <span>KW {{ currentWeekNumber }}</span>
          </template>
          <div class="breadcrumb-actions">
            <button v-if="!isAtToday" type="button" class="action-button" title="Zu heute springen" @click="goToToday">
              <CalendarDays :size="14" /> Heute
            </button>
            <div class="view-switch" role="group" aria-label="Ansicht">
              <button
                v-for="option in VIEW_OPTIONS"
                :key="option.id"
                type="button"
                :class="{ active: view === option.id }"
                :aria-pressed="view === option.id"
                @click="selectView(option.id)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
        </nav>

        <p v-if="layers.length === 0 && view !== 'graph'" class="onboarding-hint">
          Der Kalender ist noch leer. Rechts im Suchfeld eine Ebene hinzufügen (z. B. "Bayern"
          oder "Sommerferien"), um sie hier farbig zu sehen.
        </p>

        <YearView
          v-if="view === 'year'"
          :year="year"
          :layers="layers"
          :today-iso="todayIso"
          @month-click="openMonth"
          @day-click="openWeekForDay"
          @week-click="openWeek"
        />

        <MonthView
          v-else-if="view === 'month'"
          :year="year"
          :month-index0="activeMonth"
          :layers="layers"
          :today-iso="todayIso"
          :prev-disabled="year <= YEAR_MIN && activeMonth === 0"
          :next-disabled="year >= YEAR_MAX && activeMonth === 11"
          @prev="changeMonth(-1)"
          @next="changeMonth(1)"
          @week-click="openWeek"
        />

        <WeekView
          v-else-if="view === 'week'"
          :week-start="weekStart"
          :layers="layers"
          :today-iso="todayIso"
          :selected-day="selectedDay"
          :prev-disabled="year <= YEAR_MIN"
          :next-disabled="year >= YEAR_MAX"
          @prev="changeWeek(-1)"
          @next="changeWeek(1)"
        />

        <PlannerView
          v-else-if="view === 'planner'"
          :year="year"
          :month-index0="activeMonth"
          :layers="layers"
          :today-iso="todayIso"
          :prev-disabled="year <= YEAR_MIN && activeMonth === 0"
          :next-disabled="year >= YEAR_MAX && activeMonth === 11"
          @prev="changeMonth(-1)"
          @next="changeMonth(1)"
          @remove="removeLayer"
        />

        <GraphView
          v-else
          :year="year"
          :layers="layers"
          :prev-disabled="year <= YEAR_MIN"
          :next-disabled="year >= YEAR_MAX"
          @prev="year--"
          @next="year++"
        />
      </template>
    </div>

    <aside class="sidebar">
      <div v-if="view === 'year'" class="year-nav">
        <button type="button" aria-label="Vorheriges Jahr" :disabled="year <= YEAR_MIN" @click="year--"><ChevronLeft :size="16" /></button>
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
        <button type="button" aria-label="Nächstes Jahr" :disabled="year >= YEAR_MAX" @click="year++"><ChevronRight :size="16" /></button>
      </div>

      <div v-if="layers.length > 0" class="layer-list-actions">
        <button type="button" class="reset-layers" @click="resetLayers"><Trash2 :size="14" /> Alle entfernen</button>
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
              <button
                type="button"
                class="feed-toggle"
                title="Adresse des ICS-Kalenders anzeigen"
                :aria-expanded="revealedFeed === layer.id"
                @click="toggleFeed(layer.id)"
              >
                <CalendarPlus :size="13" aria-hidden="true" /> ICS
              </button>
              <button type="button" title="Ebene entfernen" @click="removeLayer(layer.id)"><X :size="14" /></button>
            </span>
            <div v-if="revealedFeed === layer.id" class="feed-panel">
              <p>Diese Adresse im Kalender abonnieren - dann kommen neue Termine automatisch dazu:</p>
              <input type="text" readonly :value="absoluteFeedUrl(layer.feedUrl)" aria-label="Adresse des ICS-Kalenders" @click="selectAllOnClick" />
              <button type="button" @click="copyFeedUrl(layer)">Kopieren</button>
              <span class="copy-status" role="status" aria-live="polite">{{ copiedFeed === layer.id ? "Kopiert!" : "" }}</span>
              <p><a :href="layer.feedUrl">.ics-Datei einmalig herunterladen</a></p>
            </div>
          </li>
        </template>
        <li v-if="layers.length === 0" class="no-layers">Noch keine Ebenen hinzugefügt.</li>
      </ul>

      <div class="add-layer">
        <div class="layer-search-wrap">
          <Search :size="14" class="search-icon" aria-hidden="true" />
          <input
            v-model="layerSearch"
            type="search"
            placeholder='Direkt suchen und hinzufügen ("Bayern", "Sommerferien", "Sonnenfinsternis" …)'
          />
        </div>
        <div class="search-results">
          <div v-for="grp in groupedOptions" :key="grp.group" class="search-group-block">
            <h3 class="search-group-title">{{ grp.group }} <span class="search-group-count">({{ grp.total }})</span></h3>
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
        <input id="embed-url" type="text" readonly :value="embedUrl" @click="selectAllOnClick" />
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
.breadcrumbs .crumb {
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: inherit;
}
.breadcrumbs .crumb:hover {
  color: var(--accent);
}
/* Heute and the view switcher are actions, not breadcrumb trail - kept as
   plain bordered buttons (the global `button` default look, not reset to
   text-only like .crumb above) so they read as clickable controls instead
   of blending into the trail's plain-text year/month/week links. */
.breadcrumb-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}
.action-button {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.3rem 0.6rem;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--ink);
}
.action-button:hover {
  color: var(--accent);
}

.view-switch {
  display: flex;
  gap: 0.3rem;
}
.view-switch button {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  padding: 0.3rem 0.6rem;
}
.view-switch button:not(.active):hover {
  color: var(--accent);
}
.view-switch button.active {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}

.onboarding-hint {
  color: var(--muted);
  font-size: 0.85rem;
  margin: 0 0 1rem;
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
/* 24px floor is WCAG 2.5.8 / Lighthouse's touch-target minimum - a 16px icon
   with 0.15rem of padding came to 21x21. Centred rather than padded up so the
   chevrons stay optically where they were. */
.year-nav button {
  cursor: pointer;
  background: none;
  border: none;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  min-height: 24px;
  padding: 0.15rem;
}
.year-nav button:disabled {
  color: var(--muted);
  cursor: default;
  opacity: 0.4;
}
.year-nav button:not(:disabled):hover {
  color: var(--accent);
}

.layer-list-actions {
  display: flex;
  justify-content: flex-end;
}
.reset-layers {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
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
  flex-wrap: wrap;
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
/* Was an <a>, now a disclosure button - keep it looking exactly the same. */
.layer-actions .feed-toggle {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: var(--accent);
  align-items: center;
  gap: 0.25rem;
}
/* Revealed feed URL, laid out like .embed-panel below (same idiom, same
   look) but as a full-width row wrapped under its layer entry. */
.feed-panel {
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.feed-panel p {
  width: 100%;
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.feed-panel input {
  flex: 1;
  min-width: 10rem;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.feed-panel > button {
  cursor: pointer;
  font-size: 0.75rem;
}
.copy-status {
  font-size: 0.75rem;
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
.layer-search-wrap {
  position: relative;
}
.layer-search-wrap .search-icon {
  position: absolute;
  left: 0.55rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--muted);
  pointer-events: none;
}
.layer-search-wrap input {
  width: 100%;
  padding-left: 1.9rem;
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

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* Mimics the year template's own layout (YearView.vue's .months/.month)
   instead of a generic spinner, so there's no layout jump once real data
   replaces it - deliberately a private copy of that geometry rather than a
   shared class, since the two are allowed to drift. */
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.skeleton-cell {
  background: var(--paper);
  padding: 0.9rem;
}
.skeleton-breadcrumbs {
  width: 8rem;
  height: 0.85rem;
  margin-bottom: 1rem;
}
.skeleton-month-title {
  width: 5rem;
  height: 0.7rem;
  margin-bottom: 0.6rem;
}
.skeleton-month-body {
  height: 8rem;
}
.skeleton-bar {
  background: var(--paper-raised);
  animation: skeleton-pulse 1.4s ease-in-out infinite;
}
@keyframes skeleton-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
@media (prefers-reduced-motion: reduce) {
  .skeleton-bar {
    animation: none;
    opacity: 0.7;
  }
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
}

/* Printing any template means printing the calendar, not the app around it
   - the layer picker, the trail, the switcher and the embed box are all
   controls, and none of them survives leaving the screen. Kept here rather
   than in PlannerView.vue (the one template built to be printed) because
   this chrome belongs to this component and scoped styles cannot reach up. */
@media print {
  .breadcrumbs,
  .sidebar,
  .embed-bar,
  .onboarding-hint {
    display: none;
  }
  .calendar-layout {
    display: block;
  }
}
</style>
