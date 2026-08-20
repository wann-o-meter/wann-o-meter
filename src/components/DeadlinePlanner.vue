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
import {
  Bookmark,
  BookmarkCheck,
  CalendarDays,
  CalendarPlus,
  ChevronDown,
  ChevronUp,
  Eye,
  ListPlus,
  Plus,
  Search,
  X,
} from "lucide-vue-next";
import Timeline from "./deadline-planner/Timeline.vue";
import TaskRail from "./deadline-planner/TaskRail.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import OrtPicker from "./deadline-planner/OrtPicker.vue";
import PlanSummary from "./deadline-planner/PlanSummary.vue";
import PlanActions from "./deadline-planner/PlanActions.vue";
import DoneGroup from "./deadline-planner/DoneGroup.vue";
import { facetLabel } from "../../lib/facets";
import { formatDate } from "../../lib/format-date";
import { offsetLabel } from "../../lib/offset-label";
import {
  forgetPlan,
  loadSavedPlans,
  planStorageKey,
  savePlan,
} from "../../lib/saved-plans";
import { downloadIcs } from "../../lib/ics-download";
import { burst } from "./deadline-planner/confetti";
import { useTaskEditor } from "./deadline-planner/useTaskEditor";
import { usePlanUrlState } from "./deadline-planner/usePlanUrlState";
import { useStickyHeader } from "./deadline-planner/useStickyHeader";
import { useTaskPicker } from "./deadline-planner/useTaskPicker";
import {
  ANCHOR_ID,
  usePlannerSchedule,
} from "./deadline-planner/usePlannerSchedule";
import type { TaskStore } from "./deadline-planner/task-store";
import type { PlanVariant } from "./deadline-planner/types";
import type { EditorKind, TaskPatch } from "./deadline-planner/task-card";
import type { ScheduleEntry } from "../../lib/deadline-plan";
import type { Gemeinde } from "../../lib/gemeinde-search";

export type { PlanVariant };

const props = defineProps<{
  slug: string;
  vorhaben: string;
  anchorLabel: string;
  anchorName: string;
  variantLabel: string;
  variantPreposition?: string;
  variants: PlanVariant[];
  defaultSlug?: string;
}>();

const rootEl = useTemplateRef<HTMLElement>("rootEl");
const railEl = useTemplateRef<HTMLElement>("railEl");
const headerEl = useTemplateRef<HTMLElement>("headerEl");
const sentinelEl = useTemplateRef<HTMLElement>("sentinelEl");

const {
  selectedSlug,
  selected,
  region,
  ortName,
  selectedForPlan,
  anchorDate,
  activeFacets,
  facetOptions,
  overlapMonths,
  touched,
} = usePlanUrlState(props.slug, props.variants, props.defaultSlug);

// Keeping a plan is the visitor's decision, not a side effect of opening one.
// Once kept, it follows whatever they change afterwards.
const kept = ref(loadSavedPlans().some((p) => p.slug === props.slug));

function planRecord() {
  // Both only say something for a variant without a Bundesland of its own,
  // otherwise they repeat what the Ort file already says.
  const own = props.variants.find(
    (v) => v.slug === selectedSlug.value,
  )?.regionCode;
  return {
    slug: props.slug,
    variant: selectedSlug.value,
    region: own ? undefined : selected.value?.regionCode,
    ort: own ? undefined : ortName.value || undefined,
    date: anchorDate.value,
    facets: [...activeFacets.value],
  };
}

// The same burst the checkboxes use, then the button collapses into the space
// it just filled: the plan is kept, the ask is done.
function keepWithBurst(event: MouseEvent) {
  burst(event.currentTarget as Element);
  toggleKept();
}

function toggleKept() {
  if (kept.value) {
    forgetPlan(props.slug);
    kept.value = false;
    return;
  }
  savePlan(planRecord());
  kept.value = true;
}

watch([anchorDate, selectedSlug, activeFacets, ortName], () => {
  if (kept.value && anchorDate.value) savePlan(planRecord());
});

const {
  doneIds,
  userNotes,
  attachments,
  lastHidden,
  hiddenTasks,
  workingDeadlines,
  isCustom,
  toggleDone,
  commitLabel,
  commitNote,
  commitAttachment,
  ensureAttachment,
  hideEntry,
  unhide,
  insertCustomTask,
  addTaskAtEnd,
} = useTaskEditor(
  selectedForPlan,
  computed(() => planStorageKey(props.vorhaben, selectedSlug.value)),
);

