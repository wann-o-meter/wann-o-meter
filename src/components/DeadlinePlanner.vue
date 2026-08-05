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
import { Plus } from "lucide-vue-next";
import MonthGrid from "./calendar/MonthGrid.vue";
import TaskCard from "./deadline-planner/TaskCard.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import { MONTH_NAMES } from "../../lib/date-display";
import type { DayLayer } from "../../lib/date-grid";
import { toDate } from "../../lib/format-date";
import { holidaysFor } from "../../lib/holidays";
import { generateIcs } from "../../lib/ics";
import type { IcsEvent } from "../../lib/ics";
import { taskCtaFor } from "./deadline-planner/task-cta";
import { useTaskEditor } from "./deadline-planner/useTaskEditor";
import {
  ANCHOR_ID,
  COUNTRY_CODE,
  usePlannerSchedule,
} from "./deadline-planner/usePlannerSchedule";
import type { PlanVariant } from "./deadline-planner/types";

export type { PlanVariant };

const props = defineProps<{
  vorhaben: string; // "Vorhaben" field's option text, e.g. "Umzug innerhalb Deutschlands"
  anchorLabel: string; // e.g. "Umzugstag" - date field label, aria-label, anchor deadline label
  variantLabel: string; // e.g. "Ort" - the variant field's label text
  variants: PlanVariant[];
  defaultSlug?: string;
}>();

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

const rootEl = useTemplateRef<HTMLElement>("rootEl");
const railEl = useTemplateRef<HTMLElement>("railEl");

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

