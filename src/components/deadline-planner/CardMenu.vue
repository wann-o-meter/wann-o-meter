<script setup lang="ts">
import { ref } from "vue";
import { Ellipsis } from "lucide-vue-next";
import type { MenuItem } from "./task-card";

defineProps<{ items: MenuItem[] }>();

const root = ref<HTMLDetailsElement | null>(null);

function select(item: MenuItem) {
  if (root.value) root.value.open = false;
  item.onSelect();
}
function closeOnBlur(e: FocusEvent) {
  const menu = e.currentTarget as HTMLDetailsElement;
  if (!menu.contains(e.relatedTarget as Node)) menu.open = false;
}
</script>

<template>
  <details ref="root" class="tools" @focusout="closeOnBlur">
    <summary class="icon-button" aria-label="Aktionen" title="Aktionen">
      <Ellipsis :size="14" />
    </summary>
    <div class="tool-menu">
      <button
        v-for="item in items"
        :key="item.label"
        type="button"
        :class="{ danger: item.danger }"
        @click="select(item)"
      >
        <component :is="item.icon" :size="12" /> {{ item.label }}
      </button>
    </div>
  </details>
</template>

<style scoped>
.tools {
  position: relative;
  flex-shrink: 0;
  transition: opacity 0.12s;
}
.tools summary {
  position: relative;
  list-style: none;
}
.tools summary::-webkit-details-marker {
  display: none;
}
.tools summary::after {
  content: "";
  position: absolute;
  inset: -0.5rem;
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
  border-radius: var(--r-sm);
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
  font-size: var(--t-meta);
  text-align: left;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
}
.tool-menu button:hover {
  background: var(--paper);
}
.tool-menu .danger {
  color: var(--overdue);
}

@media print {
  .tools {
    display: none;
  }
}
</style>
