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
import { Check, Download, Info, Link2, Plus, Printer } from "lucide-vue-next";
import TaskCard from "./deadline-planner/TaskCard.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import Timeline from "./deadline-planner/Timeline.vue";
import {
  FACET_LABELS,
  appliesTo,
  facetLabel,
  facetsUsedBy,
} from "../../lib/facets";
import { formatDateWithWeekday, toDate } from "../../lib/format-date";
import { newSourceIssueUrl } from "../../lib/github-issue";
import { computeSchedule } from "../../lib/deadline-plan";
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

// Which optional circumstances the user ticked. Off by default: a plan should
// open with what applies to everyone, not with every special case at once.
const activeFacets = ref<string[]>(
  (urlParams?.get("facets") ?? "").split(",").filter((f) => f in FACET_LABELS),
);
const facetOptions = computed(() =>
  facetsUsedBy(selected.value?.deadlines ?? []),
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

// The single most consequential assumption in the plan: whether the old flat
// ends with the moving month or a month later. Worth a control, not a footnote.
const overlapMonths = ref(urlParams?.get("overlap") === "1" ? 1 : 0);

// Keeps the plan shareable as a link - replaceState, not pushState, so picking a date doesn't spam browser history.
watch(
  [anchorDate, selectedSlug, activeFacets, overlapMonths],
  () => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (anchorDate.value) params.set("date", anchorDate.value);
    if (selected.value) params.set("variant", selected.value.slug);
    if (activeFacets.value.length > 0)
      params.set("facets", activeFacets.value.join(","));
    else params.delete("facets");
    if (overlapMonths.value > 0) params.set("overlap", "1");
    else params.delete("overlap");
    const query = params.toString();
    history.replaceState(
      null,
      "",
      query ? `?${query}` : window.location.pathname,
    );
  },
  { immediate: true },
);

// Filtering here, upstream of the editing layer, is what makes every consumer
// agree: rail, compact timeline, ICS export and the unverified count all read
// from workingDeadlines. Per-task state stays keyed by id, so unticking a chip
// and ticking it again brings a task back exactly as it was.
const selectedForPlan = computed(() =>
  selected.value
    ? {
        ...selected.value,
        deadlines: selected.value.deadlines.filter((d) =>
          appliesTo(d, activeFacets.value),
        ),
      }
    : undefined,
);

const {
  doneIds,
  userNotes,
  editingId,
  openNoteId,
  attachments,
  openAttachmentId,
  lastDeleted,
  workingDeadlines,
  isCustom,
  toggleDone,
  startEditingLabel,
  commitLabel,
  openNote,
  commitNote,
  openAttachment,
  commitAttachment,
  deleteEntry,
  undoDelete,
  insertCustomTask,
  addTaskAtEnd,
  moveEntry,
} = useTaskEditor(
  selectedForPlan,
  rootEl,
  computed(() => `wann:plan:${props.vorhaben}:${selectedSlug.value}`),
);

