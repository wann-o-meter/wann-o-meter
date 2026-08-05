<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  useTemplateRef,
  watch,
} from "vue";
import { Check, Pencil, Plus, X } from "lucide-vue-next";
import MonthGrid from "./calendar/MonthGrid.vue";
import { MONTH_NAMES, WEEKDAY_NAMES_LONG } from "../../lib/date-display";
import type { DayLayer } from "../../lib/date-grid";
import { formatDate, toDate } from "../../lib/format-date";
import { holidaysFor } from "../../lib/holidays";
import { computeSchedule } from "../../lib/deadline-plan";
import type { Deadline, ScheduleEntry } from "../../lib/deadline-plan";
import { generateIcs } from "../../lib/ics";
import type { IcsEvent } from "../../lib/ics";

// Generic so a future Geburt/Hochzeit/etc vertical can reuse this outright -
// what a specific vertical would hardcode instead comes in as props.
export interface PlanVariant {
  slug: string;
  label: string;
  regionCode?: string; // fed straight to holidaysFor(), optional
  deadlines: Deadline[];
}

const props = defineProps<{
  vorhaben: string; // "Vorhaben" field's option text, e.g. "Umzug innerhalb Deutschlands"
  anchorLabel: string; // e.g. "Umzugstag" - date field label, aria-label, anchor deadline label
  variantLabel: string; // e.g. "Ort" - the variant field's label text
  variants: PlanVariant[];
  defaultSlug?: string;
}>();

const ANCHOR_ID = "__anchor";
const CUSTOM_PREFIX = "custom-";
const COUNTRY_CODE = "DE"; // hardcoded: a German-market product end to end, no caller needs another
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

// Per-task CTAs, presentation-layer only (not a Deadline field, stays out of
// data/umzug/*.yaml). "letter" = editable generic template, never presented
// as legally reviewed. "link" = a real official self-service portal.
interface TaskCta {
  kind: "letter" | "link";
  label: string;
  url?: string; // link kind only
}
const LINK_CTAS: Record<string, TaskCta> = {
  nachsendeauftrag: {
    kind: "link",
    label: "Nachsendeauftrag bei der Post",
    url: "https://shop.deutschepost.de/nachsendeservice-beauftragen",
  },
  "kfz-ummeldung": {
    kind: "link",
    label: "i-Kfz beim Kraftfahrt-Bundesamt",
    url: "https://www.kba.de/DE/Themen/ZentraleRegister/Digitale_Fahrzeugzulassung/iKfz/ikfz_node.html",
  },
};
function taskCtaFor(id: string): TaskCta | null {
  if (id in LINK_CTAS) return LINK_CTAS[id];
  if (id.includes("kuendig"))
    return { kind: "letter", label: "Kündigungsschreiben aufsetzen" };
  return null;
}
// Generic boilerplate only, placeholders stay bracketed and vague - same
// "never fabricate a specific fact" rule the deadline data itself follows.
const LETTER_TEMPLATE = `[Ihr Name]
[Ihre Straße, Hausnummer]
[PLZ, Ort]

[Name des Anbieters]
[Straße, Hausnummer]
[PLZ, Ort]

[Ort], [Datum]

Betreff: Kündigung des Vertrags [Vertragsbezeichnung], Kundennummer [Kundennummer]

Sehr geehrte Damen und Herren,

hiermit kündige ich den oben genannten Vertrag zum nächstmöglichen Termin, hilfsweise fristgerecht zum [Kündigungsfrist gemäß Vertrag].

Bitte bestätigen Sie mir den Erhalt dieser Kündigung sowie das Vertragsende schriftlich.

Mit freundlichen Grüßen
[Ihr Name]`;

const rootEl = useTemplateRef<HTMLElement>("rootEl");

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