const { timeline, tasks, unscheduled, railNodes } = usePlannerSchedule(
  anchorDate,
  selected,
  workingDeadlines,
  () => props.anchorLabel,
  doneIds,
  overlapMonths,
);

const { stuck, headerGap } = useStickyHeader(rootEl, headerEl, sentinelEl);

const editor = ref<{ id: string; kind: EditorKind } | null>(null);

// A task added without a preset has no title yet, so it opens straight into
// its title editor.
function nameIfBlank(id: string, label?: string) {
  if (!label) editor.value = { id, kind: "label" };
}

const picker = useTaskPicker({
  insertInGap: (after, before, label) =>
    nameIfBlank(insertCustomTask(after, before, label), label),
  addAtEnd: (label) =>
    nameIfBlank(
      addTaskAtEnd(
        timeline.value
          .filter((e) => e.offset_days !== null)
          .map((e) => e.offset_days!),
        label,
      ),
      label,
    ),
});

// Kept in sync by hand with lib/vorhaben-data, importing it would pull node:fs
// into the browser bundle.
const isBundesweit = computed(() => selectedSlug.value === "bundesweit");

const ortLabel = computed(() =>
  isBundesweit.value
    ? (ortName.value || "ganz Deutschland")
    : (selected.value?.label ?? ""),
);

// An Ort we have a file for switches the plan, any other one only lends its
// Bundesland so the Feiertage are the right ones.
function onPickOrt(g: Gemeinde | null) {
  const variant = props.variants.find((v) => v.label === g?.name);
  if (variant) {
    selectedSlug.value = variant.slug;
    ortName.value = "";
    region.value = "";
    return;
  }
  selectedSlug.value = "bundesweit";
  ortName.value = g?.name ?? "";
  region.value = g?.state ?? "";
}

const dateEl = useTemplateRef<HTMLInputElement>("dateEl");
// A transparent date input only opens its picker when the calendar icon is hit,
// so the whole slot triggers it instead.
function openDatePicker() {
  try {
    dateEl.value?.showPicker();
  } catch {
    dateEl.value?.focus();
  }
}

const store = computed<TaskStore>(() => ({
  doneIds,
  userNotes,
  attachments,
  isCustom,
  editorFor: (id) => (editor.value?.id === id ? editor.value.kind : null),
  setEditor: (id, kind) => {
    if (kind === "attachment") ensureAttachment(id);
    editor.value = kind ? { id, kind } : null;
  },
  hideEntry,
  applyPatch: (entry: ScheduleEntry, patch: TaskPatch) => {
    if (patch.label !== undefined) commitLabel(entry.id, patch.label);
    if (patch.note !== undefined) commitNote(entry.id, patch.note);
    if (patch.attachment !== undefined)
      commitAttachment(entry.id, patch.attachment);
  },
}));

function onToggleDone(id: string) {
  touched.value = true;
  const wasDone = doneIds[id];
  toggleDone(id);
  if (!wasDone)
    burst(rootEl.value?.querySelector(`[data-entry-id="${id}"] .check`));
}

const planEntries = computed(() =>
  timeline.value.filter((e) => e.id !== ANCHOR_ID),
);
const doneEntries = computed(() =>
  planEntries.value.filter((e) => doneIds[e.id]),
);

// The same sentences the page renders before hydration, counted from the plan
// the visitor sees now. Keep in sync with the .overview paragraph in
// src/pages/[...slug].astro.
const overview = computed(() => {
  const entries = planEntries.value;
  const base = new Set(
    (props.variants.find((v) => v.slug === "bundesweit")?.deadlines ?? []).map(
      (d) => d.id,
    ),
  );
  const dated = entries.filter((e) => e.kind !== "soft");
  return {
    total: dated.length,
    softCount: entries.length - dated.length,
    earliest: dated[0] ?? null,
    afterAnchor: dated.filter((e) => (e.offset_days ?? 0) > 0).length,
    officeSteps: entries.filter((e) => e.needs_office).map((e) => e.label),
    undated: dated.filter((e) => e.offset_days === null).length,
    localSteps: isBundesweit.value
      ? []
      : entries
        .filter((e) => !base.has(e.id) && !isCustom(e.id))
        .map((e) => e.label.split(" ")[0]),
  };
});

