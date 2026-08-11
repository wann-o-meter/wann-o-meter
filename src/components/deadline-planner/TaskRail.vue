<script setup lang="ts">
import { Plus } from "lucide-vue-next";
import TaskCard from "./TaskCard.vue";
import TaskPicker from "./TaskPicker.vue";
import { taskCtaFor } from "./task-cta";
import { isPast } from "../../../lib/today";
import type { TaskStore } from "./task-store";
import type { TaskPicker as Picker } from "./useTaskPicker";

defineProps<{
  // usePlannerSchedule's railNodes, anchor and trailing gaps already removed
  nodes: { kind: string; [key: string]: any }[];
  anchorDate: string;
  nextUpId: string | null;
  deferred: boolean;
  hoveredId: string | null;
  store: TaskStore;
  picker: Picker;
}>();

defineEmits<{
  (e: "hover", id: string | null): void;
  (e: "toggle-done", id: string): void;
  (e: "toggle-defer"): void;
}>();
</script>

<template>
  <div class="rail">
    <template
      v-for="node in nodes"
      :key="node.kind === 'gap' ? node.id : node.entry.id"
    >
      <div
        v-if="node.kind === 'gap'"
        class="gap"
        :title="`${node.bufferDays} Tage Puffer`"
        :style="{ height: `${node.heightPx}px` }"
      >
        <button
          type="button"
          class="gap-add"
          title="Aufgabe hier einfügen"
          aria-label="Aufgabe hier einfügen"
          @click="
            picker.toggle({
              kind: 'gap',
              id: node.id,
              afterOffset: node.afterOffset,
              beforeOffset: node.beforeOffset,
            })
          "
        >
          <Plus :size="12" />
        </button>
        <TaskPicker
          v-if="
            picker.isOpen({
              kind: 'gap',
              id: node.id,
              afterOffset: node.afterOffset,
              beforeOffset: node.beforeOffset,
            })
          "
          @pick-preset="picker.pick($event)"
          @pick-blank="picker.pick()"
        />
      </div>

      <TaskCard
        v-else
        :class="{ focused: hoveredId === node.entry.id }"
        :entry="node.entry"
        :anchor-date="anchorDate"
        :is-past="isPast(node.entry.date!)"
        :done="!!store.doneIds[node.entry.id]"
        :is-custom="store.isCustom(node.entry.id)"
        :is-next="node.entry.id === nextUpId"
        :cta="taskCtaFor(node.entry.id)"
        :note="store.userNotes[node.entry.id]"
        :attachment="store.attachments[node.entry.id]"
        :deferred="deferred"
        :editor="store.editorFor(node.entry.id)"
        @update:editor="store.setEditor(node.entry.id, $event)"
        @update="store.applyPatch(node.entry, $event)"
        @delete="store.deleteEntry(node.entry)"
        @toggle-done="$emit('toggle-done', node.entry.id)"
        @toggle-defer="$emit('toggle-defer')"
        @mouseenter="$emit('hover', node.entry.id)"
        @mouseleave="$emit('hover', null)"
      />
    </template>
  </div>
</template>

<style scoped>
.rail {
  /* Distance from a card's left edge to the spine, read by TaskCard's dot. */
  --rail-gap: 1.4rem;
  position: relative;
  padding-left: 2.2rem;
}
.rail::before {
  content: "";
  position: absolute;
  left: 0.5rem;
  top: 0.6rem;
  bottom: 0.6rem;
  width: 1px;
  background: var(--line);
}
/* The buffer between two deadlines, kept as real height so the list breathes
  in proportion to the plan, plus the place a new task is inserted. The
  negative margin lets its "+" sit on the spine, in the rail's own padding. */
.gap {
  position: relative;
  margin-left: -2.2rem;
  padding-left: 2.2rem;
}
.gap-add {
  position: absolute;
  left: 0.5rem;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 1.3rem;
  height: 1.3rem;
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
  transition: opacity 0.1s;
}
.gap:hover .gap-add,
.gap-add:focus-visible {
  opacity: 1;
}
.gap-add:hover {
  border-style: solid;
  border-color: var(--accent);
  color: var(--accent);
}
.gap :deep(.task-picker) {
  left: 1.5rem;
  top: calc(50% + 0.5rem);
}

@media (max-width: 40rem) {
  .rail {
    --rail-gap: 0.95rem;
    padding-left: 1.5rem;
  }
  .rail::before,
  .gap-add {
    left: 0.25rem;
  }
  .gap {
    margin-left: -1.5rem;
    padding-left: 1.5rem;
  }
}

@media print {
  .gap-add {
    display: none;
  }
}
</style>
