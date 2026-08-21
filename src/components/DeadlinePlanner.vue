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
import { ChevronDown, ChevronUp, Eye, Search } from "lucide-vue-next";
import Timeline from "./deadline-planner/Timeline.vue";
import TaskCard from "./deadline-planner/TaskCard.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import OrtPicker from "./deadline-planner/OrtPicker.vue";
import PlanSummary from "./deadline-planner/PlanSummary.vue";
import PlanActions from "./deadline-planner/PlanActions.vue";
import { taskCtaFor } from "./deadline-planner/task-cta";
import { isPast } from "../../lib/today";
import { facetLabel } from "../../lib/facets";
import { daysUntil } from "../../lib/date-display";
import { formatDate } from "../../lib/format-date";
import { offsetLabel } from "../../lib/offset-label";
import {
  forgetPlan,
  loadSavedPlans,
  planStorageKey,
  savePlan,
} from "../../lib/saved-plans";
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
  anchorPersonal?: string;
  variantLabel: string;
  variantPreposition?: string;
  variants: PlanVariant[];
  defaultSlug?: string;
}>();

const rootEl = useTemplateRef<HTMLElement>("rootEl");
const listEl = useTemplateRef<HTMLElement>("listEl");
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
  fresh,
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
  places,
  lastHidden,
  hiddenTasks,
  workingDeadlines,
  isCustom,
  toggleDone,
  commitLabel,
  commitNote,
  commitPlace,
  commitAttachment,
  ensureAttachment,
  hideEntry,
  removeTask,
  unhide,
  addTaskAtEnd,
} = useTaskEditor(
  selectedForPlan,
  computed(() => planStorageKey(props.vorhaben, selectedSlug.value)),
);

const { timeline, tasks, unscheduled } = usePlannerSchedule(
  anchorDate,
  selected,
  workingDeadlines,
  () => props.anchorLabel,
  doneIds,
  overlapMonths,
);

const { stuck, headerGap } = useStickyHeader(rootEl, headerEl, sentinelEl);

// fresh says the wizard just sent us, playing says the entrance is running.
const playing = ref(false);

const editor = ref<{ id: string; kind: EditorKind } | null>(null);

const picker = useTaskPicker({
  // A day the visitor names is kept as its distance from the anchor, so the
  // task moves with the plan like every other one.
  addAtEnd: (label, date) =>
    addTaskAtEnd(
      timeline.value
        .filter((e) => e.offset_days !== null)
        .map((e) => e.offset_days!),
      label,
      date && anchorDate.value
        ? daysUntil(date, anchorDate.value)
        : undefined,
    ),
});

// Kept in sync by hand with lib/vorhaben-data, importing it would pull node:fs
// into the browser bundle.
const isBundesweit = computed(() => selectedSlug.value === "bundesweit");

