<script setup lang="ts">
import { ref } from "vue";
import { Bookmark, BookmarkCheck, Download, Link2, Printer } from "lucide-vue-next";
import { downloadIcs } from "../../../lib/ics-download";
import type { ScheduleEntry } from "../../../lib/deadline-plan";

const props = defineProps<{
  entries: ScheduleEntry[];
  anchorDate: string;
  calendarName: string;
  fileSlug: string;
  kept: boolean;
}>();

defineEmits<{ (e: "toggleKept"): void }>();

const linkCopied = ref(false);
async function copyPlanLink() {
  try {
    await navigator.clipboard.writeText(window.location.href);
    linkCopied.value = true;
    setTimeout(() => (linkCopied.value = false), 2000);
  } catch {
  }
}

const exportIcs = () =>
  downloadIcs(
    props.entries,
    props.calendarName,
    props.fileSlug,
    props.anchorDate,
  );

const print = () => window.print();
</script>

<template>
  <div class="actions">
    <h2 class="section">Plan mitnehmen</h2>
    <div class="actions-buttons">
      <button type="button" :aria-pressed="kept" @click="$emit('toggleKept')">
        <component :is="kept ? BookmarkCheck : Bookmark" :size="14" />
        {{ kept ? "Plan nicht mehr merken" : "Plan merken" }}
      </button>
      <button type="button" @click="copyPlanLink">
        <Link2 :size="14" />
        {{ linkCopied ? "Kopiert" : "Plan-Link kopieren" }}
      </button>
      <button type="button" @click="exportIcs">
        <Download :size="14" /> Als ICS exportieren
      </button>
      <button type="button" @click="print">
        <Printer :size="14" /> Checkliste drucken
      </button>
    </div>
    <p>
      Der Link enthält Datum, Ort und Einstellungen. Häkchen, Notizen und eigene
      Aufgaben bleiben nur in diesem Browser, auf einem anderen Gerät ist der
      Plan wieder leer.
    </p>
  </div>
</template>

<style scoped>
.actions {
  margin-top: 1rem;
  padding: 1rem;
  background: var(--paper-raised);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
}
.actions p {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: var(--t-meta);
}
.actions-buttons {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.actions-buttons button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.section {
  margin: 0 0 0.75rem;
  font-size: var(--t-meta);
  color: var(--muted);
  font-weight: var(--fw-semibold);
}

@media print {
  .actions {
    display: none;
  }
}
</style>
