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
import { Download, Info, Plus, Printer } from "lucide-vue-next";
import TaskCard from "./deadline-planner/TaskCard.vue";
import TaskPicker from "./deadline-planner/TaskPicker.vue";
import Timeline from "./deadline-planner/Timeline.vue";
import {
  FACET_LABELS,
  appliesTo,
  facetLabel,
  facetsUsedBy,
} from "../../lib/facets";
import { toDate } from "../../lib/format-date";
import { newSourceIssueUrl } from "../../lib/github-issue";
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
const overviewEl = useTemplateRef<HTMLElement>("overviewEl");

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

// Keeps the plan shareable as a link - replaceState, not pushState, so picking a date doesn't spam browser history.
watch(
  [anchorDate, selectedSlug, activeFacets],
  () => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (anchorDate.value) params.set("date", anchorDate.value);
    if (selected.value) params.set("variant", selected.value.slug);
    if (activeFacets.value.length > 0)
      params.set("facets", activeFacets.value.join(","));
    else params.delete("facets");
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

// Below this a gap is just breathing room. Labelling it twice in a row adds
// noise without insight.
const BUFFER_LABEL_DAYS = 14;
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

// The single most consequential assumption in the plan: whether the old flat
// ends with the moving month or a month later. Worth a control, not a footnote.
const overlapMonths = ref(0);
const hasNoticeRule = computed(() =>
  workingDeadlines.value.some((d) => d.offset_rule === "bgb-573c-notice"),
);

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

// Only the FIRST card in a run of same-date entries shows its date - three
// identical "15. Oktober 2026" blocks stacked on top of each other read like
// a rendering bug, not "these three tasks happen to share a day".
const suppressDate = computed(() => {
  const ids = new Set<string>();
  let lastDate: string | null = null;
  for (const node of railNodes.value) {
    if (node.kind !== "item") continue;
    if (node.entry.date !== null && node.entry.date === lastDate) {
      ids.add(node.entry.id);
    }
    lastDate = node.entry.date;
  }
  return ids;
});

// Scroll-linked highlight: tracks the page's own scroll (the rail has no inner scrollbox), picks the item closest to a fixed viewport line.
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
}
// The sticky overview widens toward the full viewport width as it approaches
// its sticky point. The gaps to the viewport edge are measured rather than
// derived from vw units, so a scrollbar cannot make the strip overshoot the
// screen and force the page into horizontal scrolling.
function measureGap() {
  const el = overviewEl.value;
  const host = el?.parentElement;
  if (!el || !host) return;
  const r = host.getBoundingClientRect();
  const cs = getComputedStyle(host);
  const viewport = document.documentElement.clientWidth; // without the scrollbar
  el.style.setProperty(
    "--gap-left",
    `${Math.max(0, r.left + parseFloat(cs.paddingLeft))}px`,
  );
  el.style.setProperty(
    "--gap-right",
    `${Math.max(0, viewport - r.right + parseFloat(cs.paddingRight))}px`,
  );
}

const lockEffects =
  typeof window === "undefined"
    ? null
    : window.matchMedia("(max-width: 48rem), (prefers-reduced-motion: reduce)");

let lastWiden = -1;

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}
function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}
function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

