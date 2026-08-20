<script setup lang="ts">
import type { ScheduleEntry } from "../../../lib/deadline-plan";
import { sourceLabel } from "../../../lib/offset-label";

const props = defineProps<{
  entry: ScheduleEntry;
  anchorDate: string;
  isCustom: boolean;
}>();

// The Frist's own page recalculates from a date. Carrying the one already
// entered here means it opens with the answer instead of an empty field.
const fristHref = () =>
  `/frist/${props.entry.id}/${props.anchorDate ? `#date=${props.anchorDate}` : ""}`;

const fallbackLabel = () =>
  props.isCustom && !props.entry.derivation?.length
    ? "Eigene Aufgabe"
    : sourceLabel(props.entry);
</script>

<template>
  <div class="footer">
    <div class="controls">
      <details v-if="entry.documents?.length" class="documents">
        <summary>Was brauche ich dafür?</summary>
        <ul>
          <li v-for="doc in entry.documents" :key="doc">{{ doc }}</li>
        </ul>
      </details>
    </div>

    <p v-if="entry.authority" class="where">Wo? {{ entry.authority }}</p>

    <!-- The statute itself is a pill in the corner of the row. What is left
    down here is the page about it, and the honest note where there is none. -->
    <p class="src">
      <a
        v-if="entry.kind !== 'soft'"
        class="frist"
        :href="fristHref()"
        data-astro-reload
        >Frist im Detail</a
      >
      <span v-if="!entry.source_url">Grundlage: {{ fallbackLabel() }}</span>
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
.documents {
  font-size: var(--t-meta);
  color: var(--muted);
}
.documents summary {
  cursor: pointer;
  padding: 0.4rem 0;
  color: var(--muted);
}
.documents summary:hover {
  color: var(--accent);
}
.documents ul {
  margin: 0.5rem 0 0;
  padding-left: 1.5rem;
}
.documents li {
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
