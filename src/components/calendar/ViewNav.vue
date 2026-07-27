<script setup lang="ts">
// The prev/title/next header every non-year template carries. Shared so the
// three (soon more) of them line up pixel-wise without copying the CSS -
// each view still owns what "prev" means for it.
import { ChevronLeft, ChevronRight } from "lucide-vue-next";

defineProps<{ title: string; prevDisabled?: boolean; nextDisabled?: boolean }>();
const emit = defineEmits<{ (e: "prev"): void; (e: "next"): void }>();
</script>

<template>
  <div class="view-nav">
    <button type="button" :disabled="prevDisabled" aria-label="Zurück" @click="emit('prev')">
      <ChevronLeft :size="18" />
    </button>
    <h2>{{ title }}</h2>
    <button type="button" :disabled="nextDisabled" aria-label="Weiter" @click="emit('next')">
      <ChevronRight :size="18" />
    </button>
  </div>
</template>

<style scoped>
.view-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-bottom: 1rem;
}
.view-nav h2 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 500;
  min-width: 14ch;
  text-align: center;
}
/* 24px floor is WCAG 2.5.8 / Lighthouse's touch-target minimum - a 16px icon
   plus 0.15rem of padding came to 23x23. */
.view-nav button {
  cursor: pointer;
  background: none;
  border: none;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  min-height: 24px;
  padding: 0.15rem;
}
.view-nav button:disabled {
  color: var(--muted);
  cursor: default;
  opacity: 0.4;
}
.view-nav button:not(:disabled):hover {
  color: var(--accent);
}
</style>
