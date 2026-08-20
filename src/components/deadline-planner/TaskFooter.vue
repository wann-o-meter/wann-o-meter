<script setup lang="ts">
import { ArrowUpRight } from "lucide-vue-next";
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { sourceLabel } from "../../../lib/offset-label";

const props = defineProps<{
  entry: ScheduleEntry;
  isCustom: boolean;
}>();

const fallbackLabel = () =>
  props.isCustom && !props.entry.derivation?.length
    ? "Eigene Aufgabe"
    : sourceLabel(props.entry);
</script>

<template>
  <div class="footer">
    <div class="controls">
      <details v-if="entry.derivation?.length" class="derivation">
        <summary>Wie wird das berechnet?</summary>
        <ol>
          <li v-for="step in entry.derivation" :key="step.step">
            {{ step.label }}
          </li>
        </ol>
      </details>
      <details v-if="entry.documents?.length" class="derivation">
        <summary>Was brauche ich dafür?</summary>
        <ul>
          <li v-for="doc in entry.documents" :key="doc">{{ doc }}</li>
        </ul>
      </details>
    </div>

    <p v-if="entry.authority" class="where">Wo? {{ entry.authority }}</p>

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

@media (min-width: 40rem) {
  }

.where {
  margin: 0.4rem 0 0;
  font-size: var(--t-meta);
  color: var(--muted);
}
.derivation {
  font-size: var(--t-meta);
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
  font-size: var(--t-meta);
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
