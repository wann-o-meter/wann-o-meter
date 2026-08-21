<script setup lang="ts">
import { computed, onMounted, ref, useTemplateRef } from "vue";
import { X } from "lucide-vue-next";

const PRESET_TASKS = [
  "Bank- und Versicherungsadresse ändern",
  "Arbeitgeber über neue Adresse informieren",
  "Vereinsmitgliedschaft ummelden",
  "Zeitungs- oder Zeitschriftenabo ummelden",
  "Streaminganbieter und Online-Konten aktualisieren",
  "Kindergarten oder Schule informieren",
  "Hausarzt und Zahnarzt wechseln",
  "Tierarzt informieren oder wechseln",
];

const emit = defineEmits<{
  (e: "pick", label: string, date: string): void;
  (e: "close"): void;
}>();

const query = ref("");
// Empty means the plan picks the day: the end of the list, where a task nobody
// dated can do no harm.
const date = ref("");
const inputEl = useTemplateRef<HTMLInputElement>("inputEl");
onMounted(() => inputEl.value?.focus());

// The same field filters the list and writes a task of its own, so nobody has
// to decide up front which of the two they are doing.
const matches = computed(() => {
  const q = query.value.trim().toLowerCase();
  return q
    ? PRESET_TASKS.filter((t) => t.toLowerCase().includes(q))
    : PRESET_TASKS;
});

function submit() {
  const label = query.value.trim();
  if (label) emit("pick", label, date.value);
}
</script>

<template>
  <div class="task-add">
    <form class="task-add-row" @submit.prevent="submit">
      <input
        ref="inputEl"
        v-model="query"
        type="text"
        class="task-add-input"
        placeholder="Eigene Aufgabe"
        aria-label="Eigene Aufgabe"
        @keydown.esc="emit('close')"
      />
      <button type="submit" class="btn-secondary" :disabled="!query.trim()">
        Hinzufügen
      </button>
      <button
        type="button"
        class="icon-button"
        aria-label="Abbrechen"
        @click="emit('close')"
      >
        <X :size="14" />
      </button>
    </form>
    <label class="task-add-date t-meta">
      <span>Termin</span>
      <input v-model="date" type="date" />
    </label>
    <ul v-if="matches.length > 0" class="task-add-presets">
      <li v-for="preset in matches" :key="preset">
        <button type="button" @click="emit('pick', preset, date)">
          {{ preset }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.task-add {
  padding: var(--s-2);
  background: var(--paper-raised);
}
.task-add-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
/* Takes the room the two buttons leave, and no more. */
.task-add-input {
  flex: 1 1 8rem;
  min-width: 0;
}
.task-add-date {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.5rem;
  color: var(--muted);
}
.task-add-presets {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
  max-height: 11rem;
  overflow-y: auto;
}
.task-add-presets button {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: var(--t-meta);
  padding: 0.4rem 0.5rem;
  border-radius: 2px;
  cursor: pointer;
}
.task-add-presets button:hover,
.task-add-presets button:focus-visible {
  background: var(--tint-accent);
  color: var(--accent);
}

@media print {
  .task-add {
    display: none;
  }
}
</style>
