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
    <h2 class="t-section">Plan speichern &amp; teilen</h2>
    <div class="actions-buttons">
      <button
        type="button"
        class="btn-primary"
        :aria-pressed="kept"
        @click="$emit('toggleKept')"
      >
        <component :is="kept ? BookmarkCheck : Bookmark" :size="14" />
        {{ kept ? "Plan nicht mehr merken" : "Plan merken" }}
      </button>
      <span class="with-note">
        <button type="button" class="btn-secondary" @click="copyPlanLink">
          <Link2 :size="14" />
          {{ linkCopied ? "Kopiert" : "Plan-Link kopieren" }}
        </button>
        <small class="t-meta">Datum, Ort und Einstellungen, sonst nichts</small>
      </span>
      <button type="button" class="btn-secondary" @click="exportIcs">
        <Download :size="14" /> Als ICS exportieren
      </button>
      <button type="button" class="btn-secondary" @click="print">
        <Printer :size="14" /> Checkliste drucken
      </button>
    </div>
    <p class="t-meta">
      Häkchen, Notizen und eigene Aufgaben bleiben nur in diesem Browser, auf
      einem anderen Gerät ist der Plan wieder leer.
    </p>
  </div>
</template>

<style scoped>
/* Plain: four things you can do, on the page itself. */
.actions {
  margin-top: var(--s-4);
}
.actions h2 {
  margin: 0 0 var(--s-2);
}
.actions p {
  margin: var(--s-2) 0 0;
  max-width: 62ch;
  color: var(--muted);
}
.actions-buttons {
  display: flex;
  gap: var(--s-1) var(--s-2);
  flex-wrap: wrap;
  align-items: flex-start;
}

/* The caveat belongs to the one button it is about, not to the block. */
.with-note {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.with-note small {
  color: var(--muted);
}

@media print {
  .actions {
    display: none;
  }
}
</style>
