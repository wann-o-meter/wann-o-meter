<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import {
  ArrowUpRight,
  CalendarClock,
  Check,
  MessageSquarePlus,
  Pencil,
  Trash2,
  TriangleAlert,
} from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { shortDate } from "../../../lib/date-display";
import CardMenu from "./CardMenu.vue";
import TaskDates from "./TaskDates.vue";
import TaskFooter from "./TaskFooter.vue";
import type { EditorKind, MenuItem, TaskPatch } from "./task-card";
import type { TaskCta } from "./task-cta";

const props = defineProps<{
  entry: ScheduleEntry;
  anchorDate: string; // the plan's own day, needed to size the tenancy overlap
  isPast: boolean;
  done: boolean;
  isCustom: boolean;
  isNext: boolean; // the one task to act on now
  deferred: boolean; // the rule's target month was pushed back by a month
  cta: TaskCta | null;
  note?: string;
  attachment?: string;
  /** Which inline editor is open, if any. Owned by the parent so only one
    card in the list can be editing at a time; v-model:editor. */
  editor: EditorKind | null;
}>();

const emit = defineEmits<{
  (e: "update:editor", value: EditorKind | null): void;
  (e: "update", patch: TaskPatch): void;
  (e: "toggle-done"): void;
  (e: "toggle-defer"): void;
  (e: "delete"): void;
}>();

/* ---------- editors: one open/close path, one commit path ---------- */

function open(kind: EditorKind) {
  emit("update:editor", kind);
}
function close() {
  emit("update:editor", null);
}
function currentValue(field: EditorKind) {
  if (field === "label") return props.entry.label ?? "";
  if (field === "date") return props.entry.date ?? "";
  if (field === "note") return props.note ?? "";
  return props.attachment ?? "";
}
function commit(field: EditorKind, value: string) {
  if (value !== currentValue(field)) emit("update", { [field]: value });
  close();
}

// Only one editor is mounted at a time, so a single ref covers all four and
// the parent no longer has to reach into the DOM to focus them.
const editorEl = ref<HTMLElement | null>(null);
watch(
  () => props.editor,
  async (kind) => {
    if (!kind) return;
    await nextTick();
    editorEl.value?.focus();
  },
);

// note and attachment are the same textarea with different copy.
const textEditor = computed(() => {
  if (props.editor === "note")
    return {
      field: "note" as const,
      value: props.note ?? "",
      rows: 2,
      placeholder: "Notiz - z. B. Aktenzeichen, Ansprechpartner, Telefonnummer",
    };
  if (props.editor === "attachment")
    return {
      field: "attachment" as const,
      value: props.attachment ?? "",
      rows: 10,
      placeholder: "",
    };
  return null;
});

// A touch date wheel fires change on every spin, and committing re-renders the
// rail under the open picker. So the date is parked and applied on close.
const pendingDate = ref("");
function parkDate(e: Event) {
  const el = e.target as HTMLInputElement;
  pendingDate.value = el.value;
  // A pointer picker closes on selection, so it can commit at once.
  if (matchMedia("(hover: hover)").matches) el.blur();
}
function closeDateEdit() {
  const iso = pendingDate.value;
  pendingDate.value = "";
  if (iso) commit("date", iso);
  else close();
}

/* ---------- derived state ---------- */

// Same three states the markers on the timeline use, same colours.
const status = computed(() =>
  props.done ? "erledigt" : props.isPast ? "ueberfaellig" : "offen",
);

// Both dates are already on the card, the gap between them is not. Only worth
// a line when the tenancy outlives the moving month itself, otherwise every
// mid-month move would report the remainder of its own month as a finding.
const doubleRent = computed(() => {
  const lease = props.entry.leaseEnd;
  if (!lease || lease.overlapDays <= 0) return null;
  if (lease.date.slice(0, 7) === props.anchorDate.slice(0, 7)) return null;
  const weeks = Math.round(lease.overlapDays / 7);
  const span =
    lease.overlapDays < 14 ? `${lease.overlapDays} Tage` : `${weeks} Wochen`;
  return { end: shortDate(lease.date), span };
});

