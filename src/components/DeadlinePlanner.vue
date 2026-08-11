<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  useTemplateRef,
  watch,
} from "vue";
import { Check, Download, Link2, Plus, Printer } from "lucide-vue-next";
import TaskCard from "./deadline-planner/TaskCard.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import Timeline from "./deadline-planner/Timeline.vue";
import {
  FACET_LABELS,
  appliesTo,
  facetLabel,
  facetsUsedBy,
} from "../../lib/facets";
import { shortDate } from "../../lib/date-display";
import { toDate } from "../../lib/format-date";
import { generateIcs } from "../../lib/ics";
import type { IcsEvent } from "../../lib/ics";
import { taskCtaFor } from "./deadline-planner/task-cta";
import { useTaskEditor } from "./deadline-planner/useTaskEditor";
import {
  ANCHOR_ID,
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
const headerEl = useTemplateRef<HTMLElement>("headerEl");
const sentinelEl = useTemplateRef<HTMLElement>("sentinelEl");

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
// agree: cards, timeline and ICS export all read from workingDeadlines.
// Per-task state stays keyed by id, so unticking a chip and ticking it again
// brings a task back exactly as it was.
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

const { timeline, tasks, unscheduled, railNodes } = usePlannerSchedule(
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

// The plan in one sentence, so the list below has a frame. Verstrichen and
// offen are counted apart: a missed deadline is the only state that demands
// something today, and folding it into "offen" is what made the old sentence
// quote a recovery date as if it were the deadline.
const openEntries = computed(() =>
  timeline.value.filter((e) => e.id !== ANCHOR_ID && !doneIds[e.id]),
);
const overdueEntries = computed(() =>
  openEntries.value.filter((e) => isPast(e.date!)),
);
const openCount = computed(
  () => openEntries.value.length - overdueEntries.value.length,
);

const nextOpen = computed(() => {
  const upcoming = openEntries.value.filter((e) => !isPast(e.date!));
  if (upcoming.length === 0) return null;
  const next = upcoming.reduce((a, b) => (a.date! <= b.date! ? a : b));
  return { id: next.id, label: next.label, date: next.date! };
});

// Only a rule that can name an alternative day has one, so a plain missed
// offset leaves the sentence without a Nachholen clause rather than with a
// made-up date.
const catchUp = computed(() => {
  const withRescue = overdueEntries.value.filter((e) => e.rescue);
  if (withRescue.length === 0) return null;
  const first = withRescue.reduce((a, b) =>
    a.rescue!.date <= b.rescue!.date ? a : b,
  );
  return { id: first.id, date: first.rescue!.date };
});

const anchorIsSunday = computed(
  () => toDate(anchorDate.value).getUTCDay() === 0,
);

// The anchor day is the header's date field and the flag on the timeline, not
// a task, so it gets no card of its own.
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
const doneEntries = computed(() =>
  timeline.value.filter((e) => e.id !== ANCHOR_ID && doneIds[e.id]),
);

// The first task still open and not in the past: the one to act on.
const nextUpId = computed(
  () =>
    tasks.value.find((t) => t.date && !isPast(t.date) && !doneIds[t.id])?.id ??
    null,
);

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

const editingDateId = ref<string | null>(null);
function onCommitDate(id: string, iso: string) {
  editingDateId.value = null;
  const days = Math.round(
    (toDate(iso).getTime() - toDate(anchorDate.value).getTime()) / 86400000,
  );
  moveEntry(id, days);
}

// Hover is shared both ways: a hovered marker highlights its card, a hovered
// card highlights its marker, and a click on either selects.
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

// Sticky header: a sentinel above it decides when it is stuck, and the
// timeline then shrinks instead of being clipped. Its measured height is
// published so a card scrolled into view stops below it, never behind it.
// Scroll anchoring has to go while this is on screen: the header changing
// height above the reader's position makes the browser correct the scroll
// back, which unsticks the header, which grows it again, and the page then
// refuses to move until you push past the whole loop.
const stuck = ref(false);
const headerH = ref(0);
const looseHeaderH = ref(0); // its height before it ever shrank
// Shrinking costs the list its place, so the header hands the freed height
// back as margin, frame by frame while the strip morphs: the compact bar
// pins at the top and nothing below it moves at all.
const headerGap = computed(() =>
  Math.max(0, looseHeaderH.value - headerH.value),
);
const observers: (IntersectionObserver | ResizeObserver)[] = [];
onMounted(() => {
  document.documentElement.style.overflowAnchor = "none";
  if (sentinelEl.value) {
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) looseHeaderH.value = headerH.value;
        stuck.value = !entry.isIntersecting;
      },
      { threshold: 0 },
    );
    io.observe(sentinelEl.value);
    observers.push(io);
  }
  if (headerEl.value && rootEl.value) {
    const ro = new ResizeObserver(() => {
      const h = headerEl.value?.offsetHeight ?? 0;
      headerH.value = h;
      if (!stuck.value && h >= looseHeaderH.value) looseHeaderH.value = h;
      rootEl.value?.style.setProperty("--tl-header-h", `${h}px`);
    });
    ro.observe(headerEl.value);
    observers.push(ro);
  }
});
onBeforeUnmount(() => {
  document.documentElement.style.removeProperty("overflow-anchor");
  observers.forEach((o) => o.disconnect());
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
  <div ref="rootEl" class="deadline-planner" :class="{ compact: stuck }">
    <div ref="sentinelEl" class="sentinel"></div>

    <header
      ref="headerEl"
      class="planner-header"
      :style="{ marginBottom: headerGap + 'px' }"
    >
      <!-- No Vorhaben field: the page title already names it, and a card that
        looks like the other two but cannot be changed is a false promise. -->
      <div class="form">
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

      <template v-if="anchorDate">
        <p class="summary">
          <template v-if="overdueEntries.length > 0">
            <strong class="late">Du bist spät dran.</strong>
            {{ overdueEntries.length }}
            {{ overdueEntries.length === 1 ? "Frist" : "Fristen" }}
            verstrichen, {{ openCount }} offen.
            <template v-if="catchUp">
              Nachholen bis
              <a
                :href="`#task-${catchUp.id}`"
                @click.prevent="onTimelineSelect(catchUp.id)"
                >{{ shortDate(catchUp.date) }}</a
              >.
            </template>
          </template>
          <template v-else-if="nextOpen">
            {{ tasks.length }} Aufgaben, {{ openCount }} noch offen. Die nächste
            Frist ist am
            <a
              :href="`#task-${nextOpen.id}`"
              @click.prevent="onTimelineSelect(nextOpen.id)"
              >{{ shortDate(nextOpen.date) }}</a
            >: {{ nextOpen.label }}.
          </template>
          <template v-else>Alle Aufgaben sind erledigt.</template>
          <span v-if="anchorIsSunday" class="sunday">
            {{ anchorLabel }} ist ein Sonntag - Ämter und Übergaben brauchen
            einen Werktag.
          </span>
        </p>

        <Timeline
          :tasks="tasks"
          :anchor-date="anchorDate"
          :anchor-name="anchorLabel"
          :region-code="selected?.regionCode"
          :hover-id="hoveredId"
          :done-ids="doneIds"
          :compact="stuck"
          draggable
          drag-hint="Griff ziehen, um den Termin zu verschieben"
          @select="onTimelineSelect"
          @place="anchorDate = $event"
          @hover="hoveredId = $event"
        />
      </template>
    </header>

    <template v-if="anchorDate">
      <fieldset v-if="facetOptions.length > 1" class="facets">
        <legend>Trifft auf mich zu</legend>
        <label v-for="id in facetOptions" :key="id" class="facet">
          <input v-model="activeFacets" type="checkbox" :value="id" />
          <span>{{ facetLabel(id) }}</span>
        </label>
      </fieldset>

      <h2 class="section">Aufgaben</h2>
      <div ref="railEl" class="rail">
        <template
          v-for="node in openNodes"
          :key="node.kind === 'gap' ? node.id : node.entry.id"
        >
          <div
            v-if="node.kind === 'gap'"
            class="gap"
            :title="`${node.bufferDays} Tage Puffer`"
            :style="{ height: `${node.heightPx}px` }"
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
            :class="{ focused: hoveredId === node.entry.id }"
            :entry="node.entry"
            :anchor-date="anchorDate"
            :is-past="isPast(node.entry.date!)"
            :done="!!doneIds[node.entry.id]"
            :is-custom="isCustom(node.entry.id)"
            :is-next="node.entry.id === nextUpId"
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

      <div v-if="unscheduled.length > 0" class="unscheduled">
        <h2 class="section">Noch nicht terminiert</h2>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="badge missing">Erfahrungswert</span>
          </li>
        </ul>
      </div>

      <div class="actions">
        <h2 class="section">Plan mitnehmen</h2>
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
  max-width: 62rem;
  --tint-accent: color-mix(in srgb, var(--accent) 10%, transparent);
}
.sentinel {
  height: 1.5rem;
}

/* Everything that answers "when is it" stays on screen: the fields, the one
  sentence and the timeline. Stuck, it swaps to the compact metrics. A header
  taller than the window pins its bottom edge instead of its top, so it can
  never own the whole viewport and leave nothing to scroll to. */
.planner-header {
  position: sticky;
  top: min(0px, calc(100vh - var(--tl-header-h, 0px) - 2rem));
  z-index: 40;
  background: var(--paper);
  padding: 0 0 0.5rem;
  transition:
    padding 0.18s,
    box-shadow 0.18s;
}
.compact .planner-header {
  padding: 0.4rem 0 0.3rem;
  box-shadow: 0 10px 24px -18px color-mix(in srgb, var(--ink) 55%, transparent);
  border-bottom: 1px solid var(--line);
}

.form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
}
.field {
  display: block;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.7rem 1rem;
  min-width: 0;
  transition:
    padding 0.22s,
    border-color 0.22s,
    background-color 0.22s;
}
.field:hover,
.field:focus-within {
  border-color: var(--accent);
}
.field span {
  display: block;
  overflow: hidden;
  max-height: 1.5rem;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.25rem;
  transition:
    max-height 0.22s,
    opacity 0.22s,
    margin-bottom 0.22s;
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
  transition: font-size 0.22s;
}
.field input {
  font-family: var(--font-mono);
}
.field input:focus-visible,
.field select:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
/* Stuck, the boxes shed their chrome and their labels and become one slim
  row of facts. Every step of that is a transition, never a swap: a layout
  that changes shape mid-scroll reads as a glitch. */
