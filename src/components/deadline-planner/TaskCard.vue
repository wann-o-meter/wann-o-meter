<script setup lang="ts">
import { computed, ref } from "vue";
import {
  ArrowUpRight,
  CalendarClock,
  Check,
  Ellipsis,
  MessageSquarePlus,
  Pencil,
  Trash2,
  TriangleAlert,
} from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { MONTH_NAMES, WEEKDAY_NAMES_SHORT } from "../../../lib/date-display";
import { toDate } from "../../../lib/format-date";
import { sourceLabel } from "../../../lib/offset-label";
import type { TaskCta } from "./task-cta";

const props = defineProps<{
  entry: ScheduleEntry;
  isPast: boolean;
  done: boolean;
  isCustom: boolean;
  editing: boolean; // title input open
  noteOpen: boolean;
  noteText?: string;
  attachmentOpen: boolean;
  attachmentText?: string;
  hasAttachment: boolean;
  cta: TaskCta | null;
  dateEditOpen: boolean;
  isNext: boolean; // the one task to act on now
  deferred: boolean; // the rule's target month was pushed back by a month
}>();

const emit = defineEmits<{
  (e: "toggle-done"): void;
  (e: "commit-label", value: string): void;
  (e: "open-label-edit"): void;
  (e: "open-note"): void;
  (e: "commit-note", value: string): void;
  (e: "open-attachment"): void;
  (e: "commit-attachment", value: string): void;
  (e: "delete"): void;
  (e: "open-date-edit"): void;
  (e: "close-date-edit"): void;
  (e: "toggle-defer"): void;
  (e: "commit-date-edit", iso: string): void;
}>();

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
  if (iso) emit("commit-date-edit", iso);
  else emit("close-date-edit");
}