// A soft step keeps its place in the order, but never a marker on the timeline:
// a dot would sit on a day nobody can defend.
const datedTasks = computed(() => tasks.value.filter((t) => t.kind !== "soft"));

const openNodes = computed(() => {
  const out: typeof railNodes.value = [];
  for (const node of railNodes.value) {
    if (node.kind === "item" && node.entry.id === ANCHOR_ID) continue;
    if (node.kind === "gap" && out[out.length - 1]?.kind !== "item") continue;
    out.push(node);
  }
  while (out.length > 0 && out[out.length - 1].kind === "gap") out.pop();
  return out;
});

// A plan can run to twenty tasks, so finding one by name beats scrolling.
const searchOpen = ref(false);
const taskQuery = ref("");
const searchEl = useTemplateRef<HTMLInputElement>("searchEl");
function toggleSearch() {
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) nextTick(() => searchEl.value?.focus());
  else taskQuery.value = "";
}
// While filtering the rail is a list, not a timeline: a gap between two tasks
// that are no longer neighbours would measure nothing.
const shownNodes = computed(() => {
  const q = taskQuery.value.trim().toLowerCase();
  if (!q) return openNodes.value;
  return openNodes.value.filter(
    (n) => n.kind === "item" && n.entry.label.toLowerCase().includes(q),
  );
});

const hoveredId = ref<string | null>(null);
let flashTimer: ReturnType<typeof setTimeout> | undefined;
function onTimelineSelect(id: string) {
  railEl.value
    ?.querySelector(`[data-entry-id="${id}"]`)
    ?.scrollIntoView({ block: "start", behavior: "smooth" });
  hoveredId.value = id;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    if (hoveredId.value === id) hoveredId.value = null;
  }, 1600);
}

const timelineHidden = ref(false);

// Parked, not deleted: the bar keeps the slot, we bring this back later.
const SHOW_FAB = false;
const fabOpen = ref(false);
const hasSlot = ref(false);
function fabDo(action: () => void) {
  fabOpen.value = false;
  action();
}
function addTask() {
  picker.toggle({ kind: "end" });
  rootEl.value
    ?.querySelector(".add-end-wrap")
    ?.scrollIntoView({ block: "center", behavior: "smooth" });
}

const calendarName = computed(
  () => `${props.vorhaben} - ${selected.value?.label ?? ""}`,
);
const fileSlug = computed(() => selected.value?.slug ?? "plan");
const exportIcs = () =>
  downloadIcs(
    timeline.value,
    calendarName.value,
    fileSlug.value,
    anchorDate.value,
  );

const scrollActiveId = ref<string | null>(null);
const activeId = computed(() => hoveredId.value ?? scrollActiveId.value);

let spyFrame = 0;
function trackActiveCard() {
  if (spyFrame) return;
  spyFrame = requestAnimationFrame(() => {
    spyFrame = 0;
    const cards =
      railEl.value?.querySelectorAll<HTMLElement>("[data-entry-id]") ?? [];
    const line = (headerEl.value?.offsetHeight ?? 0) + 80;
    let best: string | null = null;
    let bestDistance = Infinity;
    for (const el of cards) {
      const box = el.getBoundingClientRect();
      if (box.bottom < line) continue;
      const distance = Math.abs(box.top - line);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = el.dataset.entryId ?? null;
      }
    }
    scrollActiveId.value = best;
  });
}

onMounted(() => {
  hasSlot.value = !!document.getElementById("fab-slot");
  // The rest of the pre-hydration fallback is hidden by the js flag before the
  // first paint, only the title has to go once the planner renders its own.
  document.getElementById("static-title")?.remove();
  addEventListener("scroll", trackActiveCard, { passive: true });
  trackActiveCard();
});

onBeforeUnmount(() => {
  removeEventListener("scroll", trackActiveCard);
  cancelAnimationFrame(spyFrame);
});
</script>

