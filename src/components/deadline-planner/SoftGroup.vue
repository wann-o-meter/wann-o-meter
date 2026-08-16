<script setup lang="ts">
import { computed } from "vue";
import TaskCard from "./TaskCard.vue";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import type { TaskStore } from "./task-store";

const props = defineProps<{ entries: ScheduleEntry[]; store: TaskStore }>();
defineEmits<{ (e: "toggle-done", id: string): void }>();

// No fixed day, but a clear order: what comes before the move, what happens on
// the day, what follows. The offset only sorts, it is never shown.
const PHASES = [
  {
    id: "vorher",
    title: "Vorher",
    lede: "Je früher, desto entspannter. Kein Gesetz gibt hier einen Tag vor.",
    of: (e: ScheduleEntry) => (e.offset_days ?? 0) < 0,
  },
  {
    id: "am-tag",
    title: "Am Tag selbst",
    lede: "Passiert, wenn es passiert.",
    of: (e: ScheduleEntry) => (e.offset_days ?? 0) === 0,
  },
  {
    id: "danach",
    title: "Danach",
    lede: "Bleibt liegen, bis du dazu kommst.",
    of: (e: ScheduleEntry) => (e.offset_days ?? 0) > 0,
  },
];

const groups = computed(() =>
  PHASES.map((phase) => ({
    ...phase,
    entries: props.entries
      .filter(phase.of)
      .slice()
      .sort((a, b) => (a.offset_days ?? 0) - (b.offset_days ?? 0)),
  })).filter((g) => g.entries.length > 0),
);
</script>

<template>
  <section v-if="groups.length > 0" class="soft">
    <h2 class="section">Ohne feste Frist</h2>
    <p class="lede">
      Diese Schritte gehören dazu, aber kein Gesetz sagt wann. Die Reihenfolge
      stimmt, ein Datum erfinden wir dafür nicht.
    </p>

    <div v-for="group in groups" :key="group.id" class="phase">
      <h3>
        {{ group.title }}
        <span class="count">{{ group.entries.length }}</span>
      </h3>
      <p class="phase-lede">{{ group.lede }}</p>
      <TaskCard
        v-for="entry in group.entries"
        :key="entry.id"
        undated
        :entry="entry"
        anchor-date=""
        :is-past="false"
        :done="!!store.doneIds[entry.id]"
        :is-custom="store.isCustom(entry.id)"
        :cta="null"
        :note="store.userNotes[entry.id]"
        :attachment="store.attachments[entry.id]"
        :deferred="false"
        :editor="store.editorFor(entry.id)"
        @update:editor="store.setEditor(entry.id, $event)"
        @update="store.applyPatch(entry, $event)"
        @hide="store.hideEntry(entry)"
        @toggle-done="$emit('toggle-done', entry.id)"
      />
    </div>
  </section>
</template>

<style scoped>
.soft {
  margin-top: 2rem;
}
.section {
  margin: 0 0 0.25rem;
  font-size: var(--fs-sm);
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}
.lede {
  max-width: 62ch;
  margin: 0 0 1.25rem;
  color: var(--muted);
  font-size: var(--fs-sm);
}
.phase {
  margin-bottom: 1.5rem;
}
.phase h3 {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0 0 0.15rem;
  font-size: var(--fs-md);
}
.count {
  font-size: var(--fs-xs);
  font-weight: 400;
  color: var(--muted);
}
.phase-lede {
  margin: 0 0 0.75rem;
  color: var(--muted);
  font-size: var(--fs-xs);
}
/* The cards are the same shape as a Frist card, only without the dated parts,
so the eye reads one list and not two systems. */
.phase :deep(.card) {
  margin-bottom: 0.6rem;
}
</style>
