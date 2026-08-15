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
import { CalendarPlus, ChevronDown, ChevronUp, Eye } from "lucide-vue-next";
import Timeline from "./deadline-planner/Timeline.vue";
import TaskRail from "./deadline-planner/TaskRail.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import PlanSummary from "./deadline-planner/PlanSummary.vue";
import PlanActions from "./deadline-planner/PlanActions.vue";
import DoneGroup from "./deadline-planner/DoneGroup.vue";
import { facetLabel } from "../../lib/facets";
import { formatDate } from "../../lib/format-date";
import { offsetLabel } from "../../lib/offset-label";
import { planStorageKey, savePlan } from "../../lib/saved-plans";
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
} = usePlanUrlState(props.slug, props.variants, props.defaultSlug);

watch(
  [touched, anchorDate, selectedSlug, activeFacets],
  () => {
    if (touched.value && anchorDate.value)
      savePlan({
        slug: props.slug,
        variant: selectedSlug.value,
        // Only worth storing for a variant without a Bundesland of its own,
        // otherwise it just repeats what the Ort file already says.
        region: props.variants.find((v) => v.slug === selectedSlug.value)
          ?.regionCode
          ? undefined
          : selected.value?.regionCode,
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
  return {
    total: entries.length,
    earliest: entries[0] ?? null,
    afterAnchor: entries.filter((e) => (e.offset_days ?? 0) > 0).length,
    officeSteps: entries.filter((e) => e.needs_office).map((e) => e.label),
    undated: entries.filter((e) => e.offset_days === null).length,
    localSteps: isBundesweit.value
      ? []
      : entries
        .filter((e) => !base.has(e.id) && !isCustom(e.id))
        .map((e) => e.label.split(" ")[0]),
  };
});

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
  // The rest of the pre-hydration fallback is hidden by the js flag before the
  // first paint, only the title has to go once the planner renders its own.
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
        {{ isBundesweit ? "in" : (variantPreposition ?? "in") }}
        <span class="slot">
          <span>{{ isBundesweit ? "ganz Deutschland" : selected?.label }}</span>
          <select v-model="selectedSlug" :aria-label="variantLabel">
            <option v-for="v in variants" :key="v.slug" :value="v.slug">
              {{ v.label }}
            </option>
          </select>
        </span>
      </template>
    </h1>

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
      <template v-if="overview.undated > 0">
        {{ overview.undated }} Fristen sind noch nicht gegen ihre
        Rechtsgrundlage geprüft.
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
        <div class="header-row">
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
          <button type="button" class="tl-toggle" @click="exportIcs">
            <CalendarPlus :size="14" /> In den Kalender
          </button>
        </div>
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
.overview {
  max-width: 62ch;
  margin: 0 0 1rem;
  color: var(--muted);
}
.overview b {
  color: var(--ink);
  font-weight: 600;
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

.header-row {
  display: flex;
  gap: 0.4rem;
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

.hidden-group {
  margin-top: 1rem;
  font-size: var(--fs-sm);
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
  font-size: var(--fs-xs);
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
