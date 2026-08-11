<script setup lang="ts">
import { ref } from "vue";
import { Download, Link2, Printer } from "lucide-vue-next";
import { generateIcs } from "../../../lib/ics";
import type { IcsEvent } from "../../../lib/ics";
import type { ScheduleEntry } from "../../../lib/deadline-plan";

const props = defineProps<{
  entries: ScheduleEntry[];
  anchorDate: string;
  calendarName: string; // e.g. "Umzug innerhalb Deutschlands - Berlin"
  fileSlug: string;
}>();

// The URL already carries date, Ort, facets and the Mietende choice. It does
// NOT carry ticks, notes or custom tasks, so the label must not promise them.
const linkCopied = ref(false);
async function copyPlanLink() {
  try {
    await navigator.clipboard.writeText(window.location.href);
    linkCopied.value = true;
    setTimeout(() => (linkCopied.value = false), 2000);
  } catch {
    // no clipboard permission - the address bar still has the same link
  }
}

function exportIcs() {
  const events: IcsEvent[] = props.entries
    .filter((e) => e.date !== null)
    .map((e) => ({
      uid: `${e.id}-${props.anchorDate}@wannometer.de`,
      from: e.date!,
      to: e.date!,
      title: e.label,
      description: e.note,
      url: e.source_url ?? undefined,
    }));
  const blob = new Blob([generateIcs(events, props.calendarName)], {
    type: "text/calendar;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${props.fileSlug}-${props.anchorDate}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

// `window` is not in template scope.
const print = () => window.print();
</script>

<template>
  <div class="actions">
    <h2 class="section">Plan mitnehmen</h2>
    <div class="actions-buttons">
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
  border-radius: var(--radius);
}
.actions p {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: var(--fs-xs);
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
/* Local copy of the shared section heading; see the note about promoting
  .section to the app stylesheet. */
.section {
  margin: 0 0 0.75rem;
  font-size: var(--fs-sm);
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}

@media print {
  .actions {
    display: none;
  }
}
</style>