<template>
  <div ref="rootEl" class="deadline-planner" :class="{ compact: stuck }">
    <div class="title-row">
      <h1 class="title">
      {{ anchorName }} am
      <span class="slot" @click="openDatePicker">
        <span aria-hidden="true">{{
          anchorDate ? formatDate(anchorDate) : anchorLabel
        }}</span>
        <input
          ref="dateEl"
          v-model="anchorDate"
          type="date"
          :aria-label="anchorLabel"
        />
      </span>
      <template v-if="variants.length > 1">
        {{ isBundesweit && !ortName ? "in" : (variantPreposition ?? "in") }}
        <OrtPicker
          :label="ortLabel"
          :variant-label="variantLabel"
          :variants="variants"
          bundesweit-slug="bundesweit"
          @pick="onPickOrt"
        />
      </template>
      </h1>
      <Transition name="implode">
        <button v-if="!kept" type="button" class="save" @click="keepWithBurst">
          <Bookmark :size="16" /> Plan merken
        </button>
      </Transition>
    </div>

    <p v-if="overview.total > 0" class="overview">
      Der Zeitplan für {{ vorhaben }} umfasst
      <b>{{ overview.total }} Fristen</b>.
      <template v-if="overview.earliest">
        Die erste ist {{ overview.earliest.label }} ({{
          offsetLabel(overview.earliest, anchorLabel)
        }}).
      </template>
      <template v-if="overview.afterAnchor > 0">
        {{ overview.afterAnchor }} davon fallen erst nach dem
        {{ anchorLabel }} an.
      </template>
      <template v-if="overview.officeSteps.length > 0">
        <b>
          {{ overview.officeSteps.length }}
          {{
            overview.officeSteps.length === 1
              ? "Frist braucht"
              : "Fristen brauchen"
          }}
          einen Termin beim Amt</b
        >
        ({{ overview.officeSteps.join(", ") }}). Solche Termine sind je nach
        Stadt Wochen im Voraus vergeben, deshalb steht der Plan rückwärts und
        nicht als Liste zum Abarbeiten.
      </template>
      <template v-if="overview.softCount > 0">
        Dazu kommen {{ overview.softCount }} Schritte ohne feste Frist.
      </template>
      <template v-if="overview.localSteps.length > 0">
        In {{ selected?.label }} kommen dazu:
        {{ overview.localSteps.join(", ") }}.
      </template>
    </p>

    <div ref="sentinelEl" class="sentinel"></div>

    <header
      ref="headerEl"
      class="planner-header"
      :style="{ marginBottom: headerGap + 'px' }"
    >
      <template v-if="anchorDate">
        <PlanSummary
          :entries="planEntries"
          :done-ids="doneIds"
          :anchor-date="anchorDate"
          :anchor-label="anchorLabel"
          @select="onTimelineSelect"
        />
        <Timeline
          id="plan-timeline"
          :class="{ 'tl-off': timelineHidden }"
          :tasks="datedTasks"
          :anchor-date="anchorDate"
          :anchor-name="anchorLabel"
          :region-code="selected?.regionCode"
          :hover-id="activeId"
          :done-ids="doneIds"
          :compact="stuck"
          draggable
          drag-hint="Griff ziehen, um den Termin zu verschieben"
          @select="onTimelineSelect"
          @place="anchorDate = $event"
          @hover="hoveredId = $event"
        />
        <button
          type="button"
          class="tl-toggle"
          :aria-expanded="!timelineHidden"
          aria-controls="plan-timeline"
          @click="timelineHidden = !timelineHidden"
        >
          <component :is="timelineHidden ? ChevronDown : ChevronUp" :size="14" />
          {{ timelineHidden ? "Zeitstrahl zeigen" : "Zeitstrahl ausblenden" }}
        </button>
      </template>
    </header>

    <template v-if="anchorDate">
      <fieldset v-if="facetOptions.length > 1" class="facets">
        <legend>Trifft auf mich zu</legend>
        <div class="facet-row">
          <label v-for="id in facetOptions" :key="id" class="facet key">
            <input v-model="activeFacets" type="checkbox" :value="id" />
            <span>{{ facetLabel(id) }}</span>
          </label>
        </div>
      </fieldset>

      <h2 class="section">
        Aufgaben
        <button
          type="button"
          class="task-search-toggle"
          :aria-expanded="searchOpen"
          aria-label="Aufgaben durchsuchen"
          @click="toggleSearch"
        >
          <Search :size="14" />
        </button>
      </h2>
      <input
        v-if="searchOpen"
        ref="searchEl"
        v-model="taskQuery"
        type="search"
        class="task-search"
        aria-label="Aufgaben durchsuchen"
        placeholder="Aufgabe suchen"
      />
      <p v-if="taskQuery && shownNodes.length === 0" class="hint">
        Keine Aufgabe passt zu „{{ taskQuery }}".
      </p>
      <div ref="railEl">
        <TaskRail
          :nodes="shownNodes"
          :anchor-date="anchorDate"
          :anchor-label="anchorLabel"
          :hovered-id="activeId"
          :store="store"
          :picker="picker"
          @hover="hoveredId = $event"
          @toggle-done="onToggleDone"
        />
      </div>

      <div class="add-end-wrap">
        <button
          type="button"
          class="add-end"
          @click="picker.toggle({ kind: 'end' })"
        >
          + Eigene Aufgabe hinzufügen
        </button>
        <TaskPicker
          v-if="picker.isOpen({ kind: 'end' })"
          @pick-preset="picker.pick($event)"
          @pick-blank="picker.pick()"
        />
      </div>

      <DoneGroup :entries="doneEntries" @reopen="toggleDone" />

      <details v-if="hiddenTasks.length > 0" class="hidden-group">
        <summary>Nicht relevant für mich ({{ hiddenTasks.length }})</summary>
        <ul>
          <li v-for="task in hiddenTasks" :key="task.id">
            <span>{{ task.label }}</span>
            <button type="button" @click="unhide(task.id)">
              <Eye :size="14" /> Wieder einblenden
            </button>
          </li>
        </ul>
      </details>

      <p v-if="lastHidden" class="undo">
        „{{ lastHidden.label }}" ausgeblendet.
        <button type="button" @click="unhide()">Rückgängig</button>
      </p>

      <div v-if="unscheduled.length > 0" class="unscheduled">
        <h2 class="section">Noch nicht terminiert</h2>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="badge missing">Erfahrungswert</span>
          </li>
        </ul>
      </div>

      <PlanActions
        :entries="timeline"
        :anchor-date="anchorDate"
        :calendar-name="calendarName"
        :file-slug="fileSlug"
        :kept="kept"
        @toggle-kept="toggleKept"
      />
    </template>
    <p v-else class="hint">
      {{ anchorLabel }} eingeben, um den Zeitplan zu sehen.
    </p>

    <!-- Into the middle of the bottom bar, so the page's own actions sit where
    the thumb already is. -->
    <Teleport v-if="SHOW_FAB && anchorDate" to="#fab-slot" :disabled="!hasSlot">
      <div class="fab" :class="{ open: fabOpen }">
      <div v-if="fabOpen" class="fab-menu">
        <button type="button" @click="fabDo(addTask)">
          <ListPlus :size="16" /> Aufgabe hinzufügen
        </button>
        <button type="button" @click="fabDo(openDatePicker)">
          <CalendarDays :size="16" /> {{ anchorLabel }} ändern
        </button>
        <button type="button" @click="fabDo(exportIcs)">
          <CalendarPlus :size="16" /> In den Kalender
        </button>
        <button type="button" @click="fabDo(toggleKept)">
          <component :is="kept ? BookmarkCheck : Bookmark" :size="16" />
          {{ kept ? "Nicht mehr merken" : "Plan merken" }}
        </button>
      </div>
        <button
          type="button"
          class="fab-toggle"
          :aria-expanded="fabOpen"
          aria-label="Aktionen"
          @click="fabOpen = !fabOpen"
        >
          <component :is="fabOpen ? X : Plus" :size="22" />
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.deadline-planner {
  max-width: 62rem;
  padding-bottom: 5rem;
  --tint-accent: color-mix(in srgb, var(--accent) 10%, transparent);
}
.sentinel {
  height: 1.5rem;
}

