<script setup lang="ts">
import { computed, ref } from "vue";
import { formatDateWithWeekday } from "../../lib/format-date";
import { computeUmzugSchedule } from "../../lib/umzug";
import type { UmzugDeadline } from "../../lib/umzug";

const props = defineProps<{
  kommuneName: string;
  state: string;
  deadlines: UmzugDeadline[];
}>();

const moveDate = ref("");

const schedule = computed(() => (moveDate.value ? computeUmzugSchedule(moveDate.value, props.deadlines, "DE", props.state) : []));

function offsetLabel(offsetDays: number | null): string {
  if (offsetDays === null) return "Frist noch nicht recherchiert";
  if (offsetDays === 0) return "am Umzugstag";
  return offsetDays < 0 ? `${Math.abs(offsetDays)} Tage vorher` : `${offsetDays} Tage nachher`;
}
</script>

<template>
  <div class="umzug-planer">
    <p class="draft-banner">Entwurf: Diese Fristen sind noch nicht recherchiert. Zeiträume und Quellen fehlen bewusst, bis sie geprüft sind.</p>

    <label class="date-field">
      Umzugsdatum
      <input v-model="moveDate" type="date" aria-label="Umzugsdatum" />
    </label>

    <ol v-if="schedule.length > 0" class="schedule">
      <li v-for="entry in schedule" :key="entry.id" :class="{ unknown: entry.offset_days === null }">
        <span class="date">{{ entry.date ? formatDateWithWeekday(entry.date) : "?" }}</span>
        <span class="label">{{ entry.label }}</span>
        <span class="offset">{{ offsetLabel(entry.offset_days) }}</span>
        <span v-if="entry.collision" class="badge collision">{{ entry.collision }}</span>
        <span v-if="entry.weekend" class="badge collision">Wochenende</span>
        <a v-if="entry.source_url" class="badge source" :href="entry.source_url" target="_blank" rel="noopener">Quelle</a>
        <span v-else class="badge source missing">Quelle fehlt</span>
      </li>
    </ol>
    <p v-else class="hint">Umzugsdatum eingeben, um den Zeitplan für {{ kommuneName }} zu sehen.</p>
  </div>
</template>

<style scoped>
.umzug-planer {
  max-width: 40rem;
}
.draft-banner {
  background: color-mix(in srgb, var(--accent) 15%, transparent);
  border: 1px solid var(--accent);
  border-radius: 0.4rem;
  padding: 0.6rem 0.8rem;
  font-size: 0.85rem;
}
.date-field {
  display: block;
  margin: 1rem 0;
  font-weight: 600;
}
.date-field input {
  display: block;
  margin-top: 0.3rem;
}
.schedule {
  list-style: none;
  margin: 0;
  padding: 0;
}
.schedule li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--line);
}
.schedule li.unknown {
  color: var(--muted);
}
.date {
  font-variant-numeric: tabular-nums;
  min-width: 11rem;
}
.label {
  flex: 1 1 12rem;
}
.offset {
  color: var(--muted);
  font-size: 0.85rem;
}
.badge {
  font-size: 0.75rem;
  border-radius: 0.3rem;
  padding: 0.1rem 0.4rem;
}
.badge.collision {
  background: color-mix(in srgb, red 15%, transparent);
}
.badge.source {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
}
.badge.source.missing {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--muted);
}
@media print {
  .draft-banner,
  .date-field {
    display: none;
  }
}
</style>
