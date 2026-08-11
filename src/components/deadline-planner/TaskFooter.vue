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
  <!-- Below the hairline: what the card assumes and where it got it from.
    Never the action, so the eye can stop at the button above. -->
  <div class="footer">
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

    <!-- One provenance affordance: the paragraph lives inside the derivation
      it is the basis for, not next to it as a second offer. -->
    <details v-if="entry.derivation?.length" class="derivation">
      <summary>Wie wird das berechnet?</summary>
      <ol>
        <li v-for="step in entry.derivation" :key="step.step">
          {{ step.label }}
        </li>
      </ol>
      <p class="src">
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
    </details>

    <p v-else class="src">
      Grundlage:
      <a
        v-if="entry.source_url"
        :href="entry.source_url"
        target="_blank"
        rel="noopener"
        >{{ entry.source_label ?? "Quelle" }}</a
      >
      <span v-else>{{ fallbackLabel() }}</span>
    </p>
  </div>
</template>

<style scoped>
.footer {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.35rem 1.2rem;
  margin-top: 0.8rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--line);
}
.footer:empty {
  display: none;
}

/* Wraps rather than truncates: an option nobody can finish reading is worse
  than one on a second line. */
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
  padding: 0.15rem 0.5rem;
  white-space: nowrap;
}
/* A setting, so it never outweighs the action above it: the chosen side is
  marked by ink and a border, not by a fill. */
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
.derivation .src {
  margin-top: 0.5rem;
}
.derivation .src a {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}

.src {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--muted);
}
.src a {
  color: var(--accent);
}
</style>
