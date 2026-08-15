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
import { ChevronDown, ChevronUp } from "lucide-vue-next";
import Timeline from "./deadline-planner/Timeline.vue";
import TaskRail from "./deadline-planner/TaskRail.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import PlanSummary from "./deadline-planner/PlanSummary.vue";
import PlanActions from "./deadline-planner/PlanActions.vue";
import DoneGroup from "./deadline-planner/DoneGroup.vue";
import { facetLabel } from "../../lib/facets";
import { formatDate, toDate } from "../../lib/format-date";
import { planStorageKey, savePlan } from "../../lib/saved-plans";
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
  selectedForPlan,
  anchorDate,
  activeFacets,
  facetOptions,
  overlapMonths,
  deferred,
  toggleDefer,
  touched,
} = usePlanUrlState(props.variants, props.defaultSlug);

watch(
  [touched, anchorDate, selectedSlug, activeFacets],
  () => {
    if (touched.value && anchorDate.value)
      savePlan({
        slug: props.slug,
        variant: selectedSlug.value,
        region: selected.value?.regionCode,
        date: anchorDate.value,
        facets: [...activeFacets.value],
      });
  },
  { immediate: true },
);

const {
  doneIds,
  userNotes,
  attachments,
  lastDeleted,
  workingDeadlines,
  isCustom,
  toggleDone,
  commitLabel,
  commitNote,
  commitAttachment,
  deleteEntry,
  undoDelete,
  insertCustomTask,
  addTaskAtEnd,
  moveEntry,
} = useTaskEditor(
  selectedForPlan,
  rootEl,
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

const picker = useTaskPicker({
  insertInGap: (after, before, label) => insertCustomTask(after, before, label),
  addAtEnd: (label) =>
    addTaskAtEnd(
      timeline.value
        .filter((e) => e.offset_days !== null)
        .map((e) => e.offset_days!),
      label,
    ),
});

const editor = ref<{ id: string; kind: EditorKind } | null>(null);

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

function onCommitDate(id: string, iso: string) {
  const days = Math.round(
    (toDate(iso).getTime() - toDate(anchorDate.value).getTime()) / 86400000,
  );
  moveEntry(id, days);
}

const store = computed<TaskStore>(() => ({
  doneIds,
  userNotes,
  attachments,
  isCustom,
  editorFor: (id) => (editor.value?.id === id ? editor.value.kind : null),
  setEditor: (id, kind) => (editor.value = kind ? { id, kind } : null),
  deleteEntry,
  applyPatch: (entry: ScheduleEntry, patch: TaskPatch) => {
    if (patch.label !== undefined) commitLabel(entry.id, patch.label);
    if (patch.date !== undefined) onCommitDate(entry.id, patch.date);
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
  // Both are the pre-hydration fallback, the planner renders the same Fristen
  // with their notes and sources, so showing both would only duplicate.
  document.getElementById("static-plan")?.remove();
  document.getElementById("static-title")?.remove();
  const linked = location.hash.match(/^#task-(.+)$/);
  if (linked) nextTick(() => onTimelineSelect(linked[1]));
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
    <h1 class="title">
      {{ anchorName }} am
      <span class="slot date" @click="openDatePicker">
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
        {{ variantPreposition ?? "in" }}
        <span class="slot">
          <span>{{ selected?.label }}</span>
          <select v-model="selectedSlug" :aria-label="variantLabel">
            <option v-for="v in variants" :key="v.slug" :value="v.slug">
              {{ v.label }}
            </option>
          </select>
        </span>
      </template>
    </h1>

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
          :tasks="tasks"
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
        <label v-for="id in facetOptions" :key="id" class="facet key">
          <input v-model="activeFacets" type="checkbox" :value="id" />
          <span>{{ facetLabel(id) }}</span>
        </label>
      </fieldset>

      <h2 class="section">Aufgaben</h2>
      <div ref="railEl">
        <TaskRail
          :nodes="openNodes"
          :anchor-date="anchorDate"
          :deferred="deferred"
          :hovered-id="activeId"
          :store="store"
          :picker="picker"
          @hover="hoveredId = $event"
          @toggle-done="onToggleDone"
          @toggle-defer="toggleDefer"
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

      <p v-if="lastDeleted" class="undo">
        „{{ lastDeleted.label }}" entfernt.
        <button type="button" @click="undoDelete">Rückgängig</button>
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
        :calendar-name="`${vorhaben} - ${selected?.label ?? ''}`"
        :file-slug="selected?.slug ?? 'plan'"
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
  --tint-accent: color-mix(in srgb, var(--accent) 10%, transparent);
}
.sentinel {
  height: 1.5rem;
}

.planner-header {
  position: sticky;
  top: min(0px, calc(100vh - var(--tl-header-h, 0px) - 2rem));
  z-index: 40;
  background: var(--paper-raised);
  margin-inline: calc(-1 * var(--wrap-pad, 0px));
  padding: 0.6rem var(--wrap-pad, 0px);
  transition:
    padding 0.18s,
    box-shadow 0.18s;
}
.planner-header :deep(.timeline) {
  --d-werktag: var(--paper);
}
.compact .planner-header {
  padding: 0.45rem var(--wrap-pad, 0px);
  box-shadow: var(--shadow-card);
}

.title {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0 0.3em;
  margin: 0 0 1rem;
  font-size: var(--fs-lg);
  line-height: 1.35;
  letter-spacing: -0.01em;
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
.slot input,
.slot select {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  opacity: 0;
  font: inherit;
  cursor: pointer;
}
/* Clicks belong to the slot, which opens the picker. The select needs them. */
.slot.date input {
  min-width: 0;
  pointer-events: none;
}

.tl-toggle {
  display: flex;
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
  font-size: var(--fs-sm);
}
.tl-toggle:hover {
  color: var(--accent);
}
.tl-off {
  display: none;
}

.facets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  border: 0;
  padding: 0;
  margin: 1rem 0 0;
}
.facets legend {
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  padding: 0 0 0.5rem;
}
.facet {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: 1px solid var(--line);
  padding: 0.25rem 0.5rem;
  background: var(--paper-raised);
  font-size: var(--fs-sm);
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

.section {
  scroll-margin-top: calc(var(--tl-header-h, 0px) + 1rem);
  font-size: var(--fs-sm);
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
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

.undo {
  margin-top: 1rem;
  font-size: var(--fs-sm);
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
  .planner-header {
    margin-inline: 0;
    border-radius: var(--radius);
    padding: 0.9rem 1rem;
    box-shadow: var(--shadow-card);
  }
  .compact .planner-header {
    padding: 0.6rem 1rem;
  }
  .tl-toggle {
    display: none;
  }
  .tl-off {
    display: block;
  }
}

@media print {
  .planner-header :deep(.timeline),
  .facets,
  .add-end,
  .undo {
    display: none;
  }
  .planner-header {
    position: static;
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