// Picks a default anchor date so the earliest known deadline is due today, instead of an empty plan. Only computed once at setup.
function defaultAnchorDate(deadlines: PlanVariant["deadlines"]): string {
  const offsets = deadlines
    .map((d) => d.offset_days)
    .filter((o): o is number => o !== null);
  if (offsets.length === 0) return isoToday();
  const minOffset = Math.min(...offsets);
  const d = new Date(`${isoToday()}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - minOffset);
  return d.toISOString().slice(0, 10);
}

const urlParams =
  typeof window === "undefined"
    ? null
    : new URLSearchParams(window.location.search);
const urlVariant = urlParams?.get("variant");

const selectedSlug = ref(
  urlVariant && props.variants.some((v) => v.slug === urlVariant)
    ? urlVariant
    : props.defaultSlug &&
        props.variants.some((v) => v.slug === props.defaultSlug)
      ? props.defaultSlug
      : props.variants[0]?.slug,
);
const selected = computed(
  () =>
    props.variants.find((v) => v.slug === selectedSlug.value) ??
    props.variants[0],
);

const urlDate = urlParams?.get("date");
const anchorDate = ref(
  urlDate && ISO_DAY.test(urlDate)
    ? urlDate
    : defaultAnchorDate(
        props.variants.find((v) => v.slug === selectedSlug.value)?.deadlines ??
          [],
      ),
);

// Keeps the plan shareable as a link - replaceState, not pushState, so picking a date doesn't spam browser history.
watch(
  [anchorDate, selectedSlug],
  () => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (anchorDate.value) params.set("date", anchorDate.value);
    if (selected.value) params.set("variant", selected.value.slug);
    const query = params.toString();
    history.replaceState(
      null,
      "",
      query ? `?${query}` : window.location.pathname,
    );
  },
  { immediate: true },
);

const {
  doneIds,
  userNotes,
  editingId,
  openNoteId,
  attachments,
  openAttachmentId,
  lastDeleted,
  draggingId,
  dragOverGapId,
  workingDeadlines,
  isCustom,
  toggleDone,
  commitLabel,
  openNote,
  commitNote,
  openAttachment,
  commitAttachment,
  deleteEntry,
  undoDelete,
  insertCustomTask,
  addTaskAtEnd,
  onDragStart,
  onDragEnd,
  onGapDrop,
} = useTaskEditor(selected, rootEl);

const { timeline, unscheduled, railNodes, stats } = usePlannerSchedule(
  anchorDate,
  selected,
  workingDeadlines,
  () => props.anchorLabel,
  doneIds,
);

function isPast(date: string): boolean {
  return date < isoToday();
}

// Scroll-linked highlight: tracks the page's own scroll (the rail has no inner scrollbox), picks the item closest to a fixed viewport line.
const HIGHLIGHT_LINE_PX = 140; // roughly "just under the sitewide header"
const highlightedDate = ref<string | null>(null);
let scrollRaf = false;
function updateHighlight() {
  const container = railEl.value;
  if (!container) return;
  const items = container.querySelectorAll<HTMLElement>("[data-entry-date]");
  let closestDate: string | null = null;
  let closestDelta = Number.POSITIVE_INFINITY;
  let lastDate: string | null = null;
  for (const el of items) {
    const date = el.dataset.entryDate;
    if (!date) continue;
    lastDate = date;
    const delta = Math.abs(el.getBoundingClientRect().top - HIGHLIGHT_LINE_PX);
    if (delta < closestDelta) {
      closestDelta = delta;
      closestDate = date;
    }
  }
  highlightedDate.value = closestDate ?? lastDate;
}
function onPageScroll() {
  if (scrollRaf) return;
  scrollRaf = true;
  requestAnimationFrame(() => {
    scrollRaf = false;
    updateHighlight();
  });
}
onMounted(() => {
  window.addEventListener("scroll", onPageScroll, { passive: true });
  nextTick(updateHighlight);
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", onPageScroll);
});
watch(railNodes, () => nextTick(updateHighlight));

// MonthGrid's week-open button would be a dead click otherwise - scrolls the rail to that week's first item instead.
function onWeekClick(mondayIso: string) {
  const sundayIso = (() => {
    const d = toDate(mondayIso);
    d.setUTCDate(d.getUTCDate() + 6);
    return d.toISOString().slice(0, 10);
  })();
  const target = timeline.value.find(
    (e) => e.date !== null && e.date >= mondayIso && e.date <= sundayIso,
  );
  if (!target) return;
  railEl.value
    ?.querySelector(`[data-entry-id="${target.id}"]`)
    ?.scrollIntoView({ block: "center", behavior: "smooth" });
}

// Calendar sidebar reuses MonthGrid.vue as-is (generic DayLayer[] prop, no sitewide coupling) - deadlines and holidays are two separate layers.
const calendarYear = computed(() =>
  Number((anchorDate.value || isoToday()).slice(0, 4)),
);
// Which month the sidebar shows - the highlighted day if any, else the anchor day. calendarLayers' holiday fetch stays on the wider calendarYear.
const calendarMonth = computed(() => {
  const iso = highlightedDate.value || anchorDate.value || isoToday();
  return {
    year: Number(iso.slice(0, 4)),
    monthIndex0: Number(iso.slice(5, 7)) - 1,
  };
});
const calendarLayers = computed<DayLayer[]>(() => {
  if (!anchorDate.value) return [];
  const deadlineWindows = timeline.value
    .filter((e) => e.date !== null)
    .map((e) => ({ start: e.date!, end: e.date!, description: e.label }));
  const years = [
    calendarYear.value - 1,
    calendarYear.value,
    calendarYear.value + 1,
  ];
  const holidayWindows = years
    .flatMap((y) => holidaysFor(y, COUNTRY_CODE, selected.value?.regionCode))
    .map((h) => ({ start: h.date, end: h.date, description: h.name }));
  return [
    {
      color: "var(--accent)",
      label: props.vorhaben,
      url: "#",
      visible: true,
      windows: deadlineWindows,
    },
    {
      color: "var(--warn)",
      label: "Feiertage",
      url: "#",
      visible: true,
      windows: holidayWindows,
    },
  ];
});

// Popover at both "+" triggers - which gap (or the end-of-list button) is currently open.
type TaskPickerTarget =
  | { kind: "gap"; id: string; afterOffset: number; beforeOffset: number }
  | { kind: "end" };

const taskPickerTarget = ref<TaskPickerTarget | null>(null);

function isTaskPickerOpen(target: TaskPickerTarget): boolean {
  const t = taskPickerTarget.value;
  if (!t || t.kind !== target.kind) return false;
  return t.kind === "gap" && target.kind === "gap" ? t.id === target.id : true;
}

function toggleTaskPicker(target: TaskPickerTarget) {
  taskPickerTarget.value = isTaskPickerOpen(target) ? null : target;
}

function closeTaskPicker() {
  taskPickerTarget.value = null;
}

function knownEndOffsets(): number[] {
  return timeline.value
    .filter((e) => e.offset_days !== null)
    .map((e) => e.offset_days!);
}

function pickPresetTask(label: string) {
  const target = taskPickerTarget.value;
  if (!target) return;
  if (target.kind === "gap")
    insertCustomTask(target.afterOffset, target.beforeOffset, label);
  else addTaskAtEnd(knownEndOffsets(), label);
  closeTaskPicker();
}

function pickBlankTask() {
  const target = taskPickerTarget.value;
  if (!target) return;
  if (target.kind === "gap")
    insertCustomTask(target.afterOffset, target.beforeOffset);
  else addTaskAtEnd(knownEndOffsets());
  closeTaskPicker();
}

// No backdrop, so these close it on outside click/Escape. Escape is document-level, not @keydown.esc on the popover: focus sits on the trigger button, a sibling, not an ancestor, so the popover would never see the bubbled key.
function onDocumentClickForTaskPicker(event: MouseEvent) {
  if (!taskPickerTarget.value) return;
  const el = event.target as HTMLElement | null;
  if (el?.closest(".task-picker, .gap-add, .add-end")) return;
  closeTaskPicker();
}
function onDocumentKeydownForTaskPicker(event: KeyboardEvent) {
  if (event.key === "Escape" && taskPickerTarget.value) closeTaskPicker();
}
onMounted(() => {
  document.addEventListener("click", onDocumentClickForTaskPicker);
  document.addEventListener("keydown", onDocumentKeydownForTaskPicker);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onDocumentClickForTaskPicker);
  document.removeEventListener("keydown", onDocumentKeydownForTaskPicker);
});

function exportIcs() {
  if (!anchorDate.value || !selected.value) return;
  const events: IcsEvent[] = timeline.value
    .filter((e) => e.date !== null)
    .map((e) => ({
      uid: `${e.id}-${anchorDate.value}@wannometer.de`,
      from: e.date!,
      to: e.date!,
      title: e.label,
      description: e.note,
      url: e.source_url ?? undefined,
    }));
  const ics = generateIcs(
    events,
    `${props.vorhaben} - ${selected.value.label}`,
  );
  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${selected.value.slug}-${anchorDate.value}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

// `window` is not in template scope.
function print() {
  window.print();
}
</script>

<template>
  <div ref="rootEl" class="deadline-planner">
    <div class="form">
      <label class="field">
        <span>Vorhaben</span>
        <select disabled>
          <option>{{ vorhaben }}</option>
        </select>
      </label>
      <label class="field">
        <span>{{ anchorLabel }}</span>
        <input v-model="anchorDate" type="date" :aria-label="anchorLabel" />
      </label>
      <label v-if="variants.length > 1" class="field">
        <span>{{ variantLabel }}</span>
        <select v-model="selectedSlug">
          <option v-for="v in variants" :key="v.slug" :value="v.slug">
            {{ v.label }}
          </option>
        </select>
      </label>
    </div>

    <div v-if="anchorDate" class="summary">
      <div class="stat">
        <span class="k">Offen</span><span class="v">{{ stats.open }}</span>
      </div>
      <div class="stat">
        <span class="k">Erledigt</span><span class="v">{{ stats.done }}</span>
      </div>
      <div class="stat">
        <span class="k">Erste Frist</span
        ><span class="v">{{ stats.first }}</span>
      </div>
      <div v-if="stats.warnings > 0" class="stat">
        <span class="k">Warnungen</span
        ><span class="v">{{ stats.warnings }}</span>
      </div>
    </div>

    <template v-if="anchorDate">
      <p class="scalenote" title="Ziehen verschiebt eine Aufgabe, Scrollen hebt den Tag im Kalender hervor">
        Abstände sind maßstäblich.
      </p>
      <div class="planner-body">
        <div class="rail-column">
          <div ref="railEl" class="rail">
            <template
              v-for="node in railNodes"
              :key="node.kind === 'gap' ? node.id : node.entry.id"
            >
              <div
                v-if="node.kind === 'gap'"
                class="gap"
                :class="{
                  'drag-target': draggingId,
                  active: dragOverGapId === node.id,
                }"
                :style="{ height: `${node.heightPx}px` }"
                @dragover.prevent
                @dragenter="dragOverGapId = node.id"
                @dragleave="dragOverGapId === node.id && (dragOverGapId = null)"
                @drop.prevent="
                  onGapDrop($event, node.afterOffset, node.beforeOffset)
                "
              >
                <button
                  type="button"
                  class="gap-add"
                  title="Aufgabe hier einfügen"
                  aria-label="Aufgabe hier einfügen"
                  @click="
                    toggleTaskPicker({
                      kind: 'gap',
                      id: node.id,
                      afterOffset: node.afterOffset,
                      beforeOffset: node.beforeOffset,
                    })
                  "
                >
                  <Plus :size="12" />
                </button>
                <TaskPicker
                  v-if="
                    isTaskPickerOpen({
                      kind: 'gap',
                      id: node.id,
                      afterOffset: node.afterOffset,
                      beforeOffset: node.beforeOffset,
                    })
                  "
                  @pick-preset="pickPresetTask"
                  @pick-blank="pickBlankTask"
                />
              </div>
              <TaskCard
                v-else
                :entry="node.entry"
                :anchor-label="anchorLabel"
                :is-anchor="node.entry.id === ANCHOR_ID"
                :is-past="isPast(node.entry.date!)"
                :done="!!doneIds[node.entry.id]"
                :is-custom="isCustom(node.entry.id)"
                :dragging="draggingId === node.entry.id"
                :editing="editingId === node.entry.id"
                :note-open="openNoteId === node.entry.id"
                :note-text="userNotes[node.entry.id]"
                :attachment-open="openAttachmentId === node.entry.id"
                :attachment-text="attachments[node.entry.id]"
                :has-attachment="node.entry.id in attachments"
                :cta="taskCtaFor(node.entry.id)"
                @toggle-done="toggleDone(node.entry.id)"
                @commit-label="commitLabel(node.entry.id, $event)"
                @open-note="openNote(node.entry.id)"
                @commit-note="commitNote(node.entry.id, $event)"
                @open-attachment="openAttachment(node.entry.id)"
                @commit-attachment="commitAttachment(node.entry.id, $event)"
                @delete="deleteEntry(node.entry)"
                @dragstart="onDragStart($event, node.entry.id)"
                @dragend="onDragEnd"
              />
            </template>
          </div>

          <div class="add-end-wrap">
            <button
              type="button"
              class="add-end"
              @click="toggleTaskPicker({ kind: 'end' })"
            >
              + Eigene Aufgabe hinzufügen
            </button>
            <TaskPicker
              v-if="isTaskPickerOpen({ kind: 'end' })"
              @pick-preset="pickPresetTask"
              @pick-blank="pickBlankTask"
            />
          </div>
          <p v-if="lastDeleted" class="undo">
            „{{ lastDeleted.label }}" entfernt.
            <button type="button" @click="undoDelete">Rückgängig</button>
          </p>
        </div>

        <div class="calendar-panel">
          <div class="calendar-head">
            <h2>
              Kalender · {{ MONTH_NAMES[calendarMonth.monthIndex0] }}
              {{ calendarMonth.year }}
            </h2>
            <ul class="legend">
              <li><span class="swatch accent"></span>{{ vorhaben }}</li>
              <li><span class="swatch warn"></span>Feiertage</li>
            </ul>
          </div>
          <MonthGrid
            :year="calendarMonth.year"
            :month-index0="calendarMonth.monthIndex0"
            :layers="calendarLayers"
            :today-iso="isoToday()"
            :highlight-iso="highlightedDate"
            variant="full"
            @week-click="onWeekClick"
          />
        </div>
      </div>

      <div v-if="unscheduled.length > 0" class="unscheduled">
        <h2>Noch nicht terminiert</h2>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="badge missing">Quelle fehlt</span>
          </li>
        </ul>
      </div>

      <div class="actions">
        <div class="actions-buttons">
          <button type="button" @click="exportIcs">Als ICS exportieren</button>
          <button type="button" @click="print">Checkliste drucken</button>
        </div>
        <p title="Änderungen gelten nur in diesem Tab und werden beim Neuladen zurückgesetzt">
          Nur in diesem Tab gespeichert.
        </p>
      </div>
    </template>
    <p v-else class="hint">
      {{ anchorLabel }} eingeben, um den Zeitplan zu sehen.
    </p>
  </div>
</template>

<style scoped>
.deadline-planner {
  max-width: 75rem;
  /* --paper/--paper-raised are lightened and pulled apart locally so a card
    reads as raised, not just outlined - the shadow tokens below are this
    component's own deliberate departure from the sitewide flat/no-shadow
    look (see global.css), kept local rather than global for that reason. */
  --done-color: #3f7d4a;
  --paper: #fbfcfe;
  --paper-raised: #ffffff;
  --shadow-sm: 0 1px 3px color-mix(in srgb, var(--ink) 8%, transparent);
  --shadow-md: 0 2px 6px color-mix(in srgb, var(--ink) 8%, transparent);
  --shadow-lg: 0 4px 14px color-mix(in srgb, var(--ink) 16%, transparent);
  --tint-accent: color-mix(in srgb, var(--accent) 10%, transparent);
}
/* :global() has to wrap the WHOLE selector, not just the :root part - Vue's
  scoped-CSS compiler otherwise silently drops everything outside it, so this
  rule never matched .deadline-planner at all and dark mode never reached the
  component's own colors (the actual "light mode is broken" bug). */
:global(:root[data-theme="dark"] .deadline-planner) {
  --done-color: #7cc98a;
  --paper: #191c22;
  --paper-raised: #232733;
}
.form {
  display: grid;
  grid-template-columns: 1.3fr 1fr 1fr;
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.field {
  display: block;
  background: var(--paper-raised);
  padding: 0.9rem 1.1rem;
  box-shadow: var(--shadow-sm);
}
.field span {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.35rem;
}
.field input,
.field select {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  font-size: 1.05rem;
  font-weight: 500;
}
.field select:disabled {
  opacity: 1;
  color: inherit;
  cursor: default;
}
.field input:focus-visible,
.field select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
@media (max-width: 40rem) {
  .form {
    grid-template-columns: 1fr 1fr;
  }
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 2rem;
  margin: 1.5rem 0 0.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.stat .k {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.stat .v {
  font-weight: 700;
  font-size: 1.5rem;
}

.scalenote {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--muted);
  margin: 1.25rem 0 0.9rem 12.5rem;
}
/* Side by side, not stacked: the rail flows at its own full height (no inner
  scrollbox), the calendar sidebar top-sticks - unlike bottom-sticky, this
  stays pinned the whole time its column is taller than the sidebar. */
.planner-body {
  display: grid;
  grid-template-columns: 1fr 19rem;
  gap: 2.5rem;
  align-items: start;
}
.rail-column {
  min-width: 0;
}
.calendar-panel {
  position: sticky;
  top: 1.25rem;
  min-width: 0;
  max-height: calc(100vh - 2.5rem);
  overflow-y: auto;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 1rem;
  box-shadow: var(--shadow-md);
  /* MonthGrid's cells paint with --paper - re-separated from --paper-raised
    here, else cells blend into this near-white panel and erase the grid. */
  --paper: color-mix(in srgb, var(--paper-raised) 92%, var(--ink));
}
@media (max-width: 58rem) {
  .planner-body {
    grid-template-columns: 1fr;
  }
  .calendar-panel {
    position: static;
    max-height: none;
    overflow: visible;
  }
}
.rail {
  position: relative;
  margin: 0;
  padding: 0.5rem 0 0.5rem 12.5rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 11rem;
  top: 0.4rem;
  bottom: 0.4rem;
  width: 1px;
  background: var(--line);
}
/* .gap cancels the rail's indent (negative margin) and reapplies it as its
  own padding, so its hoverable box spans the full rail width including the
  line's gutter - hovering the line itself would otherwise do nothing.
  Padding doesn't move an absolute child's containing block (always the
  border-box edge), so .gap-add's `left` below is a positive rail-relative
  offset, unlike the negative item-relative one TaskCard's .dot/.when use. */
.gap {
  position: relative;
  margin-left: -12.5rem;
  padding-left: 12.5rem;
}
.gap-add {
  position: absolute;
  /* Centered on .rail::before's line: 11rem minus half the 1.3rem width. */
  left: 10.35rem;
  top: 50%;
  transform: translateY(-50%);
  width: 1.3rem;
  height: 1.3rem;
  border-radius: 50%;
  border: 1px dashed var(--muted);
  background: var(--paper);
  color: var(--muted);
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.1s;
}
.gap:hover .gap-add,
.gap-add:focus-visible {
  opacity: 1;
}
.gap-add:hover {
  border-style: solid;
  border-color: var(--accent);
  color: var(--accent);
}
/* Native drag events don't reliably trigger :hover, so drop-target state is
  JS-driven (dragOverGapId): .drag-target marks every valid gap, .active is
  the one currently under the pointer. */
.gap.drag-target {
  background: color-mix(in srgb, var(--accent) 5%, transparent);
}
.gap.drag-target .gap-add {
  opacity: 0.6;
}
.gap.active {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.gap.active .gap-add {
  opacity: 1;
  border-style: solid;
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}
.add-end {
  display: block;
  width: 100%;
  margin-top: 1rem;
  padding: 0.7rem 1rem;
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
.add-end-wrap {
  position: relative;
}
/* Positioned against whichever ancestor is already relative (.gap or
  .add-end-wrap) - TaskPicker's root element inherits this scope's CSS too
  (Vue scoped styles reach a child's root node), no new wrapper needed. */
.gap :deep(.task-picker) {
  left: 10.35rem;
  top: calc(50% + 1rem);
}
.add-end-wrap :deep(.task-picker) {
  left: 0;
  top: calc(100% + 0.4rem);
}
/* Shorter than MonthGrid's default (4rem, sized for /kalender/) - this
  sidebar is only ~19rem wide, no room for anything but mark dots anyway. */
.calendar-panel :deep(.day-cell) {
  min-height: 2.5rem;
}
.calendar-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem 1.5rem;
  margin-bottom: 0.75rem;
}
.calendar-head h2 {
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 1rem;
}
.legend {
  display: flex;
  gap: 1rem;
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 0.8rem;
  color: var(--muted);
}
.legend li {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.swatch {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  display: inline-block;
}
.swatch.accent {
  background: var(--accent);
}
.swatch.warn {
  background: var(--warn);
}

.undo {
  margin-top: 0.9rem;
  font-size: 0.85rem;
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

.unscheduled {
  margin-top: 2.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
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

.actions {
  margin-top: 2.5rem;
  padding: 1rem 1.2rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
}
.actions p {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.75rem;
}
.actions-buttons {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

@media (max-width: 32rem) {
  .rail {
    padding-left: 1.4rem;
  }
  .gap {
    margin-left: -1.4rem;
    padding-left: 1.4rem;
  }
  .rail::before {
    left: 0.2rem;
  }
  .gap-add {
    left: 0.05rem;
  }
  .scalenote {
    margin-left: 0;
  }
  .gap :deep(.task-picker) {
    left: 0;
    top: calc(100% + 0.3rem);
    max-width: calc(100vw - 3rem);
  }
}

@media print {
  .form,
  .gap-add,
  .add-end,
  .undo,
  .actions,
  .calendar-panel {
    display: none;
  }
}
</style>
