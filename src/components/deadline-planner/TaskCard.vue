<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import {
  ArrowUpRight,
  Check,
  EyeOff,
  MessageSquarePlus,
  Pencil,
  TriangleAlert,
} from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { daysUntil, shortDate } from "../../../lib/date-display";
import { sourceLabel } from "../../../lib/offset-label";
import { isoToday } from "../../../lib/today";
import CardMenu from "./CardMenu.vue";
import TaskDates from "./TaskDates.vue";
import TaskFooter from "./TaskFooter.vue";
import type { EditorKind, MenuItem, TaskPatch } from "./task-card";
import type { TaskCta } from "./task-cta";

const props = defineProps<{
  entry: ScheduleEntry;
  anchorDate: string;
  anchorLabel: string;
  isPast: boolean;
  done: boolean;
  isCustom: boolean;
  cta: TaskCta | null;
  note?: string;
  attachment?: string;
  editor: EditorKind | null;
}>();

// A soft task is recommended, not owed: it names a window, never a Frist.
const undated = computed(() => props.entry.kind === "soft");

const emit = defineEmits<{
  (e: "update:editor", value: EditorKind | null): void;
  (e: "update", patch: TaskPatch): void;
  (e: "toggle-done"): void;
  (e: "hide"): void;
}>();

function open(kind: EditorKind) {
  emit("update:editor", kind);
}
function close() {
  emit("update:editor", null);
}
function currentValue(field: EditorKind) {
  if (field === "label") return props.entry.label ?? "";
  if (field === "note") return props.note ?? "";
  return props.attachment ?? "";
}
function commit(field: EditorKind, value: string) {
  if (value !== currentValue(field)) emit("update", { [field]: value });
  close();
}

const editorEl = ref<HTMLElement | null>(null);
watch(
  () => props.editor,
  async (kind) => {
    if (!kind) return;
    await nextTick();
    editorEl.value?.focus();
  },
  // A blank custom task opens its title editor before the card mounts.
  { immediate: true },
);

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

const status = computed(() => {
  if (props.done) return "erledigt";
  if (undated.value) return "empfohlen";
  if (props.isPast) return "ueberfaellig";
  // The rail is the only place urgency is said, so the row carries no pill
  // repeating what the status block above already counts.
  return daysUntil(props.entry.date!, isoToday()) <= 14 ? "demnaechst" : "offen";
});

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
  // Only a custom task can be renamed: a Frist from the plan carries its
  // Grundlage, and a free title would no longer match it.
  ...(props.isCustom
    ? [{ label: "Titel ändern", icon: Pencil, onSelect: () => open("label") }]
    : []),
  { label: "Notiz", icon: MessageSquarePlus, onSelect: () => open("note") },
  {
    label: "Nicht relevant für mich",
    icon: EyeOff,
    onSelect: () => emit("hide"),
  },
]);
</script>

<template>
  <article
    class="row"
    :data-entry-id="entry.id"
    :data-entry-date="entry.date"
    :data-status="status"
    :data-dot-key="undated ? null : entry.id"
  >
    <div class="head">
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
        aria-label="Aufgabe umbenennen"
        placeholder="Was ist zu tun?"
        @keydown.enter="($event.target as HTMLInputElement).blur()"
        @blur="commit('label', ($event.target as HTMLInputElement).value)"
      />
      <h3 v-else class="t-title">{{ entry.label }}</h3>
      <!-- Everything that says what kind of Frist this is, in one corner. -->
      <span class="marks">
        <span v-if="entry.needs_office" class="pill">Amtstermin</span>
        <span v-if="!undated && isPast && !done" class="pill danger">
          überfällig
        </span>
        <a
          v-if="entry.source_url"
          class="pill source"
          :href="entry.source_url"
          target="_blank"
          rel="noopener"
          >{{ sourceLabel(entry) }} <ArrowUpRight :size="11" /></a
        >
      </span>
      <CardMenu :items="menuItems" />
    </div>

    <TaskDates
      :entry="entry"
      :anchor-label="anchorLabel"
      :is-past="isPast"
      :done="done"
    />

    <p v-if="!done && entry.impossible" class="flag">
      <TriangleAlert :size="14" /> Bei diesem Termin nicht mehr rechtzeitig
      möglich – Termin sofort buchen.
    </p>
    <p v-else-if="entry.movedFrom && !done" class="moved">
      {{ shortDate(entry.movedFrom) }} wäre ein geschlossener Tag, deshalb der
      nächste Werktag.
    </p>

    <p v-if="entry.note && !entry.rescue" class="hint t-body">{{ entry.note }}</p>

    <textarea
      v-if="textEditor"
      ref="editorEl"
      class="note-input"
      :aria-label="textEditor.placeholder || 'Notiz'"
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
        {{ cta.label }} aufsetzen
      </button>
    </div>

    <TaskFooter
      v-if="!undated"
      :entry="entry"
      :anchor-date="anchorDate"
      :is-custom="isCustom"
    />
  </article>
