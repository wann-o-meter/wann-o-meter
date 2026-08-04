<script setup lang="ts">
import { computed, nextTick, reactive, ref, useTemplateRef } from "vue";
import { Check, Pencil, Plus, X } from "lucide-vue-next";
import { MONTH_NAMES, WEEKDAY_NAMES_LONG } from "../../lib/date-display";
import { formatDate, toDate } from "../../lib/format-date";
import { computeUmzugSchedule } from "../../lib/umzug";
import type { UmzugDeadline, UmzugKommuneData, UmzugScheduleEntry } from "../../lib/umzug";

const props = defineProps<{
  kommunen: UmzugKommuneData[];
  defaultSlug?: string;
}>();

const MOVEDAY_ID = "__moveday";
const CUSTOM_PREFIX = "custom-";
const moveDate = ref("");
const selectedSlug = ref(props.defaultSlug && props.kommunen.some((k) => k.slug === props.defaultSlug) ? props.defaultSlug : props.kommunen[0]?.slug);
const rootEl = useTemplateRef<HTMLElement>("rootEl");

const selected = computed(() => props.kommunen.find((k) => k.slug === selectedSlug.value) ?? props.kommunen[0]);

// Client-only editing layer on top of the generated schedule - nothing here
// is persisted (no login, no storage), refreshing resets it. It exists so
// the plan can be worked FROM, not just read.
interface CustomTask {
  id: string;
  label: string;
  offsetDays: number;
}
let customUid = 0;
const customTasks = ref<CustomTask[]>([]);
const doneIds = reactive<Record<string, boolean>>({});
const deletedIds = reactive<Record<string, boolean>>({});
const userNotes = reactive<Record<string, string>>({});
const editingId = ref<string | null>(null);
const openNoteId = ref<string | null>(null);
const lastDeleted = ref<{ id: string; label: string } | null>(null);

function isCustom(id: string): boolean {
  return id.startsWith(CUSTOM_PREFIX);
}

const workingDeadlines = computed<UmzugDeadline[]>(() => {
  if (!selected.value) return [];
  const custom: UmzugDeadline[] = customTasks.value.map((t) => ({
    id: t.id,
    label: t.label,
    offset_days: t.offsetDays,
    source_url: null,
  }));
  return [...selected.value.deadlines, ...custom].filter((d) => !deletedIds[d.id]);
});

// The move day itself is UI chrome, not a researched fact - it needs no
// source and is definitionally correct, so it's injected here rather than
// stored in data/umzug/ next to entries that do need provenance. Unlike a
// real deadline it can't be checked off, noted, or deleted - it's the
// anchor everything else is measured from, not a task.
const schedule = computed<UmzugScheduleEntry[]>(() => {
  if (!moveDate.value || !selected.value) return [];
  const withAnchor: UmzugDeadline[] = [
    { id: MOVEDAY_ID, label: "Umzugstag", offset_days: 0, source_url: null },
    ...workingDeadlines.value,
  ];
  return computeUmzugSchedule(moveDate.value, withAnchor, "DE", selected.value.state);
});

const timeline = computed(() => schedule.value.filter((e) => e.date !== null));
const unscheduled = computed(() => schedule.value.filter((e) => e.date === null));
const tasks = computed(() => schedule.value.filter((e) => e.id !== MOVEDAY_ID));

// Interleaves gap markers between consecutive rows so the proportional
// spacing (a two-day gap reads differently than a two-month one) is a real
// node to hang a hover-revealed insert button on, not just margin.
type RailNode =
  | { kind: "item"; entry: UmzugScheduleEntry }
  | { kind: "gap"; id: string; afterOffset: number; beforeOffset: number; heightPx: number };

const railNodes = computed<RailNode[]>(() => {
  const nodes: RailNode[] = [];
  timeline.value.forEach((entry, i) => {
    if (i > 0) {
      const prev = timeline.value[i - 1];
      const days = Math.round((toDate(entry.date!).getTime() - toDate(prev.date!).getTime()) / 86400000);
      nodes.push({
        kind: "gap",
        id: `gap-${prev.id}-${entry.id}`,
        afterOffset: prev.offset_days!,
        beforeOffset: entry.offset_days!,
        heightPx: Math.min(96, Math.max(22, days * 2.6)),
      });
    }
    nodes.push({ kind: "item", entry });
  });
  return nodes;
});

const stats = computed(() => {
  const open = tasks.value.filter((e) => !doneIds[e.id]);
  const firstOpen = timeline.value.find((e) => e.id !== MOVEDAY_ID && !doneIds[e.id]);
  const warnings = timeline.value.filter((e) => e.id !== MOVEDAY_ID && !doneIds[e.id] && (e.weekend || e.collision)).length;
  return {
    open: open.length,
    done: tasks.value.length - open.length,
    first: firstOpen ? formatDate(firstOpen.date!).replace(/\.\d{4}$/, "") : "—",
    warnings,
  };
});

