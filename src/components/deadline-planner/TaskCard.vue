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
  anchorDate: string;
  isPast: boolean;
  done: boolean;
  isCustom: boolean;
  deferred: boolean;
  cta: TaskCta | null;
  note?: string;
  attachment?: string;
  editor: EditorKind | null;
}>();

const emit = defineEmits<{
  (e: "update:editor", value: EditorKind | null): void;
  (e: "update", patch: TaskPatch): void;
  (e: "toggle-done"): void;
  (e: "toggle-defer"): void;
  (e: "delete"): void;
}>();

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

const editorEl = ref<HTMLElement | null>(null);
watch(
  () => props.editor,
  async (kind) => {
    if (!kind) return;
    await nextTick();
    editorEl.value?.focus();
  },
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

const pendingDate = ref("");
function parkDate(e: Event) {
  const el = e.target as HTMLInputElement;
  pendingDate.value = el.value;
  if (matchMedia("(hover: hover)").matches) el.blur();
}
function closeDateEdit() {
  const iso = pendingDate.value;
  pendingDate.value = "";
  if (iso) commit("date", iso);
  else close();
}

const status = computed(() =>
  props.done ? "erledigt" : props.isPast ? "ueberfaellig" : "offen",
);

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
        {{ cta.label }} aufsetzen
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
  padding: 0.5rem;
  margin-bottom: 1.3rem;
  background: var(--paper-raised);
  border-radius: var(--radius);
  box-shadow: var(--shadow-card);
  scroll-margin-top: calc(var(--tl-header-h, 0px) + 1rem);
  transition: box-shadow 0.2s;
}
.dot {
  position: absolute;
  left: var(--dot-x, -1.5rem);
  top: 0.8rem;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--accent);
  border: 0;
}
.card[data-status="erledigt"] .dot {
  background: var(--done-color);
}
.card[data-status="ueberfaellig"] .dot {
  background: var(--warn);
}

.card[data-status="erledigt"] {
  opacity: 0.7;
}
@media (hover: hover) {
  .card:hover {
    box-shadow: var(--shadow-md);
  }
}
.card.focused {
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--accent) 60%, transparent),
    var(--shadow-md);
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

.badge {
  display: inline-block;
  vertical-align: 0.1em;
  margin-left: 0.5rem;
  color: var(--accent);
  font-size: var(--fs-xs);
  font-weight: 600;
  white-space: nowrap;
}
.badge.late {
  color: var(--warn);
}

.head {
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
  border-radius: var(--radius-sm);
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
  border-radius: 50%;
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
.check::before {
  content: "";
  position: absolute;
  inset: -0.6rem;
}

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

.hint,
.overlap {
  margin: 0.5rem 0 0;
  max-width: 68ch;
  font-size: var(--fs-sm);
}
.moved {
  margin: 0.35rem 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
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
  min-height: 2.6rem;
  color: var(--accent);
  font-size: var(--fs-sm);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
.cta-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  width: 100%;
  min-height: 2.6rem;
  font-size: var(--fs-sm);
  font-weight: 600;
  background: transparent;
  border-color: var(--accent);
  color: var(--accent);
}
.cta-button:hover {
  background: color-mix(in srgb, var(--accent) 10%, transparent);
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

.note-input,
.date-input {
  font-family: inherit;
  font-size: var(--fs-sm);
  color: inherit;
  border-radius: var(--radius-sm);
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
  max-width: 68ch;
  font-size: var(--fs-sm);
  color: var(--muted);
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