</template>

<style scoped>
/* A row in one list. The left rail is the only thing that changes with the
state of the task: how soon it is due, and whether it is the one in view. */
.row {
  position: relative;
  padding: var(--s-2) var(--s-2) var(--s-2) calc(var(--s-2) - 3px);
  border-left: 3px solid var(--line);
  scroll-margin-top: calc(var(--tl-header-h, 0px) + 1rem);
  transition: background 0.15s;
}
.row + .row {
  border-top: 1px solid var(--line);
}
.row[data-status="ueberfaellig"] {
  border-left-color: var(--overdue);
}
.row[data-status="demnaechst"] {
  border-left-color: var(--due-soon);
}
.row[data-status="empfohlen"] {
  border-left-color: transparent;
}
.row.focused {
  border-left-color: var(--accent);
  background: var(--tint-accent);
}

.head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--s-1);
}
/* Top right, and it stays there: the title takes the rest of the line and
wraps under the marks rather than pushing them off it. */
.marks {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.3rem;
  margin-left: auto;
}
/* The one pill you can click, so it takes the arrow every link that leaves the
site takes. No second pill shape, only the link affordance on the first. */
.pill.source {
  gap: 0.2rem;
  text-decoration: none;
}
.pill.source:hover {
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.head h3,
.title-input {
  flex: 1;
  min-width: 0;
  margin: 0;
}
.title-input {
  font-family: inherit;
  font-size: var(--t-title);
  font-weight: var(--fw-semibold);
  color: inherit;
  border: 1px solid var(--accent);
  border-radius: var(--r-sm);
  padding: 0.25rem 0.5rem;
  background: var(--paper);
}
.check {
  position: relative;
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  margin-top: 0.2rem;
  border: 1px solid var(--line-strong);
  background: var(--paper);
  border-radius: 50%;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--paper);
}
.check[aria-pressed="true"] {
  background: var(--done);
  border-color: var(--done);
}
.check::before {
  content: "";
  position: absolute;
  inset: -0.6rem;
}

:deep(.tools) {
  opacity: 0;
}
.row:hover :deep(.tools),
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
  margin: var(--s-1) 0 0;
  max-width: 68ch;
}
.moved {
  margin: 0.35rem 0 0;
  font-size: var(--t-meta);
  color: var(--muted);
}
.flag {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: var(--s-1) 0 0;
  color: var(--overdue);
  font-size: var(--t-meta);
  font-weight: var(--fw-semibold);
}

.cta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--s-1);
  margin-top: var(--s-1);
}
.cta-link,
.cta-button {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: var(--t-meta);
}
.cta-link {
  min-height: 2.6rem;
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
/* Secondary: this is an action, and it is not the page's one action. */
.cta-button {
  justify-content: center;
  width: 100%;
  min-height: 2.6rem;
  border: 1px solid var(--line-strong);
  border-radius: var(--r-sm);
  font-weight: var(--fw-semibold);
  background: transparent;
  color: var(--ink);
}
.cta-button:hover {
  border-color: var(--accent);
  color: var(--accent);
}
@media (min-width: 40rem) {
  .cta-button {
    width: auto;
    min-height: 0;
  }
  .cta-link {
    min-height: 0;
  }
}

.note-input {
  display: block;
  width: 100%;
  margin-top: var(--s-1);
  padding: var(--s-1);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--paper);
  font-family: inherit;
  font-size: var(--t-meta);
  color: inherit;
  resize: vertical;
}
.note {
  margin: var(--s-1) 0 0;
  max-width: 68ch;
  font-size: var(--t-meta);
  color: var(--muted);
  white-space: pre-wrap;
  cursor: text;
}

@media print {
  .cta-row {
    display: none;
  }
  .row {
    break-inside: avoid;
    padding: 0.4rem 0;
    border-left: 0;
    border-bottom: 1px solid #bbb;
  }
  .row.focused {
    background: none;
  }
  .check {
    border-color: #000;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .hint,
  .note {
    color: #333;
  }
}
</style>