// Picks a default anchor date so the earliest known deadline is due today, instead of an empty plan. Only computed once at setup.
function defaultAnchorDate(deadlines: Deadline[]): string {
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

// Client-only editing layer, nothing persisted (no login/storage) - exists so the plan can be worked FROM, not just read.
interface CustomTask {
  id: string;
  label: string;
  offsetDays: number;
}
let customUid = 0;
const customTasks = ref<CustomTask[]>([]);
const doneIds = reactive<Record<string, boolean>>({});
const deletedIds = reactive<Record<string, boolean>>({});
const userNotes = reactive<Record<string, string>>({});
// Drag-and-drop rescheduling for real (read-only) deadlines - a dragged custom task mutates its own offsetDays instead, see moveEntry().
const offsetOverrides = reactive<Record<string, number>>({});
const editingId = ref<string | null>(null);
const openNoteId = ref<string | null>(null);
// Separate from userNotes on purpose - a note is free-form text, an attachment is the letter CTA's own content (link CTAs are stateless).
const attachments = reactive<Record<string, string>>({});
const openAttachmentId = ref<string | null>(null);
const lastDeleted = ref<{ id: string; label: string } | null>(null);
const railEl = useTemplateRef<HTMLElement>("railEl");
const highlightedDate = ref<string | null>(null);
const draggingId = ref<string | null>(null);
const dragOverGapId = ref<string | null>(null);

function isCustom(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

function moveEntry(id: string, newOffsetDays: number) {
  const custom = customTasks.value.find((t) => t.id === id);
  if (custom) custom.offsetDays = newOffsetDays;
  else offsetOverrides[id] = newOffsetDays;
}

const workingDeadlines = computed<Deadline[]>(() => {
  if (!selected.value) return [];
  const custom: Deadline[] = customTasks.value.map((t) => ({
    id: t.id,
    label: t.label,
    offset_days: t.offsetDays,
    source_url: null,
  }));
  return [...selected.value.deadlines, ...custom]
    .filter((d) => !deletedIds[d.id])
    .map((d) =>
      d.id in offsetOverrides
        ? { ...d, offset_days: offsetOverrides[d.id] }
        : d,
    );
});

// The anchor day is UI chrome, not a researched fact - injected here rather than stored as data, and can't be checked off/noted/deleted like a task.
const schedule = computed<ScheduleEntry[]>(() => {
  if (!anchorDate.value || !selected.value) return [];
  const withAnchor: Deadline[] = [
    {
      id: ANCHOR_ID,
      label: props.anchorLabel,
      offset_days: 0,
      source_url: null,
    },
    ...workingDeadlines.value,
  ];
  return computeSchedule(
    anchorDate.value,
    withAnchor,
    COUNTRY_CODE,
    selected.value.regionCode,
  );
});

const timeline = computed(() => schedule.value.filter((e) => e.date !== null));
const unscheduled = computed(() =>
  schedule.value.filter((e) => e.date === null),
);
const tasks = computed(() => schedule.value.filter((e) => e.id !== ANCHOR_ID));

// Interleaves gap markers between rows so the proportional spacing is a real node to hang a hover-revealed insert button on, not just margin.
type RailNode =
  | { kind: "item"; entry: ScheduleEntry }
  | {
      kind: "gap";
      id: string;
      afterOffset: number;
      beforeOffset: number;
      heightPx: number;
    };

const railNodes = computed<RailNode[]>(() => {
  const nodes: RailNode[] = [];
  timeline.value.forEach((entry, i) => {
    if (i > 0) {
      const prev = timeline.value[i - 1];
      const days = Math.round(
        (toDate(entry.date!).getTime() - toDate(prev.date!).getTime()) /
          86400000,
      );
      nodes.push({
        kind: "gap",
        id: `gap-${prev.id}-${entry.id}`,
        afterOffset: prev.offset_days!,
        beforeOffset: entry.offset_days!,
        heightPx: Math.min(96, Math.max(28, days * 2.6)),
      });
    }
    nodes.push({ kind: "item", entry });
  });
  return nodes;
});

// Scroll-linked highlight: tracks the page's own scroll (the rail has no inner scrollbox), picks the item closest to a fixed viewport line.
const HIGHLIGHT_LINE_PX = 140; // roughly "just under the sitewide header"
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

const stats = computed(() => {
  const open = tasks.value.filter((e) => !doneIds[e.id]);
  const firstOpen = timeline.value.find(
    (e) => e.id !== ANCHOR_ID && !doneIds[e.id],
  );
  const warnings = timeline.value.filter(
    (e) => e.id !== ANCHOR_ID && !doneIds[e.id] && (e.weekend || e.collision),
  ).length;
  return {
    open: open.length,
    done: tasks.value.length - open.length,
    first: firstOpen
      ? formatDate(firstOpen.date!).replace(/\.\d{4}$/, "")
      : "—",
    warnings,
  };
});

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
      color: "var(--stamp)",
      label: props.vorhaben,
      url: "#",
      visible: true,
      windows: deadlineWindows,
    },
    {
      color: "var(--accent)",
      label: "Feiertage",
      url: "#",
      visible: true,
      windows: holidayWindows,
    },
  ];
});

