<script setup lang="ts">
// Template: the paper Familienplaner. One month per screen, a row per day,
// a column per layer - layers take the role family members have on the
// printed version hanging in the kitchen. This is the print product: the
// screen version is the preview, so the print rules live here from the
// start rather than being bolted on later.
import { computed } from "vue";
import { X } from "lucide-vue-next";
import { MONTH_NAMES, WEEKDAY_NAMES_SHORT } from "../../../lib/date-display";
import { type DayLayer, daysInMonth, isoDate } from "../../../lib/date-grid";
import ViewNav from "./ViewNav.vue";

type PlannerLayer = DayLayer & { id: string };

const props = defineProps<{
  year: number;
  monthIndex0: number;
  layers: PlannerLayer[];
  todayIso: string;
  prevDisabled?: boolean;
  nextDisabled?: boolean;
}>();
const emit = defineEmits<{
  (e: "prev"): void;
  (e: "next"): void;
  // Removes the layer outright (same as the sidebar's X), not just hides the
  // column - a planner is built by dropping the people who aren't on it.
  (e: "remove", layerId: string): void;
}>();

const monthLabel = computed(() => `${MONTH_NAMES[props.monthIndex0]} ${props.year}`);
const visibleLayers = computed(() => props.layers.filter((l) => l.visible));

interface Cell {
  color: string;
  label: string | null;
  url: string;
}

// ponytail: one window per layer per day - two windows of the SAME layer
// overlapping on one day (which no current source produces: a Bundesland's
// Ferien don't overlap each other) would show only the first. Split the
// layer into two columns if that ever stops being true.
function cellFor(layer: PlannerLayer, dayIso: string, isFirstOfMonth: boolean): Cell | null {
  // Not named `window` - shadowing the global in a browser component is a
  // trap for whoever edits this next.
  const hit = layer.windows.find((w) => w.start <= dayIso && dayIso <= w.end);
  if (!hit) return null;
  return {
    color: layer.color,
    // The bar runs continuously down the column, so the description is
    // written once, where it starts - or at the top of the month for a
    // window that began in the previous one, which would otherwise be an
    // unlabelled band of color.
    label: hit.start === dayIso || isFirstOfMonth ? hit.description : null,
    url: `${layer.url}#${hit.start}`,
  };
}

const rows = computed(() =>
  Array.from({ length: daysInMonth(props.year, props.monthIndex0) }, (_, i) => {
    const day = i + 1;
    const iso = isoDate(props.year, props.monthIndex0, day);
    const weekdayIndex = (new Date(`${iso}T00:00:00`).getDay() + 6) % 7; // Mon=0
    return {
      iso,
      day,
      weekday: WEEKDAY_NAMES_SHORT[weekdayIndex],
      weekend: weekdayIndex >= 5,
      // With no layers on, every row still gets one empty cell: a month of
      // dated blank lines is a perfectly good planner to print and fill in
      // by hand - which is the paper original this view is copying.
      cells: visibleLayers.value.length ? visibleLayers.value.map((l) => cellFor(l, iso, day === 1)) : [null],
    };
  }),
);

// A floor width per layer column rather than an even split - past ~4 layers
// an even split shrinks them to illegibility, so the table scrolls sideways
// instead (see .planner-scroll).
const columns = computed(
  () => `4.5rem repeat(${Math.max(visibleLayers.value.length, 1)}, minmax(8rem, 1fr))`,
);

// `window` is not in template scope.
function print() {
  window.print();
}
</script>

<template>
  <div class="planner-view">
    <ViewNav
      :title="monthLabel"
      :prev-disabled="prevDisabled"
      :next-disabled="nextDisabled"
      @prev="emit('prev')"
      @next="emit('next')"
    />

    <div class="planner-actions">
      <button type="button" @click="print">Drucken</button>
    </div>

    <!-- Screen-invisible, and the only thing identifying a printed sheet
         once it is off the screen. One month fits one page (see the print
         rules below), so one line here is one line per page - a true
         running header would need @page margin boxes, which no browser
         fills with author content today. -->
    <p class="print-attribution">{{ monthLabel }} · wannometer.de</p>

    <div class="planner-scroll">
      <div class="planner" :style="{ gridTemplateColumns: columns }">
        <span class="head day-head" />
        <span v-if="visibleLayers.length === 0" class="head" />
        <span v-for="layer in visibleLayers" :key="layer.id" class="head" :title="layer.label">
          <span class="dot" :style="{ background: layer.color }" />
          <span class="head-text">{{ layer.label }}</span>
          <button
            type="button"
            class="remove"
            :title="`${layer.label} entfernen`"
            :aria-label="`${layer.label} entfernen`"
            @click="emit('remove', layer.id)"
          >
            <X :size="10" />
          </button>
        </span>

        <template v-for="row in rows" :key="row.iso">
          <span class="day" :class="{ weekend: row.weekend, today: row.iso === todayIso }">
            <span class="weekday">{{ row.weekday }}</span>
            <span class="day-number">{{ row.day }}</span>
          </span>
          <span
            v-for="(cell, i) in row.cells"
            :key="i"
            class="slot"
            :class="{ weekend: row.weekend, filled: cell !== null }"
            :style="cell ? { '--bar': cell.color } : undefined"
          >
            <a v-if="cell?.label" :href="cell.url" class="slot-label">{{ cell.label }}</a>
          </span>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.planner-actions {
  display: flex;
  justify-content: center;
  margin-bottom: 1rem;
}
.planner-actions button {
  font-size: 0.78rem;
  padding: 0.25rem 0.7rem;
}
.print-attribution {
  display: none;
}