// The ramp is only the container width. The strip inside re-fits its own
// scale to whatever width it ends up with (see Timeline.vue), so widening
// spreads the plan out instead of revealing more empty rail to the right.
const WIDEN_DISTANCE = 220; // px of scroll over which the widen ramps up
const PARALLAX_LIFT = 16;
function updateWiden() {
  const el = overviewEl.value;
  if (!el || lockEffects?.matches) return;
  const top = el.getBoundingClientRect().top;
  const raw = clamp01((WIDEN_DISTANCE - top) / WIDEN_DISTANCE);
  const widen = easeInOutCubic(raw);
  // Unter einem halben Prozent sieht niemand etwas, 0 und 1 aber immer
  // schreiben, damit die Endzustände exakt erreicht werden.
  if (Math.abs(widen - lastWiden) < 0.004 && raw > 0 && raw < 1) return;
  lastWiden = widen;
  el.style.setProperty("--widen", widen.toFixed(4));
  el.style.setProperty(
    "--parallax",
    `${((1 - easeOutCubic(raw)) * PARALLAX_LIFT).toFixed(2)}px`,
  );
}
function onPageScroll() {
  if (scrollRaf) return;
  scrollRaf = true;
  requestAnimationFrame(() => {
    scrollRaf = false;
    updateHighlight();
    updateWiden();
  });
}
let gapObserver: ResizeObserver | undefined;
onMounted(() => {
  window.addEventListener("scroll", onPageScroll, { passive: true });
  nextTick(() => {
    measureGap();
    updateHighlight();
    updateWiden();
  });
  const host = overviewEl.value?.parentElement;
  if (!host) return;
  // Re-measures itself after a resize instead of needing its own listener.
  gapObserver = new ResizeObserver(() => {
    measureGap();
    lastWiden = -1;
    updateWiden();
  });
  gapObserver.observe(host);
});
onBeforeUnmount(() => {
  window.removeEventListener("scroll", onPageScroll);
  gapObserver?.disconnect();
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
      <div class="field">
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

    <fieldset v-if="facetOptions.length > 0" class="facets">
      <legend>Trifft auf mich zu</legend>
      <p class="facets-hint">Ergänze deine Situation für weitere Aufgaben.</p>
      <label v-for="id in facetOptions" :key="id" class="facet">
        <input v-model="activeFacets" type="checkbox" :value="id" />
        <span>{{ facetLabel(id) }}</span>
      </label>
    </fieldset>

    <label v-if="hasNoticeRule" class="overlap">
      <input
        type="checkbox"
        :checked="overlapMonths > 0"
        @change="
          overlapMonths = ($event.target as HTMLInputElement).checked ? 1 : 0
        "
      />
      <span>Alte Wohnung einen Monat länger behalten</span>
    </label>

    <template v-if="anchorDate">
      <p v-if="tasks.length > 0" class="progress">
        <span>{{ stats.done }} von {{ tasks.length }} erledigt</span>
        <progress :value="stats.done" :max="tasks.length"></progress>
      </p>
      <div ref="overviewEl" class="overview">
        <div class="overview-inner">
          <Timeline
            :tasks="tasks"
            :anchor-date="anchorDate"
            :anchor-name="anchorLabel"
            :region-code="selected?.regionCode"
            :highlight-date="highlightedDate"
            :hover-id="hoveredId"
            :done-ids="doneIds"
            compact
            @select="onTimelineSelect"
            @hover="hoveredId = $event"
          />
        </div>
      </div>
      <p
        class="scalenote"
        title="Ziehen verschiebt eine Aufgabe, Scrollen hebt den Tag im Zeitstrahl hervor"
      >
        Jeder Kreis ist eine Aufgabe, Klick springt zur Karte. Abstände sind
        maßstäblich.
      </p>
      <p v-if="unverifiedCount > 0" class="verify-note">
        <Info :size="13" />
        <span>
          {{ verifiedCount }} Fristen gesetzlich belegt, {{ unverifiedCount }}
          auf Erfahrungswerten.
          <a :href="sourceIssueUrl" target="_blank" rel="noopener"
            >Quelle vorschlagen</a
          >
        </span>
      </p>
      <div class="rail-column">
        <div ref="railEl" class="rail">
          <template
            v-for="node in railNodes"
            :key="node.kind === 'gap' ? node.id : node.entry.id"
          >
            <div
              v-if="node.kind === 'gap'"
              class="gap"
              :style="{ height: `${node.heightPx}px` }"
            >
              <span
                v-if="node.bufferDays >= BUFFER_LABEL_DAYS"
                class="gap-label"
              >
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
              :editing="editingId === node.entry.id"
              :note-open="openNoteId === node.entry.id"
              :note-text="userNotes[node.entry.id]"
              :attachment-open="openAttachmentId === node.entry.id"
              :attachment-text="attachments[node.entry.id]"
              :has-attachment="node.entry.id in attachments"
              :cta="taskCtaFor(node.entry.id)"
              :show-date="!suppressDate.has(node.entry.id)"
              :date-edit-open="editingDateId === node.entry.id"
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
            <span class="badge missing">Quelle fehlt</span>
          </li>
        </ul>
      </div>

      <div class="actions">
        <div class="actions-buttons">
          <button type="button" @click="exportIcs">
            <Download :size="14" /> Als ICS exportieren
          </button>
          <button type="button" @click="print">
            <Printer :size="14" /> Checkliste drucken
          </button>
        </div>
        <p>
          Auf diesem Gerät gespeichert, im Browser und nicht auf einem Server.
          Auf einem anderen Gerät ist der Plan leer, Konten gibt es noch keine.
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
  /* No calendar sidebar anymore - a single content column doesn't need the
    old two-column width, the sitewide .wrap (62rem) was already clamping
    this down anyway, just leaving dead space on wide screens. */
  max-width: 58rem;
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
  font-size: var(--fs-xs);
  font-weight: 600;
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
  font-size: var(--fs-md);
  font-weight: 600;
}
.field strong {
  display: block;
  font-size: var(--fs-md);
  font-weight: 600;
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
.progress {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin: 0 1rem 0.9rem;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.progress progress {
  flex: 1 1 auto;
  max-width: 14rem;
  height: 0.35rem;
  accent-color: var(--done-color);
}
.overlap {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0 1rem 1rem;
  font-size: var(--fs-sm);
}
.overlap input {
  accent-color: var(--accent);
  margin: 0;
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
  padding: 0.25rem 0.6rem;
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

.overview {
  --widen: 0;
  --parallax: 0px;
  --gap-left: 0px;
  --gap-right: 0px;

  position: sticky;
  top: 0;
  z-index: 5;
  margin: 0 calc(var(--gap-right) * -1 * var(--widen)) 1rem
    calc(var(--gap-left) * -1 * var(--widen));
  padding-inline: calc(0.9rem * var(--widen));
  background: var(--paper);
  box-shadow:
    0 1px 0 var(--line),
    0 calc(6px * var(--widen)) calc(20px * var(--widen))
      color-mix(in srgb, var(--ink) calc(12% * var(--widen)), transparent);
}
.overview-inner {
  transform: translate3d(0, var(--parallax), 0);
  will-change: transform;
}
.scalenote {
  font-size: var(--fs-xs);
  color: var(--muted);
  margin: 0.9rem 0 0.9rem 10.5rem;
}
.verify-note {
  margin: 0 0 0.9rem 10.5rem;
  padding: 0.5rem 0.8rem;
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
  --rail-gap: 1.5rem;
  position: relative;
  margin: 0;
  padding: 0.5rem 0 0.5rem 10.5rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 9rem;
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
  margin-left: -10.5rem;
  padding-left: 10.5rem;
}
.gap-add {
  position: absolute;
  /* Centered on .rail::before's line: 9rem minus half the 1.3rem width. */
  left: 8.35rem;
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
/* Dead time, not a deadline: set back from the card edge and washed out, so
  it can never be mistaken for the date column above it. */
.gap-label {
  position: absolute;
  left: 10.5rem;
  top: 50%;
  transform: translateY(-50%);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: color-mix(in srgb, var(--muted) 70%, transparent);
  border-left: 1px dashed var(--line);
  padding-left: 0.5rem;
  pointer-events: none;
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
.undo {
  margin-top: 0.9rem;
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

@media (max-width: 48rem) {
  .overview {
    --widen: 1 !important;
    --parallax: 0px !important;
  }
}
@media (prefers-reduced-motion: reduce) {
  .overview {
    --widen: 1 !important;
    --parallax: 0px !important;
  }
}
@media (max-width: 32rem) {
  .rail {
    --rail-gap: 1.2rem;
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
  .gap-label {
    left: 1.4rem;
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
  .overview,
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