// Full "17. Juni 2026" / "Mittwoch" instead of the compact format - the rail has room, reads less like a table row.
function whenDate(iso: string): string {
  const d = toDate(iso);
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
function weekdayName(iso: string): string {
  return WEEKDAY_NAMES_LONG[(toDate(iso).getUTCDay() + 6) % 7];
}

function offsetLabel(offsetDays: number | null): string {
  if (offsetDays === null) return "Frist noch nicht recherchiert";
  if (offsetDays === 0) return props.anchorLabel;
  return offsetDays < 0
    ? `${Math.abs(offsetDays)} Tage vorher`
    : `${offsetDays} Tage danach`;
}

function isPast(date: string): boolean {
  return date < isoToday();
}

function toggleDone(id: string) {
  doneIds[id] = !doneIds[id];
}

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

function focusWithin(selector: string) {
  nextTick(() => {
    const el = rootEl.value?.querySelector<
      HTMLInputElement | HTMLTextAreaElement
    >(selector);
    el?.focus();
    if (el instanceof HTMLInputElement) el.select();
  });
}

function startEditingLabel(id: string) {
  editingId.value = id;
  focusWithin(`[data-title-input="${id}"]`);
}

function commitLabel(id: string, value: string) {
  if (editingId.value !== id) return;
  const task = customTasks.value.find((t) => t.id === id);
  if (task) task.label = value.trim() || "Ohne Titel";
  editingId.value = null;
}

function openNote(id: string) {
  openNoteId.value = id;
  focusWithin(`[data-note-input="${id}"]`);
}

function commitNote(id: string, value: string) {
  if (openNoteId.value !== id) return;
  const trimmed = value.trim();
  if (trimmed) userNotes[id] = trimmed;
  else delete userNotes[id];
  openNoteId.value = null;
}

// Letter CTA only (link CTA is a plain <a>, stateless). First open seeds the template, later opens reuse whatever was written.
function openAttachment(id: string) {
  if (!(id in attachments)) attachments[id] = LETTER_TEMPLATE;
  openAttachmentId.value = id;
  focusWithin(`[data-attachment-input="${id}"]`);
}

function commitAttachment(id: string, value: string) {
  if (openAttachmentId.value !== id) return;
  const trimmed = value.trim();
  if (trimmed) attachments[id] = trimmed;
  else delete attachments[id];
  openAttachmentId.value = null;
}

function deleteEntry(entry: ScheduleEntry) {
  deletedIds[entry.id] = true;
  lastDeleted.value = { id: entry.id, label: entry.label };
}

function undoDelete() {
  if (!lastDeleted.value) return;
  delete deletedIds[lastDeleted.value.id];
  lastDeleted.value = null;
}

function insertCustomTask(
  afterOffset: number,
  beforeOffset: number,
  label = "",
) {
  const id = `${CUSTOM_PREFIX}${++customUid}`;
  customTasks.value.push({
    id,
    label,
    offsetDays: Math.round((afterOffset + beforeOffset) / 2),
  });
  if (!label) startEditingLabel(id);
}

function addTaskAtEnd(label = "") {
  const known = timeline.value
    .filter((e) => e.offset_days !== null)
    .map((e) => e.offset_days!);
  const offset = (known.length > 0 ? Math.max(...known) : 0) + 3;
  const id = `${CUSTOM_PREFIX}${++customUid}`;
  customTasks.value.push({ id, label, offsetDays: offset });
  if (!label) startEditingLabel(id);
}

// Popover at both "+" triggers: presets not already in data/umzug/*.yaml, plus a free-text fallthrough to the blank-task flow above. A picked preset is a plain CustomTask, just pre-filled - no offset/date claim beyond the usual gap-midpoint placement.
const PRESET_TASKS = [
  "Bank- und Versicherungsadresse ändern",
  "Arbeitgeber über neue Adresse informieren",
  "Vereinsmitgliedschaft ummelden",
  "Zeitungs- oder Zeitschriftenabo ummelden",
  "Streaminganbieter und Online-Konten aktualisieren",
  "Kindergarten oder Schule informieren",
  "Hausarzt und Zahnarzt wechseln",
  "Tierarzt informieren oder wechseln",
];

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

function pickPresetTask(label: string) {
  const target = taskPickerTarget.value;
  if (!target) return;
  if (target.kind === "gap")
    insertCustomTask(target.afterOffset, target.beforeOffset, label);
  else addTaskAtEnd(label);
  closeTaskPicker();
}

function pickBlankTask() {
  const target = taskPickerTarget.value;
  if (!target) return;
  if (target.kind === "gap")
    insertCustomTask(target.afterOffset, target.beforeOffset);
  else addTaskAtEnd();
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

// Same midpoint math as insertCustomTask - dropping between two items IS rescheduling, since position means date here.
function onDragStart(event: DragEvent, id: string) {
  draggingId.value = id;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", id);
  }
}
function onDragEnd() {
  draggingId.value = null;
  dragOverGapId.value = null;
}
function onGapDrop(
  event: DragEvent,
  afterOffset: number,
  beforeOffset: number,
) {
  const id = draggingId.value ?? event.dataTransfer?.getData("text/plain");
  draggingId.value = null;
  dragOverGapId.value = null;
  if (!id) return;
  moveEntry(id, Math.round((afterOffset + beforeOffset) / 2));
}

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
      <div class="stat">
        <span class="k">Warnungen</span
        ><span class="v">{{ stats.warnings }}</span>
      </div>
    </div>

    <template v-if="anchorDate">
      <p class="scalenote">
        Abstände maßstäblich - enge Stellen sind arbeitsreiche Wochen. Ziehen
        verschiebt eine Aufgabe auf einen neuen Tag. Scrollen hebt den Tag im
        Kalender hervor.
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
                <div
                  v-if="
                    isTaskPickerOpen({
                      kind: 'gap',
                      id: node.id,
                      afterOffset: node.afterOffset,
                      beforeOffset: node.beforeOffset,
                    })
                  "
                  class="task-picker"
                  role="menu"
                  aria-label="Aufgabe auswählen"
                >
                  <button
                    v-for="preset in PRESET_TASKS"
                    :key="preset"
                    type="button"
                    class="task-picker-option"
                    role="menuitem"
                    @click="pickPresetTask(preset)"
                  >
                    {{ preset }}
                  </button>
                  <button
                    type="button"
                    class="task-picker-option task-picker-blank"
                    role="menuitem"
                    @click="pickBlankTask"
                  >
                    + Eigene Aufgabe
                  </button>
                </div>
              </div>
              <div
                v-else
                class="item"
                :data-entry-id="node.entry.id"
                :data-entry-date="node.entry.date"
                :draggable="node.entry.id !== ANCHOR_ID"
                :class="{
                  anchor: node.entry.id === ANCHOR_ID,
                  past: isPast(node.entry.date!),
                  done: doneIds[node.entry.id],
                  dragging: draggingId === node.entry.id,
                }"
                @dragstart="
                  node.entry.id !== ANCHOR_ID &&
                  onDragStart($event, node.entry.id)
                "
                @dragend="onDragEnd"
              >
                <span class="dot"></span>
                <div class="when">
                  <b>{{ whenDate(node.entry.date!) }}</b>
                  <span
                    >{{ weekdayName(node.entry.date!) }} ·
                    {{ offsetLabel(node.entry.offset_days) }}</span
                  >
                </div>
                <div class="card">
                  <div class="card-head">
                    <button
                      v-if="node.entry.id !== ANCHOR_ID"
                      type="button"
                      class="check"
                      :aria-pressed="!!doneIds[node.entry.id]"
                      aria-label="Als erledigt markieren"
                      @click="toggleDone(node.entry.id)"
                    >
                      <Check v-if="doneIds[node.entry.id]" :size="11" />
                    </button>
                    <input
                      v-if="editingId === node.entry.id"
                      class="title-input"
                      :data-title-input="node.entry.id"
                      :value="node.entry.label"
                      placeholder="Was ist zu tun?"
                      @keydown.enter="
                        commitLabel(
                          node.entry.id,
                          ($event.target as HTMLInputElement).value,
                        )
                      "
                      @blur="
                        commitLabel(
                          node.entry.id,
                          ($event.target as HTMLInputElement).value,
                        )
                      "
                    />
                    <h3 v-else>{{ node.entry.label }}</h3>
                    <div v-if="node.entry.id !== ANCHOR_ID" class="tools">
                      <button
                        type="button"
                        title="Notiz"
                        aria-label="Notiz"
                        @click="openNote(node.entry.id)"
                      >
                        <Pencil :size="12" />
                      </button>
                      <button
                        type="button"
                        title="Entfernen"
                        aria-label="Entfernen"
                        @click="deleteEntry(node.entry)"
                      >
                        <X :size="13" />
                      </button>
                    </div>
                  </div>

                  <p v-if="node.entry.note">{{ node.entry.note }}</p>
                  <a
                    v-if="node.entry.source_url"
                    class="badge stamp"
                    :href="node.entry.source_url"
                    target="_blank"
                    rel="noopener"
                    >{{ node.entry.source_label ?? "Quelle" }}</a
                  >
                  <span
                    v-else-if="
                      node.entry.id !== ANCHOR_ID && isCustom(node.entry.id)
                    "
                    class="badge custom"
                    >Eigene Aufgabe</span
                  >
                  <span
                    v-else-if="node.entry.id !== ANCHOR_ID"
                    class="badge missing"
                    >Quelle fehlt</span
                  >

                  <template
                    v-if="
                      node.entry.id !== ANCHOR_ID && taskCtaFor(node.entry.id)
                    "
                  >
                    <a
                      v-if="taskCtaFor(node.entry.id)!.kind === 'link'"
                      class="badge cta"
                      :href="taskCtaFor(node.entry.id)!.url"
                      target="_blank"
                      rel="noopener"
                      >{{ taskCtaFor(node.entry.id)!.label }}</a
                    >
                    <button
                      v-else
                      type="button"
                      class="badge cta"
                      @click="openAttachment(node.entry.id)"
                    >
                      {{
                        node.entry.id in attachments
                          ? "Kündigungsschreiben bearbeiten"
                          : taskCtaFor(node.entry.id)!.label
                      }}
                    </button>
                  </template>

                  <textarea
                    v-if="openAttachmentId === node.entry.id"
                    class="note-input"
                    :data-attachment-input="node.entry.id"
                    :value="attachments[node.entry.id] ?? ''"
                    rows="10"
                    @keydown.esc="
                      commitAttachment(
                        node.entry.id,
                        ($event.target as HTMLTextAreaElement).value,
                      )
                    "
                    @blur="
                      commitAttachment(
                        node.entry.id,
                        ($event.target as HTMLTextAreaElement).value,
                      )
                    "
                  ></textarea>

                  <textarea
                    v-if="openNoteId === node.entry.id"
                    class="note-input"
                    :data-note-input="node.entry.id"
                    :value="userNotes[node.entry.id] ?? ''"
                    rows="2"
                    placeholder="Notiz - z. B. Aktenzeichen, Ansprechpartner, Telefonnummer"
                    @keydown.esc="
                      commitNote(
                        node.entry.id,
                        ($event.target as HTMLTextAreaElement).value,
                      )
                    "
                    @blur="
                      commitNote(
                        node.entry.id,
                        ($event.target as HTMLTextAreaElement).value,
                      )
                    "
                  ></textarea>
                  <p
                    v-else-if="userNotes[node.entry.id]"
                    class="note"
                    tabindex="0"
                    role="button"
                    @click="openNote(node.entry.id)"
                    @keydown.enter="openNote(node.entry.id)"
                  >
                    {{ userNotes[node.entry.id] }}
                  </p>

                  <p
                    v-if="!doneIds[node.entry.id] && node.entry.collision"
                    class="flag"
                  >
                    Fällt auf {{ node.entry.collision }} - Ämter geschlossen.
                  </p>
                  <p
                    v-else-if="!doneIds[node.entry.id] && node.entry.weekend"
                    class="flag"
                  >
                    Fällt auf ein Wochenende.
                  </p>
                </div>
              </div>
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
            <div
              v-if="isTaskPickerOpen({ kind: 'end' })"
              class="task-picker"
              role="menu"
              aria-label="Aufgabe auswählen"
            >
              <button
                v-for="preset in PRESET_TASKS"
                :key="preset"
                type="button"
                class="task-picker-option"
                role="menuitem"
                @click="pickPresetTask(preset)"
              >
                {{ preset }}
              </button>
              <button
                type="button"
                class="task-picker-option task-picker-blank"
                role="menuitem"
                @click="pickBlankTask"
              >
                + Eigene Aufgabe
              </button>
            </div>
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
              <li><span class="swatch stamp"></span>{{ vorhaben }}</li>
              <li><span class="swatch accent"></span>Feiertage</li>
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
        <p class="hint">
          Diese Fristen sind noch nicht recherchiert, deshalb fehlt ihr
          Zeitpunkt.
        </p>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="badge missing">Quelle fehlt</span>
          </li>
        </ul>
      </div>

      <div class="actions">
        <p>
          Änderungen gelten nur in diesem Tab und werden beim Neuladen
          zurückgesetzt. Fristen ohne Quelle bleiben vorläufig.
        </p>
        <div class="actions-buttons">
          <button type="button" @click="exportIcs">Als ICS exportieren</button>
          <button type="button" @click="print">Checkliste drucken</button>
        </div>
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
  /* --stamp: secondary "official stamp" color for provenance/edit affordances,
    additive to the site's single red accent. --paper/--paper-raised are
    lightened and pulled apart locally so a card reads as raised, not just
    outlined - the shadow tokens below are this component's own deliberate
    departure from the sitewide flat/no-shadow look (see global.css), kept
    local rather than global for that reason. */
  --stamp: #3b3b8f;
  --done-color: #3f7d4a;
  --paper: #fdfcfa;
  --paper-raised: #ffffff;
  --shadow-sm: 0 1px 3px color-mix(in srgb, var(--ink) 8%, transparent);
  --shadow-md: 0 2px 6px color-mix(in srgb, var(--ink) 8%, transparent);
  --shadow-lg: 0 4px 14px color-mix(in srgb, var(--ink) 16%, transparent);
  --tint-stamp: color-mix(in srgb, var(--stamp) 10%, transparent);
}
@media (prefers-color-scheme: dark) {
  .deadline-planner {
    --stamp: #9a9aec;
    --done-color: #7cc98a;
    --paper: #1c1d1f;
    --paper-raised: #28292c;
  }
}
:global(:root[data-theme="dark"]) .deadline-planner {
  --stamp: #9a9aec;
  --done-color: #7cc98a;
  --paper: #1c1d1f;
  --paper-raised: #28292c;
}
:global(:root[data-theme="light"]) .deadline-planner {
  --stamp: #3b3b8f;
  --done-color: #3f7d4a;
  --paper: #fdfcfa;
  --paper-raised: #ffffff;
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
  outline: 2px solid var(--stamp);
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
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
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
.item {
  position: relative;
}
/* .gap cancels the rail's indent (negative margin) and reapplies it as its
  own padding, so its hoverable box spans the full rail width including the
  line's gutter - hovering the line itself would otherwise do nothing.
  Padding doesn't move an absolute child's containing block (always the
  border-box edge), so .gap-add's `left` below is a positive rail-relative
  offset, unlike the negative item-relative one .dot/.when use. */
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
  border-color: var(--stamp);
  color: var(--stamp);
}
.item.dragging {
  opacity: 0.4;
}
/* Native drag events don't reliably trigger :hover, so drop-target state is
  JS-driven (dragOverGapId): .drag-target marks every valid gap, .active is
  the one currently under the pointer. */
