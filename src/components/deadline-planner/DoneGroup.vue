<script setup lang="ts">
import { Check } from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";

defineProps<{ entries: ScheduleEntry[] }>();
defineEmits<{ (e: "reopen", id: string): void }>();
</script>

<template>
  <details v-if="entries.length > 0" class="done-group">
    <summary>Erledigte Aufgaben</summary>
    <ul>
      <li v-for="entry in entries" :key="entry.id">
        <button
          type="button"
          class="check"
          aria-pressed="true"
          aria-label="Wieder öffnen"
          @click="$emit('reopen', entry.id)"
        >
          <Check :size="11" />
        </button>
        <span>{{ entry.label }}</span>
      </li>
    </ul>
  </details>
</template>

<style scoped>
.done-group {
  margin-top: 1rem;
  font-size: var(--t-meta);
}
.done-group summary {
  cursor: pointer;
  padding: 0.5rem 0;
  color: var(--muted);
}
.done-group ul {
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.done-group li {
  display: flex;
  align-items: center;
  min-height: 2.4rem;
  gap: 0.6rem;
  color: var(--muted);
  text-decoration: line-through;
}
.check {
  position: relative;
  flex-shrink: 0;
  width: 1.1rem;
  height: 1.1rem;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid var(--done);
  background: var(--done);
  color: var(--paper-raised);
}
.check::before {
  content: "";
  position: absolute;
  inset: -0.6rem;
}
@media (pointer: coarse) {
  .check::before {
    inset: calc((1.1rem - 44px) / 2);
  }
}
</style>
