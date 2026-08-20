import { type ComputedRef, type Ref, computed } from "vue";
import type { Deadline, ScheduleEntry } from "../../../lib/deadline-plan";
import { computeSchedule } from "../../../lib/deadline-plan";
import type { PlanVariant } from "./types";

export const ANCHOR_ID = "__anchor";
export const COUNTRY_CODE = "DE";

export function usePlannerSchedule(
  anchorDate: Ref<string>,
  selected: ComputedRef<PlanVariant | undefined>,
  workingDeadlines: ComputedRef<Deadline[]>,
  anchorLabel: () => string,
  doneIds: Record<string, boolean>,
  overlapMonths?: Ref<number>,
) {
  const schedule = computed<ScheduleEntry[]>(() => {
    if (!anchorDate.value || !selected.value) return [];
    const withAnchor: Deadline[] = [
      {
        // The anchor is the day itself, not an obligation of any kind.
        id: ANCHOR_ID,
        kind: "soft" as const,
        belongsTo: [],
        tags: [],
        label: anchorLabel(),
        offset_days: 0,
        source_url: null,
      },
      ...workingDeadlines.value,
    ];
    return computeSchedule(
      anchorDate.value,
      withAnchor,
      COUNTRY_CODE,
      selected.value.regionCode,
      undefined,
      overlapMonths?.value ?? 0,
    );
  });

  const timeline = computed(() =>
    schedule.value.filter((e) => e.date !== null),
  );
  const unscheduled = computed(() =>
    schedule.value.filter((e) => e.date === null),
  );
  const tasks = computed(() =>
    schedule.value.filter((e) => e.id !== ANCHOR_ID),
  );

  return { schedule, timeline, unscheduled, tasks };
}
