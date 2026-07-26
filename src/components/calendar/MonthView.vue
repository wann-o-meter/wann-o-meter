<script setup lang="ts">
// Template: one month as a full-size grid.
import { computed } from "vue";
import { MONTH_NAMES } from "../../../lib/date-display";
import type { DayLayer } from "../../../lib/date-grid";
import MonthGrid from "./MonthGrid.vue";
import ViewNav from "./ViewNav.vue";

const props = defineProps<{
  year: number;
  monthIndex0: number;
  layers: DayLayer[];
  todayIso: string;
  prevDisabled?: boolean;
  nextDisabled?: boolean;
}>();
const emit = defineEmits<{
  (e: "prev"): void;
  (e: "next"): void;
  (e: "week-click", mondayIso: string): void;
}>();

const title = computed(() => `${MONTH_NAMES[props.monthIndex0]} ${props.year}`);
</script>

<template>
  <div class="month-view">
    <ViewNav
      :title="title"
      :prev-disabled="prevDisabled"
      :next-disabled="nextDisabled"
      @prev="emit('prev')"
      @next="emit('next')"
    />
    <MonthGrid
      :year="year"
      :month-index0="monthIndex0"
      :layers="layers"
      :today-iso="todayIso"
      variant="full"
      @week-click="emit('week-click', $event)"
    />
  </div>
</template>