.gap.drag-target {
  background: color-mix(in srgb, var(--stamp) 5%, transparent);
}
.gap.drag-target .gap-add {
  opacity: 0.6;
}
.gap.active {
  background: color-mix(in srgb, var(--stamp) 14%, transparent);
}
.gap.active .gap-add {
  opacity: 1;
  border-style: solid;
  border-color: var(--stamp);
  background: var(--stamp);
  color: #fff;
}
.dot {
  position: absolute;
  left: -1.8rem;
  top: 0.4rem;
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--paper);
  border: 1.5px solid var(--accent);
}
.item.anchor .dot {
  width: 0.8rem;
  height: 0.8rem;
  left: -1.95rem;
  background: var(--stamp);
  border-color: var(--stamp);
}
.item.past .dot {
  border-color: var(--muted);
  background: var(--muted);
}
.item.done .dot {
  border-color: var(--done-color);
  background: var(--done-color);
}
.when {
  position: absolute;
  left: -12.2rem;
  top: 0.55rem;
  width: 10rem;
  text-align: right;
  font-family: var(--font-mono);
}
.when b {
  display: block;
  /* Smaller than the rest on purpose: nowrap text wider than its box
    overflows rightward (not away from text-align), so this plus the
    generous .when width are safety margin for the longest realistic date. */
  font-size: 0.85rem;
  line-height: 1.3;
  white-space: nowrap;
}
.when span {
  display: block;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.3;
  white-space: nowrap;
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 0.7rem 0.9rem;
  margin-bottom: 0.4rem;
  cursor: grab;
  box-shadow:
    0 1px 3px color-mix(in srgb, var(--ink) 7%, transparent),
    0 1px 1px color-mix(in srgb, var(--ink) 5%, transparent);
}
.item.anchor .card {
  cursor: default;
  border-color: var(--stamp);
  border-width: 1.5px;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--stamp) 20%, transparent);
}
.item.past .card {
  opacity: 0.6;
}
.item.done .card {
  border-left: 3px solid var(--done-color);
  opacity: 0.75;
}
.item.done .card-head h3 {
  text-decoration: line-through;
  color: var(--muted);
}
.card-head {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}
.card-head h3,
.card-head .title-input {
  flex: 1;
  min-width: 0;
}
.card h3 {
  margin: 0;
  font-size: 1rem;
}
.title-input {
  font-family: inherit;
  font-weight: 600;
  font-size: 1rem;
  color: inherit;
  border: 1px solid var(--stamp);
  border-radius: 2px;
  padding: 0.15rem 0.4rem;
  background: var(--paper);
}
.check {
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  margin-top: 0.15rem;
  border: 1px solid var(--line);
  background: var(--paper);
  border-radius: 2px;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.check[aria-pressed="true"] {
  background: var(--done-color);
  border-color: var(--done-color);
}
.tools {
  display: flex;
  gap: 0.2rem;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s;
}
.card:hover .tools,
.tools:focus-within {
  opacity: 1;
}
@media (hover: none) {
  .tools {
    opacity: 1;
  }
}
.tools button {
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 2px;
  cursor: pointer;
  color: var(--muted);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.tools button:hover {
  background: var(--paper);
  border-color: var(--line);
  color: var(--ink);
}
.card p {
  margin: 0.3rem 0 0;
  color: var(--muted);
  font-size: 0.88rem;
}
.card .badge {
  margin-top: 0.5rem;
  margin-left: 0;
}
.badge.stamp {
  border-color: var(--stamp);
  color: var(--stamp);
  background: var(--tint-stamp);
}
.badge.custom {
  border-color: var(--line);
  color: var(--muted);
}
/* A clickable badge, unlike .badge.stamp - resets button chrome, adds hover tint. */
.badge.cta {
  margin-left: 0.4rem;
  border-color: var(--stamp);
  color: var(--stamp);
  background: transparent;
  cursor: pointer;
}
.badge.cta:hover {
  background: var(--tint-stamp);
}
.note-input {
  display: block;
  width: 100%;
  margin-top: 0.5rem;
  font-family: inherit;
  font-size: 0.85rem;
  color: inherit;
  border: 1px solid var(--line);
  border-radius: 2px;
  padding: 0.4rem 0.5rem;
  background: var(--paper);
  resize: vertical;
}
.note {
  margin: 0.5rem 0 0;
  padding: 0.4rem 0.6rem;
  background: color-mix(in srgb, var(--stamp) 6%, var(--paper-raised));
  border-left: 2px solid var(--line);
  font-size: 0.85rem;
  color: var(--ink);
  white-space: pre-wrap;
  cursor: text;
}
.flag {
  margin-top: 0.5rem !important;
  padding: 0.4rem 0.6rem;
  border-left: 2px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--ink) !important;
  font-size: 0.85rem !important;
}

.badge.missing {
  border-color: var(--line);
  color: var(--muted);
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
  border-color: var(--stamp);
  color: var(--stamp);
}
.add-end-wrap {
  position: relative;
}
/* Positioned against whichever ancestor is already relative (.gap or
  .add-end-wrap) - no new wrapper needed. */
.task-picker {
  position: absolute;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 15rem;
  max-width: 19rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-lg);
  padding: 0.3rem;
}
.gap .task-picker {
  left: 10.35rem;
  top: calc(50% + 1rem);
}
.add-end-wrap .task-picker {
  left: 0;
  top: calc(100% + 0.4rem);
}
.task-picker-option {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: 0.85rem;
  padding: 0.4rem 0.6rem;
  cursor: pointer;
  border-radius: 2px;
}
.task-picker-option:hover,
.task-picker-option:focus-visible {
  background: var(--tint-stamp);
  color: var(--stamp);
}
.task-picker-blank {
  margin-top: 0.2rem;
  border-top: 1px solid var(--line);
  border-radius: 0;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.task-picker-blank:hover,
.task-picker-blank:focus-visible {
  color: var(--stamp);
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
.swatch.stamp {
  background: var(--stamp);
}
.swatch.accent {
  background: var(--accent);
}

.undo {
  margin-top: 0.9rem;
  font-size: 0.85rem;
  color: var(--muted);
}
.undo button {
  background: none;
  border: 0;
  color: var(--stamp);
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

.actions {
  margin-top: 2.5rem;
  padding: 1rem 1.2rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.actions p {
  margin: 0;
  color: var(--muted);
  font-size: 0.88rem;
  max-width: 26rem;
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
  .when {
    position: static;
    width: auto;
    text-align: left;
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
    margin: 0 0 0.3rem 1.1rem;
  }
  .dot {
    left: 0;
  }
  .item.anchor .dot {
    left: -0.1rem;
  }
  .scalenote {
    margin-left: 0;
  }
  .gap .task-picker {
    left: 0;
    top: calc(100% + 0.3rem);
    max-width: calc(100vw - 3rem);
  }
}

@media print {
  .form,
  .gap-add,
  .tools,
  .add-end,
  .undo,
  .actions,
  .calendar-panel,
  .badge.cta,
  .task-picker {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
