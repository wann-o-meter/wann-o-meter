<script setup lang="ts">
import { computed } from "vue";
import {
  Check,
  Pencil,
  X,
  ArrowUpRight,
  CalendarClock,
  TriangleAlert,
  ArrowRight,
} from "lucide-vue-next";
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
  editing: boolean; // title input open
  noteOpen: boolean;
  noteText?: string;
  attachmentOpen: boolean;
  attachmentText?: string;
  hasAttachment: boolean;
  cta: TaskCta | null;
  showDate: boolean; // false when the previous card already shows this same date
  dateEditOpen: boolean;
}>();

defineEmits<{
  (e: "toggle-done"): void;
  (e: "commit-label", value: string): void;
  (e: "open-note"): void;
  (e: "commit-note", value: string): void;
  (e: "open-attachment"): void;
  (e: "commit-attachment", value: string): void;
  (e: "delete"): void;
  (e: "open-date-edit"): void;
  (e: "commit-date-edit", iso: string): void;
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

// Relative to today, not to the anchor day - "in 39 Tagen" is what tells you
// whether to act now, "42 Tage vorher" only tells you the plan's own rhythm.
function relativeLabel(iso: string): string {
  const todayIso = new Date().toISOString().slice(0, 10);
  const days = Math.round(
    (toDate(iso).getTime() - toDate(todayIso).getTime()) / 86400000,
  );
  if (days === 0) return "heute";
  return days > 0 ? `in ${days} Tagen` : `vor ${Math.abs(days)} Tagen`;
}

// "8. Nov" - short enough for a single inline line with up to three dates.
function shortWhen(iso: string): string {
  const d = toDate(iso);
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()].slice(0, 3)}`;
}
// "YYYY-MM" -> "November 2026", for entry.rescue.leaseEndMonth.
function monthLabel(yyyyMm: string): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}

// True once the deadline is a real window, not just a point - earliest and
// startBy both default to the deadline itself when unresearched (see
// computeSchedule), so this is false for the vast majority of today's data.
const hasRange = computed(
  () =>
    props.entry.earliestDate !== props.entry.date ||
    props.entry.startByDate !== props.entry.date,
);
</script>

<template>
  <div
    class="item"
    :data-entry-id="entry.id"
    :data-entry-date="entry.date"
    :class="{ anchor: isAnchor, past: isPast, done }"
  >
    <span class="dot" :data-dot-key="entry.id"></span>
    <div v-if="showDate" class="when">
      <b :class="{ 'past-deadline': entry.pastDeadline }">{{
        whenDate(entry.date!)
      }}</b>
      <span v-if="entry.rescue" class="next-possible"
        ><ArrowRight :size="14" /> {{ whenDate(entry.rescue.date) }}</span
      >
      <span
        >{{ weekdayName(entry.date!) }} ·
        {{ offsetLabel(entry.offset_days) }}</span
      >
      <span v-if="!entry.rescue" class="rel">{{
        relativeLabel(entry.date!)
      }}</span>
    </div>

    <div v-if="isAnchor" class="anchor-divider">
      <button
        type="button"
        class="check"
        :aria-pressed="done"
        aria-label="Als erledigt markieren"
        @click="$emit('toggle-done')"
      >
        <Check v-if="done" :size="11" />
      </button>
      <span class="label" :class="{ done }">{{ entry.label }}</span>
      <span v-if="!done && entry.collision" class="flag-inline"
        >Fällt auf {{ entry.collision }} - Ämter geschlossen.</span
      >
      <span v-else-if="!done && entry.weekend" class="flag-inline"
        >Fällt auf ein Wochenende.</span
      >
      <button
        type="button"
        class="edit-anchor"
        title="Datum ändern"
        aria-label="Datum ändern"
        @click="$emit('open-date-edit')"
      >
        <CalendarClock :size="12" />
      </button>
      <input
        v-if="dateEditOpen"
        type="date"
        class="date-input"
        :value="entry.date"
        aria-label="Datum ändern"
        @change="
          $emit('commit-date-edit', ($event.target as HTMLInputElement).value)
        "
      />
    </div>

    <div v-else class="card">
      <div class="card-head">
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
          @blur="
            $emit('commit-label', ($event.target as HTMLInputElement).value)
          "
        />
        <h3 v-else>{{ entry.label }}</h3>
        <div class="tools">
          <button
            type="button"
            title="Datum ändern"
            aria-label="Datum ändern"
            @click="$emit('open-date-edit')"
          >
            <CalendarClock :size="12" />
          </button>
          <button
            type="button"
            title="Notiz"
            aria-label="Notiz"
            @click="$emit('open-note')"
          >
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

      <input
        v-if="dateEditOpen"
        type="date"
        class="date-input"
        :value="entry.date"
        aria-label="Datum ändern"
        @change="
          $emit('commit-date-edit', ($event.target as HTMLInputElement).value)
        "
      />

      <p v-if="hasRange" class="range-line">
        <template v-if="entry.earliestDate !== entry.date"
          >Möglich ab {{ shortWhen(entry.earliestDate!) }} · </template
        >Frist {{ shortWhen(entry.date!)
        }}<template v-if="entry.startByDate !== entry.date">
          ·
          <b>Termin buchen bis {{ shortWhen(entry.startByDate!) }}</b></template
        >
      </p>
      <p v-if="entry.rescue" class="flag flag-past-deadline">
        <TriangleAlert :size="15" />
        Frist verstrichen - spätestens {{ shortWhen(entry.rescue.date) }}
        nachholen (Mietende dann Ende
        {{ monthLabel(entry.rescue.leaseEndMonth) }}).
      </p>
      <details v-if="entry.derivation?.length" class="derivation">
        <summary>Wie berechnet?</summary>
        <ol>
          <li v-for="step in entry.derivation" :key="step.step">
            {{ step.label }}
          </li>
        </ol>
      </details>

      <p v-if="entry.note">{{ entry.note }}</p>
      <a
        v-if="entry.source_url"
        class="badge stamp"
        :href="entry.source_url"
        target="_blank"
        rel="noopener"
        >{{ entry.source_label ?? "Quelle" }}</a
      >
      <span v-else-if="isCustom" class="badge custom">Eigene Aufgabe</span>

      <template v-if="cta">
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
          class="cta-link"
          @click="$emit('open-attachment')"
        >
          {{
            hasAttachment ? `${cta.label} bearbeiten` : `${cta.label} aufsetzen`
          }}
        </button>
      </template>

      <textarea
        v-if="attachmentOpen"
        class="note-input"
        :data-attachment-input="entry.id"
        :value="attachmentText ?? ''"
        rows="10"
        @keydown.esc="
          $emit(
            'commit-attachment',
            ($event.target as HTMLTextAreaElement).value,
          )
        "
        @blur="
          $emit(
            'commit-attachment',
            ($event.target as HTMLTextAreaElement).value,
          )
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
        @blur="
          $emit('commit-note', ($event.target as HTMLTextAreaElement).value)
        "
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

      <p v-if="!done && entry.impossible" class="flag flag-impossible">
        Bei diesem Termin nicht mehr rechtzeitig möglich - Termin sofort buchen.
      </p>
      <!-- Weekend/holiday only matters for a single day you're pinned to -
        with a range you can just act on a different day within it. -->
      <p v-else-if="!done && !hasRange && entry.collision" class="flag">
        Fällt auf {{ entry.collision }} - Ämter geschlossen.
      </p>
      <p v-else-if="!done && !hasRange && entry.weekend" class="flag">
        Fällt auf ein Wochenende.
      </p>
    </div>
  </div>
</template>

<style scoped>
.item {
  position: relative;
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
  /* Right edge sits just shy of the rail's dot/line (dot at -1.8rem) - was
    -13rem, leaving several rem of dead space between the date and the card
    text it belongs to. */
  left: -10.5rem;
  top: 0.55rem;
  width: 8rem;
  /* flex + align-items:flex-end right-aligns each line by its OWN box, not
    by the shared text-align line-box - the weekday/offset line is often
    wider than the 8rem width and needs its right edge pinned regardless. */
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-family: var(--font-mono);
}
.when b {
  font-size: 0.85rem;
  line-height: 1.3;
  white-space: nowrap;
}
.when b.past-deadline {
  text-decoration: line-through;
  color: var(--muted);
}
.when span {
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.3;
  white-space: nowrap;
}
.when .rel {
  color: var(--accent);
  font-size: 0.68rem;
}
.when .next-possible {
  color: var(--warn);
  font-size: 0.85rem;
  display: flex;
  gap: 0.1rem;
  align-items: center;
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 0.7rem 0.9rem;
  margin-bottom: 0.4rem;
  box-shadow:
    0 1px 3px color-mix(in srgb, var(--ink) 7%, transparent),
    0 1px 1px color-mix(in srgb, var(--ink) 5%, transparent);
}
/* Full-width divider, not a card - an empty bordered box read as a stuck
  input field, and blue there implied "click me", not "milestone". */
.anchor-divider {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.6rem;
  margin: 0.4rem 0 0.8rem;
  padding: 0.5rem 0;
  border-top: 2px solid var(--accent);
  border-bottom: 2px solid var(--accent);
}
.anchor-divider .label {
  font-weight: 600;
  font-size: 1rem;
  color: var(--accent);
}
.anchor-divider .label.done {
  text-decoration: line-through;
  color: var(--muted);
}
.anchor-divider .flag-inline {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--warn);
}
.item.current .anchor-divider {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.item.focused .anchor-divider {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.edit-anchor {
  width: 1.5rem;
  height: 1.5rem;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 2px;
  cursor: pointer;
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.edit-anchor:hover {
  background: var(--paper);
  border-color: var(--line);
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
/* Spotlight: whichever card the Timeline overview is currently centered on
  (scroll position, see DeadlinePlanner's highlightedDate) stands out, every
  other card recedes - a visual anchor for "where am I in this list". */
.card {
  transition:
    opacity 0.15s,
    transform 0.15s,
    box-shadow 0.15s;
}
.item:not(.current) .card {
  opacity: 0.6;
}
.item.current .card {
  transform: scale(1.02);
  box-shadow:
    0 8px 20px color-mix(in srgb, var(--accent) 25%, transparent),
    0 2px 6px color-mix(in srgb, var(--ink) 10%, transparent);
}
/* Focused: a hover (either direction, card <-> Timeline node) or a brief
  flash after clicking a Timeline node - independent of .current so both can
  show at once without fighting each other's transform/opacity. */
.item.focused .card {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
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
/* The only bold number in the card is the one you actually need to act on -
  earliest/deadline are context, the start-by day is the decision. */
.range-line {
  font-size: 0.85rem;
}
.range-line b {
  color: var(--ink);
  font-weight: 600;
}
/* Closed by default, native <details> - the proof it wasn't estimated
  should be one click away, not printed into every card whether asked for or
  not (only offset_rule-based entries have one anyway). */
.derivation {
  margin-top: 0.4rem;
  font-size: 0.78rem;
  color: var(--muted);
}
.derivation summary {
  cursor: pointer;
  color: var(--accent);
}
.derivation ol {
  margin: 0.4rem 0 0;
  padding-left: 1.3rem;
}
.derivation li {
  margin-bottom: 0.2rem;
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
/* Its own row in body type, not a badge - an action ("aufsetzen") and a
  source citation are different kinds of thing and shouldn't look identical. */
.cta-link {
  display: block;
  margin-top: 0.5rem;
  padding: 0;
  border: 0;
  color: var(--accent);
  background: transparent;
  font-family: inherit;
  font-size: 0.88rem;
  text-decoration: underline;
  text-underline-offset: 0.15em;
  cursor: pointer;
}
.cta-link:hover {
  opacity: 0.8;
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
.date-input {
  display: block;
  font-family: inherit;
  font-size: 0.85rem;
  color: inherit;
  border: 1px solid var(--accent);
  border-radius: 2px;
  padding: 0.3rem 0.5rem;
  background: var(--paper);
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
.flag-impossible {
  font-weight: 600;
  border-left-width: 3px;
}
@media (max-width: 32rem) {
  .when {
    position: static;
    width: auto;
    display: flex;
    flex-direction: row;
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
  .cta-link {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