// Editing a date directly, instead of dragging a card to a different gap -
// same underlying moveEntry(id, offsetDays), just fed from a native date
// input rather than a drop target. The anchor is a special case: it's not
// in workingDeadlines at all (usePlannerSchedule injects it separately with
// a fixed offset_days: 0), so moveEntry has nothing to move - editing its
// date means moving the anchor itself, the same as the form's date field.
// Ticking a task off earns a 12 piece burst. Drawn on body, so no card and no
// overflow: hidden can clip it.
function onToggleDone(id: string) {
  const wasDone = doneIds[id];
  toggleDone(id);
  if (wasDone || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const el = rootEl.value?.querySelector(`[data-entry-id="${id}"] .check`);
  if (!el) return;
  const box = el.getBoundingClientRect();
  const colors = ["var(--accent)", "var(--warn)", "var(--ink)"];
  for (let i = 0; i < 12; i++) {
    const piece = document.createElement("i");
    piece.className = "wom-confetti";
    piece.style.left = `${box.left + box.width / 2}px`;
    piece.style.top = `${box.top + box.height / 2}px`;
    piece.style.background = colors[i % colors.length];
    document.body.appendChild(piece);
    const angle = (Math.PI * 2 * i) / 12 + Math.random() * 0.4;
    const dist = 40 + Math.random() * 40;
    piece
      .animate(
        [
          { transform: "translate(0,0) scale(1)", opacity: 1 },
          {
            transform: `translate(${Math.cos(angle) * dist}px,${Math.sin(angle) * dist + 30}px) scale(0.4) rotate(${Math.random() * 360}deg)`,
            opacity: 0,
          },
        ],
        {
          duration: 600 + Math.random() * 300,
          easing: "cubic-bezier(.2,.7,.4,1)",
        },
      )
      .addEventListener("finish", () => piece.remove());
  }
}

// The plan in one sentence, so the numbers below have a frame.
const summary = computed(() => {
  const open = timeline.value.filter(
    (e) => e.id !== ANCHOR_ID && !doneIds[e.id],
  );
  const head = `Aus deinem ${props.anchorLabel} am ${formatDateWithWeekday(anchorDate.value)} ergeben sich ${tasks.value.length} Aufgaben.`;
  if (open.length === 0) return `${head} Alle sind erledigt.`;
  const next = open.reduce((a, b) => (a.date! <= b.date! ? a : b));
  return `${head} Die nächste offene ist am ${formatDateWithWeekday(next.date!)}.`;
});

const suppressDate = computed(() => {
  const ids = new Set<string>();
  let lastDate: string | null = null;
  for (const node of railNodes.value) {
    if (node.kind !== "item") continue;
    if (node.entry.date !== null && node.entry.date === lastDate)
      ids.add(node.entry.id);
    lastDate = node.entry.date;
  }
  return ids;
});

// Ticked-off tasks leave the running plan and collect in a fold at the end.
const openNodes = computed(() => {
  const kept = railNodes.value.filter(
    (n) => n.kind === "gap" || !doneIds[n.entry.id] || n.entry.id === ANCHOR_ID,
  );
  // Filtering done tasks out can leave a gap with nothing above it, and a
  // buffer before the plan starts measures nothing.
  while (kept.length > 0 && kept[0].kind === "gap") kept.shift();
  return kept;
});
const doneEntries = computed(() =>
  timeline.value.filter((e) => e.id !== ANCHOR_ID && doneIds[e.id]),
);

// The first task still open and not in the past: the one to act on.
const nextUpId = computed(
  () =>
    tasks.value.find((t) => t.date && !isPast(t.date) && !doneIds[t.id])?.id ??
    null,
);

// Nothing happens between today and the first task, and saying so beats an
// unexplained stretch of empty rail.
const quietUntil = computed(() => {
  if (stats.value.done > 0) return null;
  const next = tasks.value.find((t) => t.date && !isPast(t.date));
  if (!next) return null;
  const days = Math.round(
    (toDate(next.date!).getTime() - toDate(isoToday()).getTime()) / 86400000,
  );
  return days >= 21 ? formatDateWithWeekday(next.date!) : null;
});

// The date under the flag while it is being dragged, so the collision count
// can answer "is this a better day" before the drag ends.
const dragPreview = ref<string | null>(null);
function isoShift(iso: string, days: number): string {
  return new Date(toDate(iso).getTime() + days * 86400000)
    .toISOString()
    .slice(0, 10);
}
function blockedAt(shiftDays: number): number {
  return computeSchedule(
    isoShift(anchorDate.value, shiftDays),
    workingDeadlines.value,
    COUNTRY_CODE,
    selected.value?.regionCode,
  ).filter((e) => e.needs_office === true && (e.weekend || e.collision)).length;
}
const previewCollisions = computed(() => {
  if (!dragPreview.value) return null;
  const shift = Math.round(
    (toDate(dragPreview.value).getTime() - toDate(anchorDate.value).getTime()) /
      86400000,
  );
  return blockedAt(shift);
});

const landscapeNote = computed(() => {
  if (previewCollisions.value !== null)
    return `${formatDateWithWeekday(dragPreview.value!)} · ${previewCollisions.value} Kollisionen`;
  return "Ferien, Feiertage, Wochenenden und die schon vergangene Zeit.";
});

// Tasks that need an open office on a day when none is open.
const blockedTasks = computed(() =>
  tasks.value.filter(
    (t) =>
      t.needs_office === true &&
      !doneIds[t.id] &&
      t.date !== null &&
      t.offset_days !== 0 &&
      (t.weekend || t.collision),
  ),
);
function shiftAllToWorkday() {
  for (const t of blockedTasks.value) shiftToWorkday(t);
}

// Moving a weekend deadline to the Friday before it, through the same
// moveEntry path a drag uses.
function shiftToWorkday(entry: {
  id: string;
  date: string | null;
  collision?: string | null;
  weekend?: boolean;
}) {
  if (!entry.date) return;
  let d = toDate(entry.date);
  if (entry.collision && !entry.weekend) d = new Date(d.getTime() - 86400000);
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6)
    d = new Date(d.getTime() - 86400000);
  onCommitDate(entry.id, d.toISOString().slice(0, 10));
}