// Full "17. Juni 2026" / "Mittwoch" instead of formatDateWithWeekday's
// compact "Mi., 17.06.2026" - the rail has room, and spelled-out names read
// less like a table row and more like an actual plan.
function whenDate(iso: string): string {
  const d = toDate(iso);
  return `${d.getUTCDate()}. ${MONTH_NAMES[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
function weekdayName(iso: string): string {
  return WEEKDAY_NAMES_LONG[(toDate(iso).getUTCDay() + 6) % 7];
}

function offsetLabel(offsetDays: number | null): string {
  if (offsetDays === null) return "Frist noch nicht recherchiert";
  if (offsetDays === 0) return "Umzugstag";
  return offsetDays < 0 ? `${Math.abs(offsetDays)} Tage vorher` : `${offsetDays} Tage danach`;
}

function isPast(date: string): boolean {
  return date < new Date().toISOString().slice(0, 10);
}

function toggleDone(id: string) {
  doneIds[id] = !doneIds[id];
}

function focusWithin(selector: string) {
  nextTick(() => {
    const el = rootEl.value?.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
    el?.focus();
    if (el instanceof HTMLInputElement) el.select();
  });
}

function startEditingLabel(id: string) {
  editingId.value = id;
  focusWithin(`[data-title-input="${id}"]`);
}

function commitLabel(id: string, value: string) {
  if (editingId.value !== id) return;
  const task = customTasks.value.find((t) => t.id === id);
  if (task) task.label = value.trim() || "Ohne Titel";
  editingId.value = null;
}

function openNote(id: string) {
  openNoteId.value = id;
  focusWithin(`[data-note-input="${id}"]`);
}

function commitNote(id: string, value: string) {
  if (openNoteId.value !== id) return;
  const trimmed = value.trim();
  if (trimmed) userNotes[id] = trimmed;
  else delete userNotes[id];
  openNoteId.value = null;
}

function deleteEntry(entry: UmzugScheduleEntry) {
  deletedIds[entry.id] = true;
  lastDeleted.value = { id: entry.id, label: entry.label };
}

function undoDelete() {
  if (!lastDeleted.value) return;
  delete deletedIds[lastDeleted.value.id];
  lastDeleted.value = null;
}

function insertCustomTask(afterOffset: number, beforeOffset: number) {
  const id = `${CUSTOM_PREFIX}${++customUid}`;
  customTasks.value.push({ id, label: "", offsetDays: Math.round((afterOffset + beforeOffset) / 2) });
  startEditingLabel(id);
}

function addTaskAtEnd() {
  const known = timeline.value.filter((e) => e.offset_days !== null).map((e) => e.offset_days!);
  const offset = (known.length > 0 ? Math.max(...known) : 0) + 3;
  const id = `${CUSTOM_PREFIX}${++customUid}`;
  customTasks.value.push({ id, label: "", offsetDays: offset });
  startEditingLabel(id);
}

// `window` is not in template scope.
function print() {
  window.print();
}
</script>

<template>
  <div ref="rootEl" class="umzug-planer">
    <div class="form">
      <label class="field">
        <span>Vorhaben</span>
        <select disabled>
          <option>Umzug innerhalb Deutschlands</option>
        </select>
      </label>
      <label class="field">
        <span>Umzugstag</span>
        <input v-model="moveDate" type="date" aria-label="Umzugstag" />
      </label>
      <label class="field">
        <span>Ort</span>
        <select v-model="selectedSlug">
          <option v-for="k in kommunen" :key="k.slug" :value="k.slug">{{ k.name }}</option>
        </select>
      </label>
    </div>

    <div v-if="moveDate" class="summary">
      <div class="stat"><span class="k">Offen</span><span class="v">{{ stats.open }}</span></div>
      <div class="stat"><span class="k">Erledigt</span><span class="v">{{ stats.done }}</span></div>
      <div class="stat"><span class="k">Erste Frist</span><span class="v">{{ stats.first }}</span></div>
      <div class="stat"><span class="k">Warnungen</span><span class="v">{{ stats.warnings }}</span></div>
    </div>

    <template v-if="moveDate">
      <p class="scalenote">Abstände maßstäblich - enge Stellen sind arbeitsreiche Wochen</p>
      <div class="rail">
        <template v-for="node in railNodes" :key="node.kind === 'gap' ? node.id : node.entry.id">
          <div v-if="node.kind === 'gap'" class="gap" :style="{ height: `${node.heightPx}px` }">
            <button
              type="button"
              class="gap-add"
              title="Aufgabe hier einfügen"
              aria-label="Aufgabe hier einfügen"
              @click="insertCustomTask(node.afterOffset, node.beforeOffset)"
            >
              <Plus :size="12" />
            </button>
          </div>
          <div
            v-else
            class="item"
            :class="{ moveday: node.entry.id === MOVEDAY_ID, past: isPast(node.entry.date!), done: doneIds[node.entry.id] }"
          >
            <span class="dot"></span>
            <div class="when">
              <b>{{ whenDate(node.entry.date!) }}</b>
              <span>{{ weekdayName(node.entry.date!) }} · {{ offsetLabel(node.entry.offset_days) }}</span>
            </div>
            <div class="card">
              <div class="card-head">
                <button
                  v-if="node.entry.id !== MOVEDAY_ID"
                  type="button"
                  class="check"
                  :aria-pressed="!!doneIds[node.entry.id]"
                  aria-label="Als erledigt markieren"
                  @click="toggleDone(node.entry.id)"
                >
                  <Check v-if="doneIds[node.entry.id]" :size="11" />
                </button>
                <input
                  v-if="editingId === node.entry.id"
                  class="title-input"
                  :data-title-input="node.entry.id"
                  :value="node.entry.label"
                  placeholder="Was ist zu tun?"
                  @keydown.enter="commitLabel(node.entry.id, ($event.target as HTMLInputElement).value)"
                  @blur="commitLabel(node.entry.id, ($event.target as HTMLInputElement).value)"
                />
                <h3 v-else>{{ node.entry.label }}</h3>
                <div v-if="node.entry.id !== MOVEDAY_ID" class="tools">
                  <button type="button" title="Notiz" aria-label="Notiz" @click="openNote(node.entry.id)"><Pencil :size="12" /></button>
                  <button type="button" title="Entfernen" aria-label="Entfernen" @click="deleteEntry(node.entry)"><X :size="13" /></button>
                </div>
              </div>

              <p v-if="node.entry.note">{{ node.entry.note }}</p>
              <a v-if="node.entry.source_url" class="badge stamp" :href="node.entry.source_url" target="_blank" rel="noopener">{{ node.entry.source_label ?? "Quelle" }}</a>
              <span v-else-if="node.entry.id !== MOVEDAY_ID && isCustom(node.entry.id)" class="badge custom">Eigene Aufgabe</span>
              <span v-else-if="node.entry.id !== MOVEDAY_ID" class="badge missing">Quelle fehlt</span>

              <textarea
                v-if="openNoteId === node.entry.id"
                class="note-input"
                :data-note-input="node.entry.id"
                :value="userNotes[node.entry.id] ?? ''"
                rows="2"
                placeholder="Notiz - z. B. Aktenzeichen, Ansprechpartner, Telefonnummer"
                @keydown.esc="commitNote(node.entry.id, ($event.target as HTMLTextAreaElement).value)"
                @blur="commitNote(node.entry.id, ($event.target as HTMLTextAreaElement).value)"
              ></textarea>
              <p
                v-else-if="userNotes[node.entry.id]"
                class="note"
                tabindex="0"
                role="button"
                @click="openNote(node.entry.id)"
                @keydown.enter="openNote(node.entry.id)"
              >
                {{ userNotes[node.entry.id] }}
              </p>

              <p v-if="!doneIds[node.entry.id] && node.entry.collision" class="flag">Fällt auf {{ node.entry.collision }} - Ämter geschlossen.</p>
              <p v-else-if="!doneIds[node.entry.id] && node.entry.weekend" class="flag">Fällt auf ein Wochenende.</p>
            </div>
          </div>
        </template>
      </div>

      <button type="button" class="add-end" @click="addTaskAtEnd">+ Eigene Aufgabe hinzufügen</button>
      <p v-if="lastDeleted" class="undo">„{{ lastDeleted.label }}" entfernt. <button type="button" @click="undoDelete">Rückgängig</button></p>

      <div v-if="unscheduled.length > 0" class="unscheduled">
        <h2>Noch nicht terminiert</h2>
        <p class="hint">Diese Fristen sind noch nicht recherchiert, deshalb fehlt ihr Zeitpunkt.</p>
        <ul>
          <li v-for="entry in unscheduled" :key="entry.id">
            <span class="label">{{ entry.label }}</span>
            <span class="badge missing">Quelle fehlt</span>
          </li>
        </ul>
      </div>

      <div class="actions">
        <p>Änderungen gelten nur in diesem Tab und werden beim Neuladen zurückgesetzt. Fristen ohne Quelle bleiben vorläufig.</p>
        <button type="button" @click="print">Checkliste drucken</button>
      </div>
    </template>
    <p v-else class="hint">Umzugstag eingeben, um den Zeitplan zu sehen.</p>
  </div>
</template>

<style scoped>
.umzug-planer {
  max-width: 54rem;
  /* Secondary "official stamp" color, only for provenance (sourced badges),
    the move-day anchor, and edit affordances - the site's single red accent
    stays the only interactive/warning color, this is additive. */
  --stamp: #3b3b8f;
}
@media (prefers-color-scheme: dark) {
  .umzug-planer {
    --stamp: #9a9aec;
  }
}
:global(:root[data-theme="dark"]) .umzug-planer {
  --stamp: #9a9aec;
}
:global(:root[data-theme="light"]) .umzug-planer {
  --stamp: #3b3b8f;
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
}
.field span {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.7rem;
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
  font-size: 1.05rem;
  font-weight: 500;
}
.field select:disabled {
  opacity: 1;
  color: inherit;
  cursor: default;
}
.field input:focus-visible,
.field select:focus-visible {
  outline: 2px solid var(--stamp);
  outline-offset: 3px;
}
@media (max-width: 40rem) {
  .form {
    grid-template-columns: 1fr 1fr;
  }
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 2rem;
  margin: 1.5rem 0 0.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--line);
}
.stat {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.stat .k {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
}
.stat .v {
  font-weight: 700;
  font-size: 1.5rem;
}

.scalenote {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.9rem 8.5rem;
}
.rail {
  position: relative;
  margin: 0.5rem 0 0;
  padding: 0 0 0 8.5rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 7rem;
  top: 0.4rem;
  bottom: 0.4rem;
  width: 1px;
  background: var(--line);
}
.gap {
  position: relative;
}
.gap-add {
  position: absolute;
  left: -1.95rem;
  top: 50%;
  transform: translateY(-50%);
  width: 1.15rem;
  height: 1.15rem;
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
  transition: opacity 0.12s;
}
.gap:hover .gap-add,
.gap-add:focus-visible {
  opacity: 1;
}
.gap-add:hover {
  border-style: solid;
  border-color: var(--stamp);
  color: var(--stamp);
}
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
.item.moveday .dot {
  width: 0.8rem;
  height: 0.8rem;
  left: -1.95rem;
  background: var(--stamp);
  border-color: var(--stamp);
}
.item.past .dot {
  border-color: var(--muted);
  background: var(--muted);
}
.when {
  position: absolute;
  left: -8.3rem;
  top: 0.55rem;
  width: 6.1rem;
  text-align: right;
  font-family: var(--font-mono);
}
.when b {
  display: block;
  font-size: 0.92rem;
  line-height: 1.3;
}
.when span {
  display: block;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.3;
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 0.7rem 0.9rem;
  margin-bottom: 0.4rem;
}
.item.moveday .card {
  border-color: var(--stamp);
  border-width: 1.5px;
}
.item.past .card {
  opacity: 0.6;
}
.item.done .card {
  opacity: 0.65;
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
  border: 1px solid var(--stamp);
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
  color: #fff;
}
.check[aria-pressed="true"] {
  background: var(--stamp);
  border-color: var(--stamp);
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
  border-color: var(--stamp);
  color: var(--stamp);
  background: color-mix(in srgb, var(--stamp) 10%, transparent);
}
.badge.custom {
  border-color: var(--line);
  color: var(--muted);
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
  background: color-mix(in srgb, var(--stamp) 6%, var(--paper-raised));
  border-left: 2px solid var(--line);
  font-size: 0.85rem;
  color: var(--ink);
  white-space: pre-wrap;
  cursor: text;
}
.flag {
  margin-top: 0.5rem !important;
  padding: 0.4rem 0.6rem;
  border-left: 2px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--ink) !important;
  font-size: 0.85rem !important;
}

.badge.missing {
  border-color: var(--line);
  color: var(--muted);
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
  border-color: var(--stamp);
  color: var(--stamp);
}
.undo {
  margin-top: 0.9rem;
  font-size: 0.85rem;
  color: var(--muted);
}
.undo button {
  background: none;
  border: 0;
  color: var(--stamp);
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

.actions {
  margin-top: 2.5rem;
  padding: 1rem 1.2rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}
.actions p {
  margin: 0;
  color: var(--muted);
  font-size: 0.88rem;
  max-width: 32rem;
}

@media (max-width: 32rem) {
  .rail {
    padding-left: 1.4rem;
  }
  .rail::before {
    left: 0.2rem;
  }
  .gap-add {
    left: -0.15rem;
  }
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
  .item.moveday .dot {
    left: -0.1rem;
  }
}

@media print {
  .form,
  .gap-add,
  .tools,
  .add-end,
  .undo,
  .actions {
    display: none;
  }
  .check {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
