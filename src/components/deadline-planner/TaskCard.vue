<script setup lang="ts">
import { computed, ref } from "vue";
import {
  Check,
  MessageSquarePlus,
  Pencil,
  X,
  ArrowUpRight,
  CalendarClock,
  TriangleAlert,
} from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { MONTH_NAMES, WEEKDAY_NAMES_SHORT } from "../../../lib/date-display";
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
  dateEditOpen: boolean;
  isNext: boolean; // the one task to act on now
  showDate: boolean; // false when the entry above shares this date
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
  (e: "shift-to-workday"): void;
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

// "Mo, 17. Juni 2026": the weekday belongs to the date, not to its own row.
function whenDate(iso: string): string {
  const d = toDate(iso);
  const weekday = WEEKDAY_NAMES_SHORT[(d.getUTCDay() + 6) % 7];
  const month = MONTH_NAMES[d.getUTCMonth()];
  const short = month.length > 4 ? `${month.slice(0, 3)}.` : month;
  return `${weekday}, ${d.getUTCDate()}. ${short} ${d.getUTCFullYear()}`;
}

function shortWhen(iso: string): string {
  const d = toDate(iso);
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()].slice(0, 3)}`;
}

// Nearest weekday at or before the deadline.
const previousWorkday = computed(() => {
  let d = toDate(props.entry.date!);
  // One extra day back for a holiday, then off any weekend it lands on.
  if (props.entry.collision && !props.entry.weekend)
    d = new Date(d.getTime() - 86400000);
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6)
    d = new Date(d.getTime() - 86400000);
  return d.toISOString().slice(0, 10);
});

// The month the rule itself says the tenancy ends, not a re-derivation of it.
const leaseEndLabel = computed(() => {
  const step = props.entry.derivation?.find(
    (d) => d.step === "target-end-month",
  );
  if (!step?.value) return "";
  const [y, m] = step.value.split("-").map(Number);
  return `bis Ende ${MONTH_NAMES[m - 1]} ${y}`;
});

const isSunday = computed(() => toDate(props.entry.date!).getUTCDay() === 0);

// A step at offset 0 happens on the day itself, so it cannot move.
const pinnedToAnchor = computed(() => props.entry.offset_days === 0);
const showOfficeClosed = computed(
  () =>
    !props.done &&
    !hasRange.value &&
    props.entry.needs_office === true &&
    (!!props.entry.collision || !!props.entry.weekend),
);

// True once the deadline is a real window, not just a point.
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
    :class="{ anchor: isAnchor, past: isPast, done, next: isNext }"
  >
    <span class="dot" :data-dot-key="entry.id"></span>
    <div v-if="showDate" class="when">
      <b :class="{ overdue: !!entry.rescue }">{{
        whenDate(entry.rescue ? entry.rescue.date : entry.date!)
      }}</b>
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
      <button
        type="button"
        class="edit-anchor"
        @click="$emit('open-date-edit')"
      >
        <CalendarClock :size="12" /> Termin verschieben
      </button>
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
      <p v-if="isSunday" class="anchor-warn">
        <TriangleAlert :size="14" />
        Ein Sonntag: Hausordnung und Ruhezeiten gelten, und Übergaben machen die
        wenigsten Vermieter.
      </p>
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
        <span v-if="isNext && !done" class="badge next-badge"
          >Als Nächstes</span
        >
        <div class="tools">
          <button
            type="button"
            title="Termin verschieben"
            aria-label="Termin verschieben"
            @click="$emit('open-date-edit')"
          >
            <CalendarClock :size="12" />
          </button>
          <button
            type="button"
            title="Titel ändern"
            aria-label="Titel ändern"
            @click="$emit('open-label-edit')"
          >
            <Pencil :size="12" />
          </button>
          <button
            type="button"
            title="Notiz"
            aria-label="Notiz"
            @click="$emit('open-note')"
          >
            <MessageSquarePlus :size="12" />
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
        @change="parkDate"
        @blur="closeDateEdit"
        @keydown.enter="($event.target as HTMLInputElement).blur()"
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
      <div v-if="entry.rescue" class="past-deadline">
        <b><TriangleAlert :size="15" /> Frist verstrichen</b>
        <p>
          Was du jetzt tun kannst: spätestens am
          {{ shortWhen(entry.rescue.date) }} nachholen ({{
            entry.rescue.label
          }}).
        </p>
      </div>
      <p v-if="entry.offset_rule || deferred" class="defer">
        <span class="defer-label">Mietende {{ leaseEndLabel }}</span>
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
        <summary>
          Wie berechnet? ({{ entry.derivation.length }} Schritte)
        </summary>
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

      <div v-if="cta" class="cta-row">
        <a
          v-if="cta?.kind === 'link'"
          class="cta-link"
          :href="cta.url"
          target="_blank"
          rel="noopener"
          >{{ cta.label }} <ArrowUpRight :size="14"
        /></a>
        <button
          v-else-if="cta"
          type="button"
          class="cta-button"
          @click="$emit('open-attachment')"
        >
          {{
            hasAttachment
              ? `${cta!.label} bearbeiten`
              : `${cta!.label} aufsetzen`
          }}
        </button>
      </div>

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
      <!-- Only matters for a single pinned day, a range has other days. -->
      <p v-else-if="showOfficeClosed" class="flag hint">
        {{ entry.collision ? `${entry.collision}, ` : "Sa/So, " }}Ämter haben
        zu.
        <button
          v-if="!pinnedToAnchor"
          type="button"
          @click="$emit('shift-to-workday')"
        >
          Auf {{ shortWhen(previousWorkday) }} vorziehen
        </button>
      </p>
    </div>
  </div>
</template>

<style scoped>
.item {
  position: relative;
}
.dot {
  --dot: 0.55rem;
  position: absolute;
  left: calc(-1 * var(--rail-gap, 1.5rem) - var(--dot) / 2);
  top: 0.4rem;
  width: var(--dot);
  height: var(--dot);
  border-radius: 50%;
  background: var(--paper);
  border: 1.5px solid var(--accent);
}
.item.anchor .dot {
  --dot: 0.8rem;
  background: var(--anchor);
  border-color: var(--anchor);
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
  /* Right edge sits just shy of the rail's dot/line (dot at -1.8rem). */
  left: -11.6rem;
  top: 0.55rem;
  width: 10.5rem;
  /* align-items:flex-end right-aligns each line by its OWN box: lines wider
    than 8rem still get their right edge pinned. */
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-family: var(--font-mono);
}
.when b {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--ink);
  line-height: 1.25;
  white-space: nowrap;
}
.when b.past-deadline {
  text-decoration: line-through;
  color: var(--muted);
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  box-shadow: var(--shadow-sm);
}
.card:hover {
  box-shadow: var(--shadow-md);
}
.item.next .card {
  border-color: var(--accent);
  border-left-width: 3px;
  box-shadow: var(--shadow-md);
}
/* A quiet label: the blue in this card belongs to its action. */
.next-badge {
  align-self: center;
  margin: 0 0 0 auto;
  border-color: var(--line);
  background: var(--paper);
  color: var(--muted);
  font-family: var(--font-sans);
  white-space: nowrap;
}
/* Full-width divider, not a card - an empty bordered box read as a stuck
  input field, and blue there implied "click me", not "milestone". */
/* A slim divider, not a card: nothing happens on this row itself. */
.anchor-divider {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin: 0.5rem 0 1rem;
  padding: 0.25rem 1rem;
  border-left: 3px solid var(--anchor);
  background: color-mix(in srgb, var(--anchor) 8%, transparent);
  border-radius: var(--radius);
}
.anchor-divider .label {
  font-weight: 600;
  font-size: var(--fs-md);
  color: var(--accent);
}
/* A square button has no text baseline to align the row by. */
.anchor-divider .check {
  align-self: center;
  margin-top: 0;
}
.anchor-divider .label.done {
  text-decoration: line-through;
  color: var(--muted);
}
.anchor-warn {
  flex-basis: 100%;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin: 0.25rem 0 0;
  font-size: var(--fs-sm);
  color: var(--warn);
}
.item.current .anchor-divider {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.item.focused .anchor-divider {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.edit-anchor {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: var(--fs-xs);
  padding: 0.25rem 0.5rem;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  color: var(--accent);
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
.item.done .card p,
.item.done .card .range-line,
.item.done .card .derivation,
.item.done .card .cta-row,
.item.done .card .defer,
.item.done .card .badge {
  display: none;
}
.item.done .card-head h3 {
  text-decoration: line-through;
  color: var(--muted);
}
/* Spotlight: the card the Timeline is centered on stands out, others recede. */
.card {
  transition:
    opacity 0.15s,
    transform 0.15s,
    border-color 0.15s,
    box-shadow 0.15s;
}
/* An accent edge and elevation, never a blue glow. */
.item.current .card {
  border-color: var(--accent);
  box-shadow: var(--shadow-lg);
}
.item.focused .card {
  border-color: var(--accent);
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
  font-size: var(--fs-md);
}
.title-input {
  font-family: inherit;
  font-weight: 600;
  font-size: var(--fs-md);
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
  margin-top: 0.25rem;
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
  margin: 0.25rem 0 0;
  max-width: 68ch;
  color: var(--muted);
  font-size: var(--fs-sm);
}
/* Only the start-by day is bold: it is the decision, the rest is context. */
.range-line {
  font-size: var(--fs-sm);
}
.range-line b {
  color: var(--ink);
  font-weight: 600;
}
/* The proof it wasn't estimated should be one click away, not in every card. */
.derivation {
  margin-top: 0.5rem;
  font-size: var(--fs-sm);
  color: var(--muted);
}
.derivation summary {
  cursor: pointer;
  color: var(--accent);
}
.defer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.5rem 0 0;
}
.defer-label {
  font-size: var(--fs-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
}
.defer button {
  font-size: var(--fs-xs);
  padding: 0.25rem 0.5rem;
}
.defer button[aria-pressed="true"] {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.cta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--line);
}
.derivation ol {
  margin: 0.5rem 0 0;
  padding-left: 1.5rem;
}
.derivation li {
  margin-bottom: 0.25rem;
}
.card .badge {
  margin-top: 0.5rem;
  margin-left: 0;
}
.badge.stamp {
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--accent);
  background: var(--tint-accent);
  text-decoration: none;
}
.badge.stamp:hover {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}
.badge.custom {
  border-color: var(--line);
  color: var(--muted);
}
/* Its own row in body type, not a badge - an action ("aufsetzen") and a
  source citation are different kinds of thing and shouldn't look identical. */
/* A link leaves the page, a button acts in place. Same colour, own shape. */
.cta-link {
  display: inline-block;
  color: var(--accent);
  font-size: var(--fs-sm);
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
.cta-link:hover {
  opacity: 0.8;
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
  padding: 0.5rem 0.5rem;
  background: var(--paper);
  resize: vertical;
}
.date-input {
  display: block;
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
  padding: 0.5rem 0.5rem;
  background: color-mix(in srgb, var(--accent) 6%, var(--paper-raised));
  border-left: 2px solid var(--line);
  font-size: var(--fs-sm);
  color: var(--ink);
  white-space: pre-wrap;
  cursor: text;
}
.flag {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.5rem !important;
  color: var(--warn) !important;
  font-size: var(--fs-sm) !important;
}
/* A closed office is a fact with a fix, not an alarm. */
.flag.hint {
  color: var(--muted) !important;
}
.flag button {
  font-size: var(--fs-xs);
  padding: 0.25rem 0.5rem;
}
.past-deadline {
  margin-top: 0.5rem;
  padding-left: 0.75rem;
  border-left: 3px solid var(--warn);
}
.past-deadline b {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--warn);
  font-size: var(--fs-sm);
}
.past-deadline p {
  margin: 0.25rem 0 0;
  font-size: var(--fs-sm);
}
.flag-impossible {
  font-weight: 600;
  border-left-width: 3px;
}
@media (max-width: 40rem) {
  .item {
    margin-bottom: 1rem;
  }
  .check::before {
    content: "";
    position: absolute;
    inset: -0.55rem;
  }
  .when {
    position: static;
    width: auto;
    display: flex;
    flex-direction: row;
    /* Every child is nowrap, so a rescue card would otherwise run off screen. */
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: baseline;
    margin: 0 0 0.5rem 1rem;
  }
}

@media print {
  .tools,
  .cta-link,
  .cta-button {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