.planner-scroll {
  overflow-x: auto;
}
.planner {
  display: grid;
  border: 1px solid var(--line);
  /* No row gaps and no per-row borders inside the layer columns - that is
     what makes a multi-day window read as one continuous vertical bar
     instead of a stack of separate blocks. Row separation comes from the
     day column and the weekend shading instead. */
  gap: 0;
  min-width: 100%;
}

.head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
  padding: 0.5rem 0.5rem;
  border-bottom: 1px solid var(--line);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
}
.head-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Sits after the label, pushed to the column's right edge - deliberately
   quiet until hovered, since a column header is a label first and a control
   second. */
.remove {
  margin-left: auto;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  color: var(--muted);
  opacity: 0.6;
}
.remove:hover {
  color: var(--accent);
  opacity: 1;
}
.dot {
  width: 0.65rem;
  height: 0.65rem;
  display: inline-block;
  flex-shrink: 0;
}

.day {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  padding: 0.25rem 0.5rem;
  border-bottom: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--muted);
}
.day-number {
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}
.day.today {
  background: var(--accent);
  color: var(--accent-ink);
}
.day.today .day-number {
  color: var(--accent-ink);
  font-weight: 600;
}

.slot {
  min-height: 1.6rem;
  padding: 0.25rem 0.5rem;
  border-left: 1px solid var(--line);
  display: flex;
  align-items: center;
  font-size: 0.75rem;
}
/* Solid edge bar + a tint of the same colour behind it: the bar is the
   continuous line down the column, the tint keeps the label on a normal ink
   colour instead of needing per-colour contrast maths. */
.slot.filled {
  box-shadow: inset 0.28rem 0 0 var(--bar);
  background: color-mix(in srgb, var(--bar) 16%, transparent);
}
.weekend {
  background: var(--paper-raised);
}
.slot.filled.weekend {
  background: color-mix(in srgb, var(--bar) 24%, var(--paper-raised));
}
.slot-label {
  color: inherit;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-left: 0.15rem;
}
.slot-label:hover {
  color: var(--accent);
}

@media print {
  /* Deliberately no `@page { size: ... }` - forcing A4 portrait would
     override the paper the user picks in the print dialog, and this table
     fits A3 landscape (the classic wide planner look) just as happily. */
  @page {
    margin: 12mm;
  }
  /* The whole grid is background colour and inset shadow, and browsers drop
     both in print unless "Hintergrundgrafiken" is ticked - without this the
     planner comes out as 31 empty rows. Inherits, so one declaration on the
     grid covers every slot and the weekend shading. */
  .planner {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
    font-size: 8pt;
    border-color: #000;
  }
  /* ViewNav's own root - the month/year it shows is already in the
     attribution line, and its chevrons are controls. */
  .view-nav,
  .planner-actions,
  .remove {
    display: none;
  }
  .print-attribution {
    display: block;
    margin: 0 0 0.4rem;
    font-size: 8pt;
    color: #000;
  }
  /* 31 rows plus a header have to fit one page - anything taller starts
     splitting months across sheets, which is the one thing a wall planner
     may not do. */
  .slot,
  .day {
    min-height: 0;
    padding: 0.05rem 0.3rem;
    break-inside: avoid;
    border-color: #000;
  }
  .head {
    padding: 0.1rem 0.3rem;
    border-color: #000;
  }
  .day.today {
    background: none;
    color: #000;
    font-weight: 700;
  }
  .planner-scroll {
    overflow-x: visible;
  }
}
</style>
