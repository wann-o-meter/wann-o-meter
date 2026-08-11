<script setup lang="ts">
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

defineEmits<{
  (e: "pick-preset", label: string): void;
  (e: "pick-blank"): void;
}>();
</script>

<template>
  <div class="task-picker" role="menu" aria-label="Aufgabe auswählen">
    <button
      v-for="preset in PRESET_TASKS"
      :key="preset"
      type="button"
      class="task-picker-option"
      role="menuitem"
      @click="$emit('pick-preset', preset)"
    >
      {{ preset }}
    </button>
    <button
      type="button"
      class="task-picker-option task-picker-blank"
      role="menuitem"
      @click="$emit('pick-blank')"
    >
      + Eigene Aufgabe
    </button>
  </div>
</template>

<style scoped>
.task-picker {
  position: absolute;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  min-width: 15rem;
  max-width: 19rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-lg);
  padding: 0.25rem;
}
.task-picker-option {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: var(--fs-sm);
  padding: 0.5rem 0.5rem;
  cursor: pointer;
  border-radius: 2px;
}
.task-picker-option:hover,
.task-picker-option:focus-visible {
  background: var(--tint-accent);
  color: var(--accent);
}
.task-picker-blank {
  margin-top: 0.25rem;
  border-top: 1px solid var(--line);
  border-radius: 0;
  color: var(--muted);
  font-size: var(--fs-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.task-picker-blank:hover,
.task-picker-blank:focus-visible {
  color: var(--accent);
}

@media print {
  .task-picker {
    display: none;
  }
}
</style>
