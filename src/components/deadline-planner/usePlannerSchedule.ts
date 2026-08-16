import { type ComputedRef, type Ref, computed } from "vue";
import type { Deadline, ScheduleEntry } from "../../../lib/deadline-plan";
import { computeSchedule } from "../../../lib/deadline-plan";
import { formatDate, toDate } from "../../../lib/format-date";
import type { PlanVariant } from "./types";

export const ANCHOR_ID = "__anchor";
export const COUNTRY_CODE = "DE";

type RailNode =
  | { kind: "item"; entry: ScheduleEntry }
  // A gap is drawn in days. Around a step without a date it would show time
  // nobody measured, so it is only spanned between two real Fristen.
  | {
      kind: "gap";
      id: string;
      afterOffset: number;
      beforeOffset: number;
      heightPx: number;
      bufferDays: number;
    };

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
      const prev = timeline.value[i - 1];
      if (i > 0 && entry.kind !== "soft" && prev.kind !== "soft") {
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
