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
import { longDate, shortDate } from "../../../lib/date-display";
import { sourceLabel } from "../../../lib/offset-label";
import type { TaskCta } from "./task-cta";

const props = defineProps<{
  entry: ScheduleEntry;
  anchorDate: string; // the plan's own day, needed to size the tenancy overlap
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
      <h3 v-else>
        {{ entry.label }}
        <span v-if="isPast && !done" class="badge late">Überfällig</span>
        <span v-else-if="isNext && !done" class="badge">Als Nächstes</span>
      </h3>
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

    <!-- A missed deadline gets one instruction in ink and the dates behind it
      in grey. Everything else on the card ranks below that line. -->
    <template v-if="isPast && !done && entry.rescue">
      <p class="lead">Bis {{ longDate(entry.rescue.date) }} nachholen.</p>
      <p class="meta">
        Frist war {{ longDate(entry.date!) }}.
        <template v-if="!doubleRent">{{ entry.rescue.label }}.</template>
      </p>
    </template>
    <p v-else class="dates">
      <span :class="{ overdue: isPast }"
        >Frist: {{ longDate(entry.date!)
        }}<template v-if="isPast"> (verstrichen)</template></span
      >
      <template v-if="entry.earliestDate !== entry.date">
        &nbsp;·&nbsp; möglich ab: {{ longDate(entry.earliestDate!) }}</template
      >
      <template v-if="entry.startByDate !== entry.date">
        &nbsp;·&nbsp;
        <b>Termin buchen bis: {{ longDate(entry.startByDate!) }}</b>
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

    <!-- Below the hairline: what the card assumes and where it got it from.
      Never the action, so the eye can stop at the button above. -->
    <div class="footer">
      <div
        v-if="entry.offset_rule || deferred"
        class="defer"
        role="radiogroup"
        aria-label="Mietende"
      >
        <span class="defer-label">Mietende</span>
        <button
          type="button"
          role="radio"
          :aria-checked="!deferred"
          @click="deferred && $emit('toggle-defer')"
        >
          Ende des Umzugsmonats
        </button>
        <button
          type="button"
          role="radio"
          :aria-checked="deferred"
          @click="!deferred && $emit('toggle-defer')"
        >
          Einen Monat später
        </button>
      </div>

      <!-- One provenance affordance: the paragraph lives inside the derivation
        it is the basis for, not next to it as a second offer. -->
      <details v-if="entry.derivation?.length" class="derivation">
        <summary>Wie wird das berechnet?</summary>
        <ol>
          <li v-for="step in entry.derivation" :key="step.step">
            {{ step.label }}
          </li>
        </ol>
        <p class="src">
          Grundlage:
          <a
            v-if="entry.source_url"
            :href="entry.source_url"
            target="_blank"
            rel="noopener"
            >{{ entry.source_label ?? "Quelle" }} <ArrowUpRight :size="12"
          /></a>
          <span v-else>{{ sourceLabel(entry) }}</span>
        </p>
      </details>

      <p v-else class="src">
        Grundlage:
        <a
          v-if="entry.source_url"
          :href="entry.source_url"
          target="_blank"
          rel="noopener"
          >{{ entry.source_label ?? "Quelle" }}</a
        >
        <span v-else>{{
          isCustom ? "Eigene Aufgabe" : sourceLabel(entry)
        }}</span>
      </p>
    </div>
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
.card[data-status="erledigt"] .cta-row,
.card[data-status="erledigt"] .footer {
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

/* Three levels and no more: the instruction, the consequence, the record.
  Mono is for the fact row only, a date set in mono inside a sentence is the
  thing that made these cards read as noise. */
.lead {
  margin: 0.5rem 0 0;
  font-size: var(--fs-md);
  font-weight: 600;
}
.meta {
  margin: 0.2rem 0 0;
  font-size: var(--fs-sm);
  color: var(--muted);
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
/* Not struck through: the day still governs the legal outcome, it is only
  behind us. */
.dates .overdue {
  color: var(--warn);
}
.hint {
  margin: 0.5rem 0 0;
  max-width: 68ch;
  font-size: var(--fs-sm);
}
.src {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.derivation .src {
  margin-top: 0.5rem;
}
.src a {
  color: var(--accent);
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

/* Assumptions and provenance, below a hairline and in the small size, so the
  eye stops at the button above instead of shopping the whole card. */
.footer {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 1.2rem;
  margin-top: 0.8rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--line);
}
.footer:empty {
  display: none;
}

/* Wraps rather than truncates: an option nobody can finish reading is worse
  than one on a second line. */
.defer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.3rem;
}
.defer-label {
  font-size: var(--fs-xs);
  color: var(--muted);
}
.defer button {
  font-size: var(--fs-xs);
  padding: 0.15rem 0.5rem;
  white-space: nowrap;
}
/* A setting, so it never outweighs the action above it: the chosen side is
  marked by ink and a border, not by a fill. */
.defer button[aria-checked="true"] {
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}
.defer button[aria-checked="false"] {
  color: var(--muted);
}
.derivation {
  font-size: var(--fs-xs);
  color: var(--muted);
}
.derivation summary {
  cursor: pointer;
  color: var(--muted);
}
.derivation summary:hover {
  color: var(--accent);
}
.derivation ol {
  margin: 0.5rem 0 0;
  padding-left: 1.5rem;
}
.derivation li {
  margin-bottom: 0.25rem;
}
.derivation .src a {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
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