const menuItems = computed<MenuItem[]>(() => [
  {
    label: "Termin verschieben",
    icon: CalendarClock,
    onSelect: () => open("date"),
  },
  { label: "Titel ändern", icon: Pencil, onSelect: () => open("label") },
  { label: "Notiz", icon: MessageSquarePlus, onSelect: () => open("note") },
  {
    label: "Aufgabe entfernen",
    icon: Trash2,
    danger: true,
    onSelect: () => emit("delete"),
  },
]);
</script>

<template>
  <article
    class="card"
    :data-entry-id="entry.id"
    :data-entry-date="entry.date"
    :data-status="status"
  >
    <div class="head">
      <span class="dot" :data-dot-key="entry.id"></span>
      <button
        type="button"
        class="check"
        :aria-pressed="done"
        :aria-label="`${entry.label} als erledigt markieren`"
        @click="$emit('toggle-done')"
      >
        <Check v-if="done" :size="11" />
      </button>
      <input
        v-if="editor === 'label'"
        ref="editorEl"
        class="title-input"
        :value="entry.label"
        placeholder="Was ist zu tun?"
        @keydown.enter="($event.target as HTMLInputElement).blur()"
        @blur="commit('label', ($event.target as HTMLInputElement).value)"
      />
      <h3 v-else>
        {{ entry.label }}
        <span v-if="isPast && !done" class="badge late">Überfällig</span>
        <span v-else-if="isNext && !done" class="badge">Als Nächstes</span>
      </h3>
      <CardMenu :items="menuItems" />
    </div>

    <TaskDates
      :entry="entry"
      :is-past="isPast"
      :done="done"
      :show-rescue-label="!doubleRent"
    />

    <input
      v-if="editor === 'date'"
      ref="editorEl"
      type="date"
      class="date-input"
      :value="entry.date"
      aria-label="Datum ändern"
      @change="parkDate"
      @blur="closeDateEdit"
      @keydown.enter="($event.target as HTMLInputElement).blur()"
    />

    <p v-if="doubleRent && !done" class="overlap">
      Mietende {{ doubleRent.end }}, {{ doubleRent.span }} nach dem Umzug. So
      lange läuft die Miete für beide Wohnungen.
    </p>

    <p v-if="!done && entry.impossible" class="flag">
      <TriangleAlert :size="14" /> Bei diesem Termin nicht mehr rechtzeitig
      möglich – Termin sofort buchen.
    </p>
    <p v-else-if="entry.movedFrom && !done" class="moved">
      {{ shortDate(entry.movedFrom) }} wäre ein geschlossener Tag, deshalb der
      nächste Werktag.
    </p>

    <!-- An expired card keeps only the line that says what to do now. -->
    <p v-if="entry.note && !entry.rescue" class="hint">{{ entry.note }}</p>

    <textarea
      v-if="textEditor"
      ref="editorEl"
      class="note-input"
      :value="textEditor.value"
      :rows="textEditor.rows"
      :placeholder="textEditor.placeholder"
      @keydown.esc="($event.target as HTMLTextAreaElement).blur()"
      @blur="
        commit(textEditor.field, ($event.target as HTMLTextAreaElement).value)
      "
    ></textarea>
    <p
      v-else-if="note"
      class="note"
      tabindex="0"
      role="button"
      @click="open('note')"
      @keydown.enter="open('note')"
    >
      {{ note }}
    </p>

    <div v-if="cta" class="cta-row">
      <a
        v-if="cta.kind === 'link'"
        class="cta-link"
        :href="cta.url"
        target="_blank"
        rel="noopener"
        >{{ cta.label }} <ArrowUpRight :size="14"
      /></a>
      <button
        v-else
        type="button"
        class="cta-button"
        @click="open('attachment')"
      >
        {{ attachment ? `${cta.label} bearbeiten` : `${cta.label} aufsetzen` }}
      </button>
    </div>

    <TaskFooter
      :entry="entry"
      :is-custom="isCustom"
      :deferred="deferred"
      @toggle-defer="$emit('toggle-defer')"
    />
  </article>
</template>

<style scoped>
.card {
  position: relative;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-left: 4px solid var(--line);
  border-radius: var(--radius);
  padding: 0.9rem 1.1rem;
  margin-bottom: 0.6rem;
  scroll-margin-top: calc(var(--tl-header-h, 0px) + 1rem);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}