// The URL already carries date, Ort, facets and the Mietende choice. It does
// NOT carry ticks, notes or custom tasks, so the label must not promise them.
const linkCopied = ref(false);
async function copyPlanLink() {
  try {
    await navigator.clipboard.writeText(window.location.href);
    linkCopied.value = true;
    setTimeout(() => (linkCopied.value = false), 2000);
  } catch {
    // no clipboard permission - the address bar still has the same link
  }
}

const sourceIssueUrl = newSourceIssueUrl();
const editingDateId = ref<string | null>(null);
function onCommitDate(id: string, iso: string) {
  editingDateId.value = null;
  if (id === ANCHOR_ID) {
    anchorDate.value = iso;
    return;
  }
  const days = Math.round(
    (toDate(iso).getTime() - toDate(anchorDate.value).getTime()) / 86400000,
  );
  moveEntry(id, days);
}

const { timeline, tasks, unscheduled, railNodes, stats } = usePlannerSchedule(
  anchorDate,
  selected,
  workingDeadlines,
  () => props.anchorLabel,
  doneIds,
  overlapMonths,
);

function isPast(date: string): boolean {
  return date < isoToday();
}

// One line ("6 von 10 Fristen noch nicht verifiziert") instead of a
// "Quelle fehlt" badge repeated on every unsourced card - the per-card badge
// read as ten separate apologies for the same gap. Tasks marked
// no_source_needed (e.g. Sperrmüllabholung - no Satzung governs a deadline
// for it at all) don't count toward either side of the fraction.
const verifiableTasks = computed(() =>
  tasks.value.filter((t) => !t.no_source_needed),
);
const unverifiedCount = computed(
  () => verifiableTasks.value.filter((t) => t.source_url === null).length,
);
const verifiedCount = computed(
  () => verifiableTasks.value.length - unverifiedCount.value,
);
const noSourceCount = computed(
  () => tasks.value.length - verifiableTasks.value.length,
);

// Only the FIRST card in a run of same-date entries shows its date - three
// identical "15. Oktober 2026" blocks stacked on top of each other read like
// a rendering bug, not "these three tasks happen to share a day".

