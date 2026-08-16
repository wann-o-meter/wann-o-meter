<script setup lang="ts">
import { ArrowUpRight } from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { sourceLabel } from "../../../lib/offset-label";

const props = defineProps<{
  entry: ScheduleEntry;
  isCustom: boolean;
  deferred: boolean;
}>();

defineEmits<{ (e: "toggle-defer"): void }>();

const fallbackLabel = () =>
  props.isCustom && !props.entry.derivation?.length
    ? "Eigene Aufgabe"
    : sourceLabel(props.entry);
</script>

<template>
  <div class="footer">
    <div class="controls">
      <div
        v-if="entry.offset_rule || deferred"
        class="defer"
        role="radiogroup"
        aria-label="Mietende"
      >
        <span class="defer-label">Mietende</span>
        <button
          type="button"
          role="radio"
          :aria-checked="!deferred"
          @click="deferred && $emit('toggle-defer')"
        >
          Ende des Umzugsmonats
        </button>
        <button
          type="button"
          role="radio"
          :aria-checked="deferred"
          @click="!deferred && $emit('toggle-defer')"
        >
          Einen Monat später
        </button>
      </div>

      <details v-if="entry.derivation?.length" class="derivation">
        <summary>Wie wird das berechnet?</summary>
        <ol>
          <li v-for="step in entry.derivation" :key="step.step">
            {{ step.label }}
          </li>
        </ol>
      </details>
    </div>

    <p class="src">
      <a
        v-if="entry.kind !== 'soft'"
        class="frist"
        :href="`/frist/${entry.id}/`"
        >Frist im Detail</a
      >
      Grundlage:
      <a
        v-if="entry.source_url"
        :href="entry.source_url"
        target="_blank"
        rel="noopener"
        >{{ entry.source_label ?? "Quelle" }} <ArrowUpRight :size="12"
      /></a>
      <span v-else>{{ fallbackLabel() }}</span>
    </p>
  </div>
</template>

<style scoped>
/* Controls above the divider, where the plan comes from always below it. */
.footer {
  margin-top: 0.6rem;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 1.2rem;
}
.controls:empty {
  display: none;
}

.defer {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.3rem;
}
.defer-label {
  font-size: var(--fs-xs);
  color: var(--muted);
}
.defer button {
  font-size: var(--fs-xs);
  min-height: 2.2rem;
  padding: 0.35rem 0.7rem;
  white-space: nowrap;
}
@media (min-width: 40rem) {
  .defer button {
    min-height: 0;
    padding: 0.15rem 0.5rem;
  }
}
.defer button[aria-checked="true"] {
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}
.defer button[aria-checked="false"] {
  color: var(--muted);
}

.derivation {
  font-size: var(--fs-xs);
  color: var(--muted);
}
.derivation summary {
  cursor: pointer;
  padding: 0.4rem 0;
  color: var(--muted);
}
.derivation summary:hover {
  color: var(--accent);
}
.derivation ol {
  margin: 0.5rem 0 0;
  padding-left: 1.5rem;
}
.derivation li {
  margin-bottom: 0.25rem;
}
.src {
  margin: 0.4rem 0 0;
  padding-top: 0.4rem;
  border-top: 1px solid var(--line);
  font-size: var(--fs-xs);
  color: var(--muted);
}
.src .frist {
  margin-right: 0.6rem;
}
.src a {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  color: var(--accent);
}

@media print {
  /* The Grundlage stays, the controls that change it do not. */
  .controls {
    display: none;
  }
  .src {
    border-top: 0;
    padding-top: 0;
    color: #444;
  }
  .src a {
    color: inherit;
  }
  .src svg {
    display: none;
  }
}
</style>
