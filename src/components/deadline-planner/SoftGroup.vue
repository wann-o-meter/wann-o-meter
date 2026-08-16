<script setup lang="ts">
import { Check } from "lucide-vue-next";
import CardMenu from "./CardMenu.vue";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import type { MenuItem } from "./task-card";
import { EyeOff } from "lucide-vue-next";

defineProps<{ entries: ScheduleEntry[]; doneIds: Record<string, boolean> }>();
const emit = defineEmits<{
  (e: "toggle-done", id: string): void;
  (e: "hide", entry: ScheduleEntry): void;
}>();

const menu = (entry: ScheduleEntry): MenuItem[] => [
  {
    label: "Nicht relevant für mich",
    icon: EyeOff,
    onSelect: () => emit("hide", entry),
  },
];
</script>

<template>
  <section v-if="entries.length > 0" class="soft">
    <h2 class="section">Ohne feste Frist</h2>
    <p class="lede">
      Diese Schritte gehören dazu, aber kein Gesetz sagt wann. Wir erfinden dafür
      auch kein Datum.
    </p>
    <ul>
      <li v-for="entry in entries" :key="entry.id" :data-entry-id="entry.id">
        <button
          type="button"
          class="check"
          :aria-pressed="!!doneIds[entry.id]"
          :aria-label="`${entry.label} als erledigt markieren`"
          @click="emit('toggle-done', entry.id)"
        >
          <Check v-if="doneIds[entry.id]" :size="11" />
        </button>
        <div class="body">
          <p class="label">{{ entry.label }}</p>
          <p v-if="entry.note" class="note">{{ entry.note }}</p>
        </div>
        <CardMenu :items="menu(entry)" />
      </li>
    </ul>
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
  margin: 0 0 0.75rem;
  color: var(--muted);
  font-size: var(--fs-sm);
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--line);
}
/* Quieter than a dated card: no raised surface, no accent, no numbers. */
.body {
  flex: 1;
  min-width: 0;
}
.label {
  margin: 0;
  font-size: var(--fs-sm);
}
li:has(.check[aria-pressed="true"]) .label {
  text-decoration: line-through;
  color: var(--muted);
}
.note {
  margin: 0.15rem 0 0;
  color: var(--muted);
  font-size: var(--fs-xs);
}
.check {
  position: relative;
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  margin-top: 0.15rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: var(--paper);
  color: var(--paper);
  cursor: pointer;
}
.check[aria-pressed="true"] {
  background: var(--muted);
  border-color: var(--muted);
}
.check::before {
  content: "";
  position: absolute;
  inset: -0.6rem;
}
:deep(.tools) {
  opacity: 0;
}
li:hover :deep(.tools),
:deep(.tools[open]),
:deep(.tools:focus-within) {
  opacity: 1;
}
@media (hover: none) {
  :deep(.tools) {
    opacity: 1;
  }
}
</style>
