<script setup lang="ts">
import { computed, ref } from "vue";
import { formatDate, formatDateWithWeekday, toDate } from "../../lib/format-date";
import { computeUmzugSchedule } from "../../lib/umzug";
import type { UmzugDeadline, UmzugKommuneData, UmzugScheduleEntry } from "../../lib/umzug";

const props = defineProps<{
  kommunen: UmzugKommuneData[];
  defaultSlug?: string;
}>();

const MOVEDAY_ID = "__moveday";
const moveDate = ref("");
const selectedSlug = ref(props.defaultSlug && props.kommunen.some((k) => k.slug === props.defaultSlug) ? props.defaultSlug : props.kommunen[0]?.slug);

const selected = computed(() => props.kommunen.find((k) => k.slug === selectedSlug.value) ?? props.kommunen[0]);

// The move day itself is UI chrome, not a researched fact - it needs no
// source and is definitionally correct, so it's injected here rather than
// stored in data/umzug/ next to entries that do need provenance.
const schedule = computed<UmzugScheduleEntry[]>(() => {
  if (!moveDate.value || !selected.value) return [];
  const withAnchor: UmzugDeadline[] = [
    { id: MOVEDAY_ID, label: "Umzugstag", offset_days: 0, source_url: null },
    ...selected.value.deadlines,
  ];
  return computeUmzugSchedule(moveDate.value, withAnchor, "DE", selected.value.state);
});

const timeline = computed(() => schedule.value.filter((e) => e.date !== null));
const unscheduled = computed(() => schedule.value.filter((e) => e.date === null));
const knownDeadlines = computed(() => timeline.value.filter((e) => e.id !== MOVEDAY_ID));

const stats = computed(() => {
  const warnings = timeline.value.filter((e) => e.weekend || e.collision).length;
  const first = knownDeadlines.value[0];
  return {
    count: selected.value?.deadlines.length ?? 0,
    first: first ? formatDate(first.date!).replace(/\.\d{4}$/, "") : "—",
    lead: first ? `${Math.abs(first.offset_days!)} Tage` : "—",
    warnings: warnings > 0 ? warnings : timeline.value.length > 0 ? 0 : "—",
  };
});

// Gap-based spacing (capped): a two-day gap and a two-month gap should look
// like the busy stretch and the quiet stretch they are, not identical rows.
function gapMargin(index: number): string {
  if (index === 0) return "0";
  const days = Math.round((toDate(timeline.value[index].date!).getTime() - toDate(timeline.value[index - 1].date!).getTime()) / 86400000);
  return `${Math.min(96, Math.max(14, days * 2.6))}px`;
}

function offsetLabel(offsetDays: number | null): string {
  if (offsetDays === null) return "Frist noch nicht recherchiert";
  if (offsetDays === 0) return "am Umzugstag";
  return offsetDays < 0 ? `${Math.abs(offsetDays)} Tage vorher` : `${offsetDays} Tage danach`;
}

function isPast(date: string): boolean {
  return date < new Date().toISOString().slice(0, 10);
}

// `window` is not in template scope.
function print() {
  window.print();
}
</script>

<template>
  <div class="umzug-planer">
    <div class="form">
      <label class="field">
        <span>Ort</span>
        <select v-model="selectedSlug">
          <option v-for="k in kommunen" :key="k.slug" :value="k.slug">{{ k.name }}</option>
        </select>
      </label>
      <label class="field">
        <span>Umzugstag</span>
        <input v-model="moveDate" type="date" aria-label="Umzugstag" />
      </label>
    </div>

    <div v-if="moveDate" class="summary">
      <div class="stat"><span class="k">Fristen</span><span class="v">{{ stats.count }}</span></div>
      <div class="stat"><span class="k">Erste Frist</span><span class="v">{{ stats.first }}</span></div>
      <div class="stat"><span class="k">Vorlauf nötig</span><span class="v">{{ stats.lead }}</span></div>
      <div class="stat"><span class="k">Warnungen</span><span class="v">{{ stats.warnings }}</span></div>
    </div>

    <template v-if="moveDate">
      <ol class="rail">
        <li
          v-for="(entry, i) in timeline"
          :key="entry.id"
          class="item"
          :class="{ moveday: entry.id === MOVEDAY_ID, past: isPast(entry.date!) }"
          :style="{ marginTop: gapMargin(i) }"
        >
          <span class="dot"></span>
          <div class="when">
            <b>{{ formatDateWithWeekday(entry.date!) }}</b>
            <span>{{ offsetLabel(entry.offset_days) }}</span>
          </div>
          <div class="card">
            <h3>{{ entry.label }}</h3>
            <p v-if="entry.note">{{ entry.note }}</p>
            <a v-if="entry.source_url" class="badge" :href="entry.source_url" target="_blank" rel="noopener">{{ entry.source_label ?? "Quelle" }}</a>
            <span v-else-if="entry.id !== MOVEDAY_ID" class="badge missing">Quelle fehlt</span>
            <p v-if="entry.collision" class="flag">Fällt auf {{ entry.collision }} - Ämter geschlossen.</p>
            <p v-else-if="entry.weekend" class="flag">Fällt auf ein Wochenende.</p>
          </div>
        </li>
      </ol>

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
        <p>Der Plan bleibt vorläufig, bis jede Frist eine Quelle hat. Kalender-Abo folgt danach.</p>
        <button type="button" @click="print">Checkliste drucken</button>
      </div>
    </template>
    <p v-else class="hint">Umzugstag eingeben, um den Zeitplan zu sehen.</p>
  </div>
</template>

<style scoped>
.umzug-planer {
  max-width: 44rem;
}
.form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.field {
  display: block;
  background: var(--paper-raised);
  padding: 0.6rem 0.8rem;
}
.field span {
  display: block;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 0.25rem;
}
.field input,
.field select {
  display: block;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 0;
  font-size: 1rem;
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
  font-weight: 600;
  font-size: 1.25rem;
}

.rail {
  position: relative;
  list-style: none;
  margin: 2.25rem 0 0;
  padding: 0 0 0 6.5rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 5.25rem;
  top: 0.4rem;
  bottom: 0.4rem;
  width: 1px;
  background: var(--line);
}
.item {
  position: relative;
}
.dot {
  position: absolute;
  left: -1.65rem;
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
  left: -1.78rem;
  background: var(--ink);
  border-color: var(--ink);
}
.item.past .dot {
  border-color: var(--muted);
  background: var(--muted);
}
.when {
  position: absolute;
  left: -6.5rem;
  top: 0.75rem;
  width: 5.2rem;
  text-align: right;
  font-size: 0.8rem;
}
.when b {
  display: block;
  font-size: 0.82rem;
}
.when span {
  color: var(--muted);
  font-size: 0.72rem;
}
.card {
  background: var(--paper-raised);
  border: 1px solid var(--line);
  padding: 0.7rem 0.9rem;
  margin-bottom: 0.4rem;
}
.item.moveday .card {
  border-color: var(--ink);
}
.item.past .card {
  opacity: 0.6;
}
.card h3 {
  margin: 0 0 0.2rem;
  font-size: 1rem;
}
.card p {
  margin: 0;
  color: var(--muted);
  font-size: 0.88rem;
}
.card .badge {
  margin-top: 0.5rem;
  margin-left: 0;
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
  .actions {
    display: none;
  }
}
</style>