function when(iso: string): string {
  const d = toDate(iso);
  return `${WEEKDAY_NAMES_SHORT[(d.getUTCDay() + 6) % 7]}, ${String(d.getUTCDate()).padStart(2, "0")}.${String(d.getUTCMonth() + 1).padStart(2, "0")}.${d.getUTCFullYear()}`;
}
function shortWhen(iso: string): string {
  const d = toDate(iso);
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()].slice(0, 3)}`;
}

// Same three states the markers on the timeline use, same colours.
const status = computed(() =>
  props.done ? "erledigt" : props.isPast ? "ueberfaellig" : "offen",
);

// A <details> menu has no outside-click of its own, so it closes when an item
// is used or when focus leaves it.
function closeMenu(e: Event) {
  const menu = e.currentTarget as HTMLDetailsElement;
  if ((e.target as HTMLElement).closest("button")) menu.open = false;
}
function closeMenuOnBlur(e: FocusEvent) {
  const menu = e.currentTarget as HTMLDetailsElement;
  if (!menu.contains(e.relatedTarget as Node)) menu.open = false;
}
</script>

<template>
  <article
    class="card"
    :data-entry-id="entry.id"
    :data-entry-date="entry.date"
    :data-status="status"
  >
    <span class="dot" :data-dot-key="entry.id"></span>
    <p v-if="isNext && !done" class="eyebrow">Als Nächstes</p>

    <div class="head">
      <button
        type="button"
        class="check"
        :aria-pressed="done"
        aria-label="Als erledigt markieren"
        @click="$emit('toggle-done')"
      >
        <Check v-if="done" :size="11" />
      </button>
      <input
        v-if="editing"
        class="title-input"
        :data-title-input="entry.id"
        :value="entry.label"
        placeholder="Was ist zu tun?"
        @keydown.enter="
          $emit('commit-label', ($event.target as HTMLInputElement).value)
        "
        @blur="$emit('commit-label', ($event.target as HTMLInputElement).value)"
      />
      <h3 v-else>{{ entry.label }}</h3>
      <details class="tools" @click="closeMenu" @focusout="closeMenuOnBlur">
        <summary aria-label="Aktionen" title="Aktionen">
          <Ellipsis :size="14" />
        </summary>
        <div class="tool-menu">
          <button type="button" @click="$emit('open-date-edit')">
            <CalendarClock :size="12" /> Termin verschieben
          </button>
          <button type="button" @click="$emit('open-label-edit')">
            <Pencil :size="12" /> Titel ändern
          </button>
          <button type="button" @click="$emit('open-note')">
            <MessageSquarePlus :size="12" /> Notiz
          </button>
          <button type="button" class="danger" @click="$emit('delete')">
            <Trash2 :size="12" /> Aufgabe entfernen
          </button>
        </div>
      </details>
    </div>

    <p class="dates">
      <span :class="{ overdue: isPast }">Frist: {{ when(entry.date!) }}</span>
      <template v-if="entry.earliestDate !== entry.date">
        &nbsp;·&nbsp; möglich ab: {{ when(entry.earliestDate!) }}</template
      >
      <template v-if="entry.startByDate !== entry.date">
        &nbsp;·&nbsp; <b>Termin buchen bis: {{ when(entry.startByDate!) }}</b>
      </template>
    </p>

    <input
      v-if="dateEditOpen"
      type="date"
      class="date-input"
      :value="entry.date"
      aria-label="Datum ändern"
      @change="parkDate"
      @blur="closeDateEdit"
      @keydown.enter="($event.target as HTMLInputElement).blur()"
    />

    <p v-if="entry.rescue" class="flag rescue">
      <TriangleAlert :size="14" /> Frist verstrichen - bis
      {{ shortWhen(entry.rescue.date) }} nachholen, {{ entry.rescue.label }}.
    </p>
    <p v-if="!done && entry.impossible" class="flag">
      Bei diesem Termin nicht mehr rechtzeitig möglich - Termin sofort buchen.
    </p>
    <p v-else-if="entry.movedFrom && !done" class="moved">
      {{ shortWhen(entry.movedFrom) }} wäre ein geschlossener Tag, deshalb der
      nächste Werktag.
    </p>

    <!-- An expired card keeps only the line that says what to do now. -->
    <p v-if="entry.note && !entry.rescue" class="hint">{{ entry.note }}</p>

    <p v-if="entry.offset_rule || deferred" class="defer">
      <span class="defer-label">Mietende</span>
      <button
        type="button"
        :aria-pressed="!deferred"
        @click="deferred && $emit('toggle-defer')"
      >
        Ende des Umzugsmonats
      </button>
      <button
        type="button"
        :aria-pressed="deferred"
        @click="!deferred && $emit('toggle-defer')"
      >
        Einen Monat später (Überlappung)
      </button>
    </p>

    <details v-if="entry.derivation?.length" class="derivation">
      <summary>Wie berechnet?</summary>
      <ol>
        <li v-for="step in entry.derivation" :key="step.step">
          {{ step.label }}
        </li>
      </ol>
    </details>

    <textarea
      v-if="attachmentOpen"
      class="note-input"
      :data-attachment-input="entry.id"
      :value="attachmentText ?? ''"
      rows="10"
      @keydown.esc="
        $emit('commit-attachment', ($event.target as HTMLTextAreaElement).value)
      "
      @blur="
        $emit('commit-attachment', ($event.target as HTMLTextAreaElement).value)
      "
    ></textarea>

    <textarea
      v-if="noteOpen"
      class="note-input"
      :data-note-input="entry.id"
      :value="noteText ?? ''"
      rows="2"
      placeholder="Notiz - z. B. Aktenzeichen, Ansprechpartner, Telefonnummer"
      @keydown.esc="
        $emit('commit-note', ($event.target as HTMLTextAreaElement).value)
      "
      @blur="$emit('commit-note', ($event.target as HTMLTextAreaElement).value)"
    ></textarea>
    <p
      v-else-if="noteText"
      class="note"
      tabindex="0"
      role="button"
      @click="$emit('open-note')"
      @keydown.enter="$emit('open-note')"
    >
      {{ noteText }}
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
        @click="$emit('open-attachment')"
      >
        {{
          hasAttachment ? `${cta.label} bearbeiten` : `${cta.label} aufsetzen`
        }}
      </button>
    </div>

    <p class="src">
      Grundlage:
      <a
        v-if="entry.source_url"
        :href="entry.source_url"
        target="_blank"
        rel="noopener"
        >{{ entry.source_label ?? "Quelle" }}</a
      >
      <span v-else>{{ isCustom ? "Eigene Aufgabe" : sourceLabel(entry) }}</span>
    </p>
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
/* The dot sits on the rail line to the left of the card, and both it and the
  card edge carry the same three states as the markers on the timeline. */
.dot {
  position: absolute;
  left: calc(-1 * var(--rail-gap, 1.4rem) - 0.6rem);
  top: 1.05rem;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  background: var(--paper);
  border: 2px solid var(--accent);
}
.card[data-status="erledigt"] .dot {
  background: var(--done-color);
  border-color: var(--done-color);
}
.card[data-status="ueberfaellig"] .dot {
  border-color: var(--warn);
}

.card[data-status="offen"] {
  border-left-color: var(--accent);
}
.card[data-status="erledigt"] {
  border-left-color: var(--done-color);
}
.card[data-status="ueberfaellig"] {
  border-left-color: var(--warn);
}
.card.focused,
.card.current {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent);
}
.card[data-status="erledigt"] {
  opacity: 0.7;
}
.card[data-status="erledigt"] .hint,
.card[data-status="erledigt"] .defer,
.card[data-status="erledigt"] .derivation,
.card[data-status="erledigt"] .cta-row,
.card[data-status="erledigt"] .src {
  display: none;
}
.card[data-status="erledigt"] h3 {
  text-decoration: line-through;
  color: var(--muted);
}

.eyebrow {
  margin: 0 0 0.15rem;
  font-size: var(--fs-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
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
@media (max-width: 40rem) {
  .check::before {
    content: "";
    position: absolute;
    inset: -0.55rem;
  }
}

.tools {
  position: relative;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s;
}
.card:hover .tools,
.tools[open],
.tools:focus-within {
  opacity: 1;
}
@media (hover: none) {
  .tools {
    opacity: 1;
  }
}
.tools summary {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid transparent;
  border-radius: 2px;
  cursor: pointer;
  color: var(--muted);
  list-style: none;
}
.tools summary::-webkit-details-marker {
  display: none;
}
.tools summary:hover,
.tools[open] summary {
  background: var(--paper);
  border-color: var(--line);
  color: var(--ink);
}
.tool-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 0.25rem);
  z-index: 4;
  display: flex;
  flex-direction: column;
  min-width: 12rem;
  padding: 0.25rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
}
.tool-menu button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: var(--fs-sm);
  text-align: left;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
}
.tool-menu button:hover {
  background: var(--paper);
}
.tool-menu .danger {
  color: var(--warn);
}

.dates {
  margin: 0.35rem 0 0;
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--muted);
}
.dates b {
  color: var(--ink);
  font-weight: 600;
}
.dates .overdue {
  text-decoration: line-through;
}
.hint {
  margin: 0.5rem 0 0;
  max-width: 68ch;
  font-size: var(--fs-sm);
}
.src {
  margin: 0.5rem 0 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.src a {
  color: var(--accent);
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

.defer {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0.25rem;
  margin: 0.5rem 0 0;
}
.defer-label {
  flex-shrink: 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.defer button {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--fs-xs);
  padding: 0.25rem 0.5rem;
}
.defer button[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.derivation {
  margin-top: 0.5rem;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.derivation summary {
  cursor: pointer;
  color: var(--accent);
}
.derivation ol {
  margin: 0.5rem 0 0;
  padding-left: 1.5rem;
}
.derivation li {
  margin-bottom: 0.25rem;
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
.cta-button {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--fs-xs);
  color: var(--accent);
  border-color: var(--accent);
}
.note-input {
  display: block;
  width: 100%;
  margin-top: 0.5rem;
  font-family: inherit;
  font-size: var(--fs-sm);
  color: inherit;
  border: 1px solid var(--line);
  border-radius: 2px;
  padding: 0.5rem;
  background: var(--paper);
  resize: vertical;
}
.date-input {
  display: block;
  margin-top: 0.5rem;
  font-family: inherit;
  font-size: var(--fs-sm);
  color: inherit;
  border: 1px solid var(--accent);
  border-radius: 2px;
  padding: 0.25rem 0.5rem;
  background: var(--paper);
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
  .tools,
  .cta-row {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