/* The dot sits on the rail line to the left of the card, anchored to the
  title row so an eyebrow above it cannot push the two out of line. Filled and
  small on purpose: the hollow ring is the timeline's state glyph, and the rail
  is spaced by list order, not by date. Card padding is part of the offset,
  since the row it hangs on starts inside it. */
.dot {
  position: absolute;
  left: calc(-1 * var(--rail-gap, 1.4rem) - 1.1rem - 0.25rem);
  top: 0.5rem;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--line);
  border: 0;
}
.card[data-status="erledigt"] .dot {
  background: var(--done-color);
}
.card[data-status="ueberfaellig"] .dot {
  background: var(--warn);
}

.card[data-status="offen"] {
  border-left-color: var(--accent);
}
.card[data-status="erledigt"] {
  border-left-color: var(--done-color);
  opacity: 0.7;
}
.card[data-status="ueberfaellig"] {
  border-left-color: var(--warn);
}
.card.focused,
.card.current {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent);
}
.card[data-status="erledigt"] .hint,
.card[data-status="erledigt"] .cta-row,
.card[data-status="erledigt"] :deep(.footer) {
  display: none;
}
.card[data-status="erledigt"] h3 {
  text-decoration: line-through;
  color: var(--muted);
}

/* State rides along with the title instead of costing a line above it. */
.badge {
  display: inline-block;
  vertical-align: 0.1em;
  margin-left: 0.4rem;
  padding: 0.05rem 0.4rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 12%, var(--paper-raised));
  color: var(--accent);
  font-size: var(--fs-xs);
  font-weight: 600;
  white-space: nowrap;
}
.badge.late {
  background: color-mix(in srgb, var(--warn) 12%, var(--paper-raised));
  color: var(--warn);
}

.head {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}
.head h3,
.title-input {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: var(--fs-md);
}
.title-input {
  font-family: inherit;
  font-weight: 600;
  color: inherit;
  border: 1px solid var(--accent);
  border-radius: 2px;
  padding: 0.25rem 0.5rem;
  background: var(--paper);
}
.check {
  position: relative;
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  margin-top: 0.15rem;
  border: 1px solid var(--line);
  background: var(--paper);
  /* A rounded square, not a circle: circles on this page mean timeline state,
    and a bare grey one next to a title read as one of them. */
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--paper);
}
.check[aria-pressed="true"] {
  background: var(--done-color);
  border-color: var(--done-color);
}
@media (max-width: 40rem) {
  .check::before {
    content: "";
    position: absolute;
    inset: -0.55rem;
  }
}

/* The menu is quiet until the card is under the pointer. */
:deep(.tools) {
  opacity: 0;
}
.card:hover :deep(.tools),
:deep(.tools[open]),
:deep(.tools:focus-within) {
  opacity: 1;
}
@media (hover: none) {
  :deep(.tools) {
    opacity: 1;
  }
}

.hint {
  margin: 0.5rem 0 0;
  max-width: 68ch;
  font-size: var(--fs-sm);
}
.moved {
  margin: 0.35rem 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
/* A consequence of the plan, not a warning about it, so it carries no colour
  and no bar of its own. */
.overlap {
  margin: 0.4rem 0 0;
  max-width: 60ch;
  font-size: var(--fs-sm);
}
.flag {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.5rem 0 0;
  color: var(--warn);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.cta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.6rem;
}
.cta-link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--accent);
  font-size: var(--fs-sm);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
/* The one thing the card asks you to do, so it is the one filled control. */
.cta-button {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--fs-sm);
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}

.note-input,
.date-input {
  font-family: inherit;
  font-size: var(--fs-sm);
  color: inherit;
  border-radius: 2px;
  background: var(--paper);
}
.note-input {
  display: block;
  width: 100%;
  margin-top: 0.5rem;
  border: 1px solid var(--line);
  padding: 0.5rem;
  resize: vertical;
}
.date-input {
  display: block;
  margin-top: 0.5rem;
  border: 1px solid var(--accent);
  padding: 0.25rem 0.5rem;
}
.note {
  margin: 0.5rem 0 0;
  padding: 0.5rem;
  background: color-mix(in srgb, var(--accent) 6%, var(--paper-raised));
  border-left: 2px solid var(--line);
  font-size: var(--fs-sm);
  white-space: pre-wrap;
  cursor: text;
}

@media print {
  .cta-row {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