.title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem 1.5rem;
}
/* Keeping a plan is a real action, so it looks like one instead of hiding as
grey text under a chart. */
.save {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  flex-shrink: 0;
  padding: 0.4rem 0.9rem;
  border: 1px solid var(--accent);
  color: var(--accent);
  font-size: var(--t-meta);
  font-weight: var(--fw-semibold);
  background: var(--paper-raised);
}
.save:hover {
  background: color-mix(in srgb, var(--accent) 10%, var(--paper-raised));
}
.save[aria-pressed="true"] {
  border-color: var(--done);
  color: var(--done);
}
.implode-leave-active {
  transition:
    transform 0.3s cubic-bezier(0.4, 0, 1, 1),
    opacity 0.3s ease-in;
}
.implode-leave-to {
  transform: scale(0.2) rotate(-8deg);
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .implode-leave-active {
    transition: none;
  }
}

.overview {
  max-width: 62ch;
  margin: 0 0 1rem;
  color: var(--muted);
}
/* A phone opens this page for the plan, not for the reasoning behind it. */
@media (max-width: 40rem) {
  .overview {
    display: none;
  }
}

.overview b {
  color: var(--ink);
  font-weight: var(--fw-semibold);
}

.planner-header {
  position: sticky;
  top: min(0px, calc(100vh - var(--tl-header-h, 0px) - 2rem));
  z-index: 40;
  margin-inline: calc(-1 * var(--wrap-pad, 0px));
  padding: 0.6rem var(--wrap-pad, 0px);
  transition:
    padding 0.18s,
    box-shadow 0.18s;
}
.planner-header :deep(.timeline) {
  --d-werktag: var(--paper-raised);
}
/* Whoever owns the surface decides: with no surface of its own the header lets
the two stats be cards, once it has one they flatten into it. */
.compact .planner-header {
  background: var(--paper-raised);
  box-shadow: var(--shadow-card);
}
.compact .planner-header :deep(.stat) {
  background: var(--paper);
  box-shadow: none;
}
.compact .planner-header {
  padding: 0.45rem var(--wrap-pad, 0px);
}