// Scroll-linked highlight: tracks the page's own scroll (the rail has no inner scrollbox), picks the item closest to a fixed viewport line.
const highlightedDate = ref<string | null>(null);
const viewRange = ref<[string, string] | null>(null);
let scrollRaf = false;
function updateHighlight() {
  const container = railEl.value;
  if (!container) return;
  const items = container.querySelectorAll<HTMLElement>("[data-entry-date]");
  let closestDate: string | null = null;
  let closestDelta = Number.POSITIVE_INFINITY;
  let lastDate: string | null = null;
  // Which dates are on screen right now, for the timeline's viewport box.
  let firstSeen: string | null = null;
  let lastSeen: string | null = null;
  for (const el of items) {
    const date = el.dataset.entryDate;
    if (!date) continue;
    lastDate = date;
    const box = el.getBoundingClientRect();
    if (box.bottom > 0 && box.top < window.innerHeight) {
      if (!firstSeen) firstSeen = date;
      lastSeen = date;
    }
    const delta = Math.abs(
      el.getBoundingClientRect().top - window.innerHeight / 2,
    );
    if (delta < closestDelta) {
      closestDelta = delta;
      closestDate = date;
    }
  }
  // At the very bottom of the page the last item's top can never reach the
  // highlight line (there's nothing left to scroll it down to) - the
  // line-proximity search alone would then highlight whatever's closest,
  // never the last item, however far the user scrolls.
  const atBottom =
    window.innerHeight + window.scrollY >=
    document.documentElement.scrollHeight - 2;
  highlightedDate.value = atBottom ? lastDate : (closestDate ?? lastDate);
  viewRange.value = firstSeen && lastSeen ? [firstSeen, lastSeen] : null;
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

// Hover state is shared both ways: hovering a Timeline node sets it (via
// @hover below), which highlights the matching card. Hovering a card sets it
// too (via @mouseenter/@mouseleave on TaskCard), which highlights the
// matching node - same ref, two sources.
const hoveredId = ref<string | null>(null);
let flashTimer: ReturnType<typeof setTimeout> | undefined;

// Reverse direction of the highlight sync above: clicking a node/pin on the
// compact Timeline scrolls the rail to that task and briefly flashes it via
// the same hover styling, so the jump is easy to follow.
function onTimelineSelect(id: string) {
  railEl.value
    ?.querySelector(`[data-entry-id="${id}"]`)
    ?.scrollIntoView({ block: "center", behavior: "smooth" });
  hoveredId.value = id;
  clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    if (hoveredId.value === id) hoveredId.value = null;
  }, 900);
}

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
  // The statically rendered plan (StaticPlan.astro) shows the same deadlines
  // relative to the anchor day, for crawlers and for a failed hydration. Once
  // this island is up it shows them with real dates, so the static copy goes.
  document.getElementById("static-plan")?.remove();
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
      <div class="field static">
        <span>Vorhaben</span>
        <strong>{{ vorhaben }}</strong>
      </div>
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

    <fieldset v-if="facetOptions.length > 1" class="facets">
      <legend>Trifft auf mich zu</legend>
      <p class="facets-hint">Ergänze deine Situation für weitere Aufgaben.</p>
      <label v-for="id in facetOptions" :key="id" class="facet">
        <input v-model="activeFacets" type="checkbox" :value="id" />
        <span>{{ facetLabel(id) }}</span>
      </label>
    </fieldset>

    <template v-if="anchorDate">
      <div v-if="tasks.length > 0" class="mini-header">
        <b>{{ stats.done }} von {{ tasks.length }} erledigt</b>
        <progress :value="stats.done" :max="tasks.length"></progress>
      </div>

      <p class="summary">{{ summary }}</p>
      <p v-if="blockedTasks.length > 0" class="quiet grouped-warn">
        {{ blockedTasks.length }}
        {{ blockedTasks.length === 1 ? "Aufgabe fällt" : "Aufgaben fallen" }}
        auf einen Tag mit geschlossenen Ämtern.
        <button type="button" @click="shiftAllToWorkday">
          {{ blockedTasks.length === 1 ? "Vorziehen" : "Alle vorziehen" }}
        </button>
      </p>
      <p v-if="quietUntil" class="quiet">
        Bis {{ quietUntil }} ist nichts zu tun.
      </p>

      <div class="overview-wrap">
        <div class="overview">
          <div class="overview-inner">
            <Timeline
              :tasks="tasks"
              :anchor-date="anchorDate"
              :anchor-name="anchorLabel"
              :region-code="selected?.regionCode"
              :highlight-date="highlightedDate"
              :view-range="viewRange"
              :hover-id="hoveredId"
              :done-ids="doneIds"
              compact
              draggable
              @select="onTimelineSelect"
              @place="anchorDate = $event"
              @preview="dragPreview = $event"
              @hover="hoveredId = $event"
            />
          </div>
        </div>
        <p class="scalenote">{{ landscapeNote }}</p>
      </div>
      <p v-if="unverifiedCount > 0" class="verify-note">
        <Info :size="13" />
        <span>
          Von {{ tasks.length }} Aufgaben sind {{ verifiedCount }} gesetzlich
          belegt, {{ unverifiedCount }} beruhen auf Erfahrungswerten,
          {{ noSourceCount }} brauchen keine Quelle.
          <a :href="sourceIssueUrl" target="_blank" rel="noopener"
            >Quelle vorschlagen</a
          >
        </span>
      </p>
      <div class="rail-column">
        <div ref="railEl" class="rail">
          <template
            v-for="node in openNodes"
            :key="node.kind === 'gap' ? node.id : node.entry.id"
          >
            <div
              v-if="node.kind === 'gap'"
              class="gap"
              :title="`${node.bufferDays} Tage Puffer`"
              :class="{ tall: node.bufferDays >= 14 }"
              :style="{ height: `${node.heightPx}px` }"
            >
              <span v-if="node.bufferDays >= 14" class="gap-label">
                {{ node.bufferDays }} Tage Puffer
              </span>
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
              :class="{
                current: node.entry.date === highlightedDate,
                focused: hoveredId === node.entry.id,
              }"
              :entry="node.entry"
              :anchor-label="anchorLabel"
              :is-anchor="node.entry.id === ANCHOR_ID"
              :is-past="!node.entry.rescue && isPast(node.entry.date!)"
              :done="!!doneIds[node.entry.id]"
              :is-custom="isCustom(node.entry.id)"
              :is-next="node.entry.id === nextUpId"
              :show-date="!suppressDate.has(node.entry.id)"
              :editing="editingId === node.entry.id"
              :note-open="openNoteId === node.entry.id"
              :note-text="userNotes[node.entry.id]"
              :attachment-open="openAttachmentId === node.entry.id"
              :attachment-text="attachments[node.entry.id]"
              :has-attachment="node.entry.id in attachments"
              :cta="taskCtaFor(node.entry.id)"
              :date-edit-open="editingDateId === node.entry.id"
              :deferred="overlapMonths > 0"
              @toggle-done="onToggleDone(node.entry.id)"
              @commit-label="commitLabel(node.entry.id, $event)"
              @open-label-edit="startEditingLabel(node.entry.id)"
              @open-note="openNote(node.entry.id)"
              @commit-note="commitNote(node.entry.id, $event)"
              @open-attachment="openAttachment(node.entry.id)"
              @commit-attachment="commitAttachment(node.entry.id, $event)"
              @delete="deleteEntry(node.entry)"
              @open-date-edit="editingDateId = node.entry.id"
              @close-date-edit="editingDateId = null"
              @toggle-defer="overlapMonths = overlapMonths > 0 ? 0 : 1"
              @shift-to-workday="shiftToWorkday(node.entry)"
              @commit-date-edit="onCommitDate(node.entry.id, $event)"
              @mouseenter="hoveredId = node.entry.id"
              @mouseleave="hoveredId = null"
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

        <details v-if="doneEntries.length > 0" class="done-group">
          <summary>Erledigte Aufgaben</summary>
          <ul>
            <li v-for="entry in doneEntries" :key="entry.id">
              <button
                type="button"
                class="check"
                aria-pressed="true"
                aria-label="Wieder öffnen"
                @click="toggleDone(entry.id)"
              >
                <Check :size="11" />
              </button>
              <span>{{ entry.label }}</span>
            </li>
          </ul>
        </details>

        <p v-if="lastDeleted" class="undo">
          „{{ lastDeleted.label }}" entfernt.
          <button type="button" @click="undoDelete">Rückgängig</button>
        </p>
      </div>

      <div v-if="unscheduled.length > 0" class="unscheduled">
        <h2>Noch nicht terminiert</h2>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="badge missing">Erfahrungswert</span>
          </li>
        </ul>
      </div>

      <div class="sticky-export">
        <button type="button" @click="exportIcs">
          <Download :size="14" /> Als ICS exportieren
        </button>
      </div>

      <div class="actions">
        <h2>Plan mitnehmen</h2>
        <div class="actions-buttons">
          <button type="button" @click="copyPlanLink">
            <Link2 :size="14" />
            {{ linkCopied ? "Kopiert" : "Plan-Link kopieren" }}
          </button>
          <button type="button" @click="exportIcs">
            <Download :size="14" /> Als ICS exportieren
          </button>
          <button type="button" @click="print">
            <Printer :size="14" /> Checkliste drucken
          </button>
        </div>
        <p>
          Der Link enthält Datum, Ort und Einstellungen. Häkchen, Notizen und
          eigene Aufgaben bleiben nur in diesem Browser, auf einem anderen Gerät
          ist der Plan wieder leer.
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
  /* A single content column does not need the old two-column width. */
  max-width: 58rem;
  /* The elevation scale and the palette are sitewide now (see global.css),
    only these two are this component's own. */
  --shadow-lg: 0 6px 24px color-mix(in srgb, var(--ink) 18%, transparent);
  --tint-accent: color-mix(in srgb, var(--accent) 10%, transparent);
}
/* Separate elevated fields, not one hairline-divided grid. */
.form {
  display: grid;
  grid-template-columns: 1.3fr 1fr 1fr;
  gap: 0.6rem;
}
.field {
  display: block;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 1rem 1rem;
  box-shadow: var(--shadow-sm);
  transition:
    border-color 0.12s,
    box-shadow 0.12s;
}
/* Every field is editable, so every field reacts to a cursor. */
.field:hover,
.field:focus-within {
  border-color: var(--accent);
  box-shadow: var(--shadow-md);
}
.field span {
  display: block;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.field input,
.field select {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  font-size: var(--fs-md);
  font-weight: 600;
  cursor: pointer;
}
.field strong {
  display: block;
  font-size: var(--fs-md);
  font-weight: 600;
}
/* Not editable, so it does not pretend to react to a cursor. */
.field.static {
  box-shadow: none;
  background: transparent;
}
.field.static:hover {
  border-color: var(--line);
  box-shadow: none;
}
.field input:focus-visible,
.field select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
/* Two columns left a dead cell showing the container's line color, and both
  selects truncated their text. */
@media (max-width: 40rem) {
  .form {
    grid-template-columns: 1fr;
  }
}

.facets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  border: 0;
  padding: 0;
  /* No side indent - it has to line up with the form above and the rail below. */
  margin: 1rem 0;
}
.mini-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin-bottom: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius);
  background: var(--paper-raised);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-sm);
  font-size: var(--fs-sm);
}
.mini-header progress {
  flex: 1 1 8rem;
  max-width: 14rem;
  height: 0.25rem;
  accent-color: var(--done-color);
}
.summary {
  margin: 0 0 0.5rem;
  font-size: var(--fs-md);
}
.quiet {
  margin: 0 0 1rem;
  color: var(--muted);
  font-size: var(--fs-sm);
}
.grouped-warn {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.grouped-warn button {
  font-size: var(--fs-xs);
  padding: 0.25rem 0.5rem;
}
.facets-hint {
  flex-basis: 100%;
  margin: 0 0 0.5rem;
  color: var(--muted);
  font-size: var(--fs-xs);
}
.facets legend {
  /* Not a flex item, so it sits on its own line above the options. */
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

/* The landscape stays on screen while the list scrolls past it. */
.overview-wrap {
  position: sticky;
  top: 0;
  z-index: 6;
  margin-bottom: 1rem;
  padding-bottom: 0.25rem;
  background: var(--paper);
  box-shadow: 0 1px 0 var(--line);
}
@media (max-width: 40rem) {
  .overview-wrap {
    position: static;
    box-shadow: none;
  }
}
.overview {
  margin: 0.5rem 0 0;
}
.scalenote {
  font-size: var(--fs-xs);
  color: var(--muted);
  margin: 1rem 0 1rem 11.6rem;
}
.verify-note {
  margin: 0 0 1rem 11.6rem;
  padding: 0.5rem 0.75rem;
  border-left: 2px solid var(--line);
  background: color-mix(in srgb, var(--muted) 8%, transparent);
  color: var(--muted);
  font-size: var(--fs-xs);
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.rail-column {
  min-width: 0;
}
.rail {
  /* Distance from a card's left edge to the rail line. TaskCard's dots read
    it so they stay centred on the line at every breakpoint. */
  --rail-gap: 0.9rem;
  position: relative;
  margin: 0;
  padding: 0.5rem 0 0.5rem 11.6rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 10.7rem;
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
  margin-left: -11.6rem;
  padding-left: 11.6rem;
}
/* Every gap tall enough to notice says how long it is. */
.gap-label {
  position: absolute;
  left: 11.6rem;
  top: 50%;
  transform: translateY(-50%);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--muted);
  pointer-events: none;
}
.gap-add {
  position: absolute;
  /* Centered on .rail::before's line. */
  left: 10.05rem;
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
.add-end {
  display: block;
  width: 100%;
  margin-top: 1rem;
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
.done-group {
  margin-top: 1rem;
  font-size: var(--fs-sm);
}
.done-group summary {
  cursor: pointer;
  color: var(--muted);
}
.done-group ul {
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.done-group li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--muted);
  text-decoration: line-through;
}
.done-group .check {
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: 1px solid var(--done-color);
  background: var(--done-color);
  color: var(--paper-raised);
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

.unscheduled {
  margin-top: 2rem;
  padding-top: 1rem;
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

/* Phones only: the desktop copy of this button lives in .actions below. */
.sticky-export {
  display: none;
}
@media (max-width: 40rem) {
  .sticky-export {
    position: sticky;
    bottom: 0;
    z-index: 7;
    display: block;
    margin: 1rem -1rem 0;
    padding: 0.5rem 1rem;
    background: var(--paper);
    border-top: 1px solid var(--line);
  }
  .sticky-export button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    width: 100%;
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-ink);
  }
}
.actions {
  margin-top: 2rem;
  padding: 1rem 1rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
}
.actions h2 {
  margin: 0 0 0.75rem;
  font-size: var(--fs-md);
  border: 0;
  padding: 0;
}
.actions p {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: var(--fs-xs);
}
.actions-buttons {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.actions-buttons button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

@media (max-width: 40rem) {
  .rail {
    --rail-gap: 1.2rem;
    padding-left: 1.5rem;
  }
  .gap {
    margin-left: -1.4rem;
    padding-left: 1.5rem;
  }
  .rail::before {
    left: 0.2rem;
  }
  .gap-add {
    left: 0.05rem;
  }
  .scalenote,
  .verify-note {
    margin-left: 0;
  }
  .gap :deep(.task-picker) {
    left: 0;
    top: calc(100% + 0.3rem);
    max-width: calc(100vw - 3rem);
  }
}

@media print {
  .facets,
  .form,
  .overview-wrap,
  .mini-header,
  .sticky-export,
  .gap-add,
  .add-end,
  .undo,
  .actions {
    display: none;
  }
}

/* Confetti lives on document.body, so scoped selectors can never match it. */
:global(.wom-confetti) {
  position: fixed;
  width: 6px;
  height: 6px;
  pointer-events: none;
  z-index: 80;
}
</style>