const ortLabel = computed(() =>
  isBundesweit.value
    ? ortName.value || "ganz Deutschland"
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
  places,
  isCustom,
  editorFor: (id) => (editor.value?.id === id ? editor.value.kind : null),
  setEditor: (id, kind) => {
    if (kind === "attachment") ensureAttachment(id);
    editor.value = kind ? { id, kind } : null;
  },
  hideEntry,
  removeTask,
  applyPatch: (entry: ScheduleEntry, patch: TaskPatch) => {
    if (patch.label !== undefined) commitLabel(entry.id, patch.label);
    if (patch.note !== undefined) commitNote(entry.id, patch.note);
    if (patch.place !== undefined) commitPlace(entry.id, patch.place);
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
const fristCount = (n: number) => `${n} ${n === 1 ? "Frist" : "Fristen"}`;

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
  const after = dated.filter((e) => (e.offset_days ?? 0) > 0).length;
  const soft = entries.length - dated.length;
  return {
    total: entries.length,
    headline:
      dated.length > 0
        ? fristCount(dated.length)
        : `${entries.length} Schritte`,
    tail:
      dated.length === 0
        ? " ohne gesetzliche Frist"
        : soft > 0
          ? ` und ${soft} weitere Schritte`
          : "",
    first: entries[0] ?? null,
    // Only worth a sentence where it splits the Fristen.
    afterAnchor: after === dated.length ? 0 : after,
    officeSteps: entries.filter((e) => e.needs_office).map((e) => e.label),
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

// A plan can run to twenty tasks, so finding one by name beats scrolling.
const searchOpen = ref(false);
const taskQuery = ref("");
const searchEl = useTemplateRef<HTMLInputElement>("searchEl");
function toggleSearch() {
  searchOpen.value = !searchOpen.value;
  if (searchOpen.value) nextTick(() => searchEl.value?.focus());
  else taskQuery.value = "";
}
// Leaving an empty field puts the button back. A field with a query stays: it
// is the only thing saying why the list is short.
function closeSearch() {
  if (!taskQuery.value.trim()) searchOpen.value = false;
}
const shownEntries = computed(() => {
  const q = taskQuery.value.trim().toLowerCase();
  if (!q) return planEntries.value;
  return planEntries.value.filter((e) => e.label.toLowerCase().includes(q));
});

const hoveredId = ref<string | null>(null);
let flashTimer: ReturnType<typeof setTimeout> | undefined;
function onTimelineSelect(id: string) {
  listEl.value
    ?.querySelector(`[data-entry-id="${id}"]`)
    ?.scrollIntoView({ block: "start", behavior: "smooth" });
  hoveredId.value = id;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    if (hoveredId.value === id) hoveredId.value = null;
  }, 1600);
}

const timelineHidden = ref(false);

const calendarName = computed(
  () => `${props.vorhaben} - ${selected.value?.label ?? ""}`,
);
const fileSlug = computed(() => selected.value?.slug ?? "plan");

const scrollActiveId = ref<string | null>(null);
const activeId = computed(() => hoveredId.value ?? scrollActiveId.value);

let spyFrame = 0;
function trackActiveCard() {
  if (spyFrame) return;
  spyFrame = requestAnimationFrame(() => {
    spyFrame = 0;
    const cards =
      listEl.value?.querySelectorAll<HTMLElement>("[data-entry-id]") ?? [];
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
  addEventListener("scroll", trackActiveCard, { passive: true });
  trackActiveCard();
  if (!fresh.value) return;
  // The entrance waits for the frame after hydration. Started any earlier it
  // runs while the island is still building itself, the browser paints none of
  // its frames, and the plan lands as a jump instead of a movement.
  const start = () => (playing.value = true);
  requestAnimationFrame(() => requestAnimationFrame(start));
  // Where the frames never come, start it anyway: a short wait is one thing, a
  // list that stays blank is another.
  setTimeout(start, 300);
  // Once it has played, the plan is a plan: a card that appears later because
  // the Ort changed has nothing to announce. It is also the safety net: where
  // no frame ever comes, a plan the visitor can read beats one that waits.
  setTimeout(() => {
    fresh.value = false;
    playing.value = false;
  }, 1500);
});

onBeforeUnmount(() => {
  removeEventListener("scroll", trackActiveCard);
  cancelAnimationFrame(spyFrame);
});
</script>

<template>
  <div
    ref="rootEl"
    class="deadline-planner"
    :class="{ compact: stuck, fresh, playing }"
  >
    <div class="title-row">
      <h1 class="title t-display">
        {{ anchorPersonal ?? anchorLabel }} am
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
    </div>

    <PlanSummary
      v-if="anchorDate"
      :entries="planEntries"
      :done-ids="doneIds"
      :anchor-date="anchorDate"
      :anchor-label="anchorLabel"
      @select="onTimelineSelect"
    />

    <div ref="sentinelEl" class="sentinel"></div>

    <header
      ref="headerEl"
      class="planner-header"
      :style="{ marginBottom: headerGap + 'px' }"
    >
      <template v-if="anchorDate">
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
          <component
            :is="timelineHidden ? ChevronDown : ChevronUp"
            :size="14"
          />
          {{ timelineHidden ? "Zeitstrahl zeigen" : "Zeitstrahl ausblenden" }}
        </button>
      </template>
    </header>

    <template v-if="anchorDate">
      <fieldset v-if="facetOptions.length > 1" class="facets">
        <legend class="t-section">Plan verfeinern</legend>
        <p class="t-meta refine-lede">
          {{ facetOptions.length }} Fragen, jede ergänzt weitere Aufgaben.
        </p>
        <div class="facet-row">
          <label v-for="id in facetOptions" :key="id" class="chip">
            <input v-model="activeFacets" type="checkbox" :value="id" />
            <span>{{ facetLabel(id) }}</span>
          </label>
        </div>
      </fieldset>

      <h2 class="section t-section">
        Aufgaben
        <span class="search-slot" :class="{ open: searchOpen }">
          <button
            type="button"
            class="task-search-toggle icon-button"
            :aria-expanded="searchOpen"
            aria-label="Aufgaben durchsuchen"
            @click="toggleSearch"
          >
            <Search :size="14" />
          </button>
          <input
            ref="searchEl"
            v-model="taskQuery"
            type="search"
            class="task-search"
            aria-label="Aufgaben durchsuchen"
            placeholder="Aufgabe suchen"
            @keydown.esc="closeSearch"
            @blur="closeSearch"
          />
        </span>
      </h2>
      <p v-if="taskQuery && shownEntries.length === 0" class="hint">
        Keine Aufgabe passt zu „{{ taskQuery }}".
      </p>
      <div ref="listEl" class="list">
        <TaskCard
          v-for="(entry, i) in shownEntries"
          :key="entry.id"
          :class="{ focused: activeId === entry.id }"
          :style="{ '--i': i }"
          :entry="entry"
          :anchor-date="anchorDate"
          :anchor-label="anchorLabel"
          :is-past="isPast(entry.date!)"
          :done="!!doneIds[entry.id]"
          :is-custom="store.isCustom(entry.id)"
          :cta="taskCtaFor(entry.id)"
          :note="store.userNotes[entry.id]"
          :attachment="store.attachments[entry.id]"
          :place="store.places[entry.id]"
          :editor="store.editorFor(entry.id)"
          @update:editor="store.setEditor(entry.id, $event)"
          @update="store.applyPatch(entry, $event)"
          @hide="store.hideEntry(entry)"
          @remove="store.removeTask(entry.id)"
          @toggle-done="onToggleDone(entry.id)"
          @mouseenter="hoveredId = entry.id"
          @mouseleave="hoveredId = null"
        />
        <div class="add-end-wrap">
          <TaskPicker
            v-if="picker.isOpen({ kind: 'end' })"
            @pick="picker.pick"
            @close="picker.close()"
          />
          <button
            v-else
            type="button"
            class="add-end t-meta"
            @click="picker.toggle({ kind: 'end' })"
          >
            + Eigene Aufgabe hinzufügen
          </button>
        </div>
      </div>

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
        <h2 class="section t-section">Noch nicht terminiert</h2>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="pill">kein Datum</span>
          </li>
        </ul>
      </div>

      <p v-if="overview.total > 0" class="overview t-body">
        Der Zeitplan für {{ vorhaben }} umfasst <b>{{ overview.headline }}</b
        >{{ overview.tail }}.
        <template v-if="overview.first">
          Es geht los mit {{ overview.first.label }} ({{
            offsetLabel(overview.first, anchorLabel)
          }}).
        </template>
        <template v-if="overview.afterAnchor > 0">
          {{ fristCount(overview.afterAnchor) }} laufen erst nach dem
          {{ anchorLabel }}.
        </template>
        <template v-if="overview.officeSteps.length > 0">
          Termine beim Amt sind je nach Stadt Wochen im Voraus vergeben ({{
            overview.officeSteps.join(", ")
          }}).
        </template>
        <template v-if="overview.localSteps.length > 0">
          In {{ selected?.label }} kommen dazu:
          {{ overview.localSteps.join(", ") }}.
        </template>
      </p>

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
.overview {
  max-width: 62ch;
  margin: var(--s-4) 0 0;
  color: var(--muted);
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
.compact .planner-header {
  background: var(--paper-raised);
  box-shadow: var(--shadow-card);
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
  margin: 0 0 var(--s-2);
}
/* One signal that a word is editable: it carries the accent, and hovering it
underlines it. A dotted rule under a word reads as a spelling mistake. */
.slot {
  position: relative;
  display: inline-block;
  overflow: hidden;
  color: var(--accent);
  cursor: pointer;
}
.slot:hover {
  text-decoration: underline;
  text-underline-offset: 0.15em;
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
  padding: 0;
}
.refine-lede {
  margin: 0.15rem 0 var(--s-1);
  color: var(--muted);
}

/* The field takes the button's place instead of opening a row under it: both
sit in the same slot and trade widths. */
.search-slot {
  display: inline-flex;
  align-items: center;
  margin-left: 0.4rem;
  vertical-align: middle;
}
.task-search-toggle,
.task-search {
  transition:
    width 0.18s ease,
    opacity 0.14s ease;
}
.task-search {
  width: 0;
  min-width: 0;
  padding-inline: 0;
  border-width: 0;
  opacity: 0;
  visibility: hidden;
  font-size: var(--t-meta);
}
.search-slot.open .task-search {
  width: min(14rem, 50vw);
  padding-inline: 0.5rem;
  border-width: 1px;
  opacity: 1;
  visibility: visible;
}
.search-slot.open .task-search-toggle {
  width: 0;
  opacity: 0;
  visibility: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .task-search-toggle,
  .task-search {
    transition: none;
  }
}
.section {
  scroll-margin-top: calc(var(--tl-header-h, 0px) + 1rem);
  border: 0;
  padding: 0;
  margin: var(--s-4) 0 var(--s-2);
}

/* The plan arrives once, on the step out of the wizard: the rows come in from
below, each a moment after the one above it, and the last few together so the
wait never grows with the plan. Hidden from the first frame, so nothing shows
itself before it comes in. */
.fresh :deep(.list > *) {
  opacity: 0;
}
.fresh.playing :deep(.list > *) {
  animation: rise 0.32s ease both;
  animation-delay: calc(min(var(--i, 0), 8) * 45ms);
}
@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(0.5rem);
  }
}
@media (prefers-reduced-motion: reduce) {
  .fresh :deep(.list > *) {
    opacity: 1;
    animation: none;
  }
}

/* One container, one divider between rows. The active row is marked inside it,
by a rail and a tint, never by becoming a different shape. */
.list {
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--paper-raised);
}
/* No clipping: a card menu opens past the bottom of a short card, and on the
last row it leaves the list altogether. The rows round their own corners. */
.list > :first-child {
  border-start-start-radius: inherit;
  border-start-end-radius: inherit;
}
.list > :last-child {
  border-end-start-radius: inherit;
  border-end-end-radius: inherit;
}

/* The last row of the list, not a button orphaned under it. */
.add-end-wrap {
  border-top: 1px solid var(--line);
}
.add-end {
  display: block;
  width: 100%;
  padding: var(--s-1) var(--s-2);
  border: 0;
  border-radius: 0;
  border-end-start-radius: inherit;
  border-end-end-radius: inherit;
  background: transparent;
  color: var(--muted);
  text-align: left;
  cursor: pointer;
}
.add-end:hover {
  color: var(--accent);
  background: var(--tint-accent);
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

:global(.wom-confetti) {
  position: fixed;
  width: 6px;
  height: 6px;
  pointer-events: none;
  z-index: 80;
}
</style>