.compact .field {
  border-color: transparent;
  background: transparent;
  padding: 0.1rem 0.4rem;
}
.compact .field span {
  max-height: 0;
  opacity: 0;
  margin-bottom: 0;
}
.compact .field input,
.compact .field select {
  font-size: var(--fs-sm);
}

.summary {
  margin: 0.6rem 0 0.4rem;
  font-size: var(--fs-md);
  transition:
    font-size 0.22s,
    margin 0.22s;
}
.summary a {
  color: var(--accent);
}
.summary .late {
  color: var(--warn);
}
.compact .summary {
  margin: 0.3rem 0 0.2rem;
  font-size: var(--fs-sm);
}
.sunday {
  display: block;
  overflow: hidden;
  max-height: 3rem;
  font-size: var(--fs-sm);
  color: var(--muted);
  transition:
    max-height 0.22s,
    opacity 0.22s;
}
.compact .sunday {
  max-height: 0;
  opacity: 0;
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

.rail {
  /* Distance from a card's left edge to the spine, read by TaskCard's dot. */
  --rail-gap: 1.4rem;
  position: relative;
  padding-left: 2.2rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 0.5rem;
  top: 0.6rem;
  bottom: 0.6rem;
  width: 1px;
  background: var(--line);
}
/* The buffer between two deadlines, kept as real height so the list breathes
  in proportion to the plan, plus the place a new task is inserted. The
  negative margin lets its "+" sit on the spine, in the rail's own padding. */
.gap {
  position: relative;
  margin-left: -2.2rem;
  padding-left: 2.2rem;
}
.gap-add {
  position: absolute;
  left: 0.5rem;
  top: 50%;
  transform: translate(-50%, -50%);
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
.gap :deep(.task-picker) {
  left: 1.5rem;
  top: calc(50% + 0.5rem);
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
  border-radius: 50%;
  border: 1px solid var(--done-color);
  background: var(--done-color);
  color: var(--paper-raised);
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

.actions {
  margin-top: 1rem;
  padding: 1rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
}
.actions .section {
  margin-top: 0;
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
    --rail-gap: 0.95rem;
    padding-left: 1.5rem;
  }
  .gap {
    margin-left: -1.5rem;
    padding-left: 1.5rem;
  }
  .rail::before {
    left: 0.25rem;
  }
  .gap-add {
    left: 0.25rem;
  }
  .form {
    grid-template-columns: 1fr;
    gap: 0.4rem;
  }
  .planner-header {
    padding-top: 0.4rem;
  }
}

@media print {
  .planner-header :deep(.timeline),
  .facets,
  .gap-add,
  .add-end,
  .undo,
  .actions {
    display: none;
  }
  /* The header keeps printing: a checklist without the move date is useless. */
  .planner-header {
    position: static;
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
