import { type ComputedRef, type Ref, computed } from "vue";
import type { Deadline, ScheduleEntry } from "../../../lib/deadline-plan";
import { computeSchedule } from "../../../lib/deadline-plan";
import { formatDate, toDate } from "../../../lib/format-date";
import type { PlanVariant } from "./types";

export const ANCHOR_ID = "__anchor";
export const COUNTRY_CODE = "DE"; // hardcoded: a German-market product end to end, no caller needs another

// Interleaves gap markers between rows so the proportional spacing is a real
// node to hang a hover-revealed insert button on, not just margin.
export type RailNode =
  | { kind: "item"; entry: ScheduleEntry }
  | {
      kind: "gap";
      id: string;
      afterOffset: number;
      beforeOffset: number;
      heightPx: number;
      bufferDays: number; // days of real dead time between the previous deadline and the next task's earliest-possible day, clamped to >= 0 - a bar that already starts earlier isn't a negative gap, it's none at all
    };

// Resolves the working deadline list to real dates, plus everything the rail
// and summary stats derive from it. The anchor day is UI chrome, not a
// researched fact - injected here rather than stored as data, and can't be
// checked off/noted/deleted like a task.
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
        id: ANCHOR_ID,
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

  const railNodes = computed<RailNode[]>(() => {
    const nodes: RailNode[] = [];
    timeline.value.forEach((entry, i) => {
      if (i > 0) {
        const prev = timeline.value[i - 1];
        const bufferDays = Math.max(
          0,
          Math.round(
            (toDate(entry.earliestDate!).getTime() -
              toDate(prev.date!).getTime()) /
              86400000,
          ),
        );
        nodes.push({
          kind: "gap",
          id: `gap-${prev.id}-${entry.id}`,
          afterOffset: prev.offset_days!,
          beforeOffset: entry.offset_days!,
          heightPx: Math.min(48, Math.max(20, bufferDays * 1.6)),
          bufferDays,
        });
      }
      nodes.push({ kind: "item", entry });
    });
    return nodes;
  });

  const stats = computed(() => {
    const open = tasks.value.filter((e) => !doneIds[e.id]);
    const firstOpen = timeline.value.find(
      (e) => e.id !== ANCHOR_ID && !doneIds[e.id],
    );
    const warnings = timeline.value.filter(
      (e) =>
        e.id !== ANCHOR_ID &&
        !doneIds[e.id] &&
        (e.weekend || e.collision || e.impossible),
    ).length;
    return {
      open: open.length,
      done: tasks.value.length - open.length,
      first: firstOpen
        ? formatDate(firstOpen.date!).replace(/\.\d{4}$/, "")
        : "—",
      warnings,
    };
  });

  return { schedule, timeline, unscheduled, tasks, railNodes, stats };
}
