<script setup lang="ts">
import { Check, Pencil, X } from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { MONTH_NAMES, WEEKDAY_NAMES_LONG } from "../../../lib/date-display";
import { toDate } from "../../../lib/format-date";
import type { TaskCta } from "./task-cta";

const props = defineProps<{
  entry: ScheduleEntry;
  anchorLabel: string; // "Umzugstag" etc - also the offset-0 label
  isAnchor: boolean;
  isPast: boolean;
  done: boolean;
  isCustom: boolean;
  dragging: boolean;
  editing: boolean; // title input open
  noteOpen: boolean;
  noteText?: string;
  attachmentOpen: boolean;
  attachmentText?: string;
  hasAttachment: boolean;
  cta: TaskCta | null;
}>();

defineEmits<{
  (e: "toggle-done"): void;
  (e: "commit-label", value: string): void;
  (e: "open-note"): void;
  (e: "commit-note", value: string): void;
  (e: "open-attachment"): void;
  (e: "commit-attachment", value: string): void;
  (e: "delete"): void;
  (e: "dragstart", event: DragEvent): void;
  (e: "dragend"): void;
}>();

// Full "17. Juni 2026" / "Mittwoch" instead of the compact format - the rail
// has room, reads less like a table row.
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
</script>

<template>
  <div
    class="item"
    :data-entry-id="entry.id"
    :data-entry-date="entry.date"
    :draggable="!isAnchor"
    :class="{ anchor: isAnchor, past: isPast, done, dragging }"
    @dragstart="!isAnchor && $emit('dragstart', $event)"
    @dragend="$emit('dragend')"
  >
    <span class="dot"></span>
    <div class="when">
      <b>{{ whenDate(entry.date!) }}</b>
      <span>{{ weekdayName(entry.date!) }} · {{ offsetLabel(entry.offset_days) }}</span>
    </div>
    <div class="card">
      <div class="card-head">
        <button
          v-if="!isAnchor"
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
          @keydown.enter="$emit('commit-label', ($event.target as HTMLInputElement).value)"
          @blur="$emit('commit-label', ($event.target as HTMLInputElement).value)"
        />
        <h3 v-else>{{ entry.label }}</h3>
        <div v-if="!isAnchor" class="tools">
          <button type="button" title="Notiz" aria-label="Notiz" @click="$emit('open-note')">
            <Pencil :size="12" />
          </button>
          <button
            type="button"
            title="Entfernen"
            aria-label="Entfernen"
            @click="$emit('delete')"
          >
            <X :size="13" />
          </button>
        </div>
      </div>

      <p v-if="entry.note">{{ entry.note }}</p>
      <a
        v-if="entry.source_url"
        class="badge stamp"
        :href="entry.source_url"
        target="_blank"
        rel="noopener"
        >{{ entry.source_label ?? "Quelle" }}</a
      >
      <span v-else-if="!isAnchor && isCustom" class="badge custom">Eigene Aufgabe</span>
      <span v-else-if="!isAnchor" class="badge missing">Quelle fehlt</span>

      <template v-if="!isAnchor && cta">
        <a
          v-if="cta.kind === 'link'"
          class="badge cta"
          :href="cta.url"
          target="_blank"
          rel="noopener"
          >{{ cta.label }}</a
        >
        <button v-else type="button" class="badge cta" @click="$emit('open-attachment')">
          {{ hasAttachment ? "Kündigungsschreiben bearbeiten" : cta.label }}
        </button>
      </template>

      <textarea
        v-if="attachmentOpen"
        class="note-input"
        :data-attachment-input="entry.id"
        :value="attachmentText ?? ''"
        rows="10"
        @keydown.esc="$emit('commit-attachment', ($event.target as HTMLTextAreaElement).value)"
        @blur="$emit('commit-attachment', ($event.target as HTMLTextAreaElement).value)"
      ></textarea>

      <textarea
        v-if="noteOpen"
        class="note-input"
        :data-note-input="entry.id"
        :value="noteText ?? ''"
        rows="2"
        placeholder="Notiz - z. B. Aktenzeichen, Ansprechpartner, Telefonnummer"
        @keydown.esc="$emit('commit-note', ($event.target as HTMLTextAreaElement).value)"
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

      <p v-if="!done && entry.collision" class="flag">
        Fällt auf {{ entry.collision }} - Ämter geschlossen.
      </p>
      <p v-else-if="!done && entry.weekend" class="flag">Fällt auf ein Wochenende.</p>
    </div>
  </div>
</template>

<style scoped>
.item {
  position: relative;
}
.item.dragging {
  opacity: 0.4;
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
  background: var(--accent);
  border-color: var(--accent);
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
  border-color: var(--accent);
  border-width: 1.5px;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 20%, transparent);
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
  border: 1px solid var(--accent);
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
  color: var(--paper);
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
  border-color: var(--accent);
  color: var(--accent);
  background: var(--tint-accent);
}
.badge.custom {
  border-color: var(--line);
  color: var(--muted);
}
/* Tertiary on purpose: the checkbox is the card's main action, this shouldn't
  compete with it - plain small text instead of another bordered badge box. */
.badge.cta {
  margin-left: 0.6rem;
  padding: 0;
  border: 0;
  color: var(--muted);
  background: transparent;
  font-size: 0.78rem;
  text-decoration: underline;
  text-underline-offset: 0.15em;
  cursor: pointer;
}
.badge.cta:hover {
  color: var(--accent);
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
  background: color-mix(in srgb, var(--accent) 6%, var(--paper-raised));
  border-left: 2px solid var(--line);
  font-size: 0.85rem;
  color: var(--ink);
  white-space: pre-wrap;
  cursor: text;
}
.flag {
  margin-top: 0.5rem !important;
  padding: 0.4rem 0.6rem;
  border-left: 2px solid var(--warn);
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  color: var(--ink) !important;
  font-size: 0.85rem !important;
}
.badge.missing {
  border-color: var(--line);
  color: var(--muted);
}

@media (max-width: 32rem) {
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
}

@media print {
  .tools,
  .badge.cta {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