.title {
  /* The Ort popover anchors here, so it opens at the left of the heading and
  stays inside the content column. */
  position: relative;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 0.3em;
  margin: 0 0 1rem;
  font-size: var(--t-section);
  line-height: 1.35;
}
.slot {
  position: relative;
  display: inline-block;
  overflow: hidden;
  color: var(--accent);
  border-bottom: 2px dashed var(--line);
  cursor: pointer;
}
.slot:hover {
  border-bottom-color: var(--accent);
}
.slot:focus-within {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
/* The input covers the slot but takes no clicks: the slot opens the picker. */
.slot input {
  position: absolute;
  inset: 0;
  width: 100%;
  min-width: 0;
  height: 100%;
  padding: 0;
  border: 0;
  opacity: 0;
  font: inherit;
  cursor: pointer;
  pointer-events: none;
}

.tl-toggle {
  display: flex;
  white-space: nowrap;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  width: 100%;
  min-height: 1.8rem;
  margin-top: 0.15rem;
  padding: 0.1rem 0.5rem;
  border-color: transparent;
  background: transparent;
  color: var(--muted);
  font-size: var(--t-meta);
}
.tl-toggle:hover {
  color: var(--accent);
}
.keep[aria-pressed="true"] {
  color: var(--done);
}
.tl-off {
  display: none;
}
/* A phone gets the plan, not a chart of it. */
@media (max-width: 40rem) {
  .planner-header :deep(.timeline),
  .tl-toggle {
    display: none;
  }
}

.facets {
  border: 0;
  padding: 0;
  margin: 1rem 0 0;
  min-width: 0;
}
/* One line that scrolls, not four that wrap: it sits above the plan and must
not push it off the screen. */
.facet-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.facets legend {
  font-size: var(--t-meta);
  font-weight: var(--fw-semibold);
  color: var(--muted);
  padding: 0 0 0.5rem;
}
.facet {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 0.3rem 0.8rem;
  background: var(--paper-raised);
  font-size: var(--t-meta);
  cursor: pointer;
}
.facet:has(input:checked) {
  border-color: var(--accent);
  color: var(--accent);
}
.facet:has(input:focus-visible) {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.facet input {
  accent-color: var(--accent);
  margin: 0;
}

.task-search-toggle {
  margin-left: 0.4rem;
  padding: 0.15rem 0.3rem;
  vertical-align: middle;
  color: var(--muted);
}
.task-search {
  width: 100%;
  max-width: 22rem;
  margin-bottom: 0.75rem;
}
.section {
  scroll-margin-top: calc(var(--tl-header-h, 0px) + 1rem);
  font-size: var(--t-meta);
  color: var(--muted);
  font-weight: var(--fw-semibold);
  border: 0;
  padding: 0;
  margin: 1.75rem 0 0.75rem;
}

.add-end-wrap {
  position: relative;
}
.add-end {
  display: block;
  width: 100%;
  margin-top: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px dashed var(--line);
  background: transparent;
  color: var(--muted);
  text-align: left;
  cursor: pointer;
}
.add-end:hover {
  border-style: solid;
  border-color: var(--accent);
  color: var(--accent);
}
.add-end-wrap :deep(.task-picker) {
  left: 0;
  top: calc(100% + 0.4rem);
}

.hidden-group {
  margin-top: 1rem;
  font-size: var(--t-meta);
}
.hidden-group summary {
  cursor: pointer;
  padding: 0.5rem 0;
  color: var(--muted);
}
.hidden-group ul {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}
.hidden-group li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.6rem;
  min-height: 2.4rem;
  color: var(--muted);
}
.hidden-group button {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  flex-shrink: 0;
  padding: 0.2rem 0.5rem;
  font-size: var(--t-meta);
}

.undo {
  margin-top: 1rem;
  font-size: var(--t-meta);
  color: var(--muted);
}
.undo button {
  background: none;
  border: 0;
  color: var(--accent);
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
  font-size: inherit;
}

.unscheduled ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.unscheduled li {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
}
.unscheduled .badge.missing {
  border-color: var(--line);
  color: var(--muted);
}

@media (min-width: 40rem) {
  .deadline-planner {
    padding-bottom: 0;
  }
  /* Wide enough for the timeline, so the header is a card that holds it. */
  .planner-header {
    margin-inline: 0;
    border-radius: var(--r-lg);
    padding: 0.9rem 1rem;
    background: var(--paper-raised);
    box-shadow: var(--shadow-card);
  }
  .planner-header :deep(.stat) {
    background: var(--paper);
    box-shadow: none;
  }
  .compact .planner-header {
    padding: 0.6rem 1rem;
  }
  /* A wide screen has room for the timeline, so it never collapses. The
  actions next to it stay. */
  .tl-toggle {
    display: none;
  }
  .tl-off {
    display: block;
  }
}

@media print {
  /* Everything that only exists to be clicked. */
  .planner-header :deep(.timeline),
  .planner-header :deep(.bar),
  .tl-toggle,
  .facets,
  .add-end-wrap,
  .hidden-group,
  .undo,
  .sentinel {
    display: none;
  }
  .planner-header {
    position: static;
    margin-bottom: 0 !important;
    padding: 0;
    background: none;
  }
  .overview {
    color: #000;
  }
  .section {
    margin-top: 1rem;
  }
  /* The dashed underline says "you can change this", which paper cannot. */
  .slot {
    border-bottom: 0;
    color: inherit;
  }
}

.fab {
  position: relative;
  display: flex;
  justify-content: center;
}
/* The menu opens upward, out of the bar. */
.fab-menu {
  position: absolute;
  bottom: calc(100% + 0.6rem);
  right: 50%;
  transform: translateX(50%);
}
.fab-toggle {
  margin-top: -1.2rem;
}
.fab-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3.4rem;
  height: 3.4rem;
  border: 0;
  border-radius: 50%;
  background: var(--accent);
  color: var(--accent-ink);
  box-shadow: var(--shadow-lg);
}
.fab-menu {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.3rem;
  padding: 0.4rem;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--paper-raised);
  box-shadow: var(--shadow-lg);
}
.fab-menu button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 2.4rem;
  padding: 0.4rem 0.7rem;
  border: 0;
  background: none;
  font-size: var(--t-meta);
  white-space: nowrap;
}
.fab-menu button:hover {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  border-radius: var(--r-sm);
}
/* A wide screen keeps the header in view, so it needs no floating copy. */
@media (min-width: 40rem) {
  .fab {
    display: none;
  }
}
@media print {
  .fab {
    display: none;
  }
}

:global(.wom-confetti) {
  position: fixed;
  width: 6px;
  height: 6px;
  pointer-events: none;
  z-index: 80;
}
</style>
