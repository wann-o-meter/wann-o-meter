import { generateIcs } from "./ics";
import type { IcsEvent } from "./ics";
import type { ScheduleEntry } from "./deadline-plan";

export function downloadIcs(
  entries: ScheduleEntry[],
  calendarName: string,
  fileSlug: string,
  anchorDate: string,
): void {
  const events: IcsEvent[] = entries
    .filter((e) => e.date !== null)
    .map((e) => ({
      uid: `${e.id}-${anchorDate}@wannometer.de`,
      from: e.date!,
      to: e.date!,
      title: e.label,
      description: e.note,
      url: e.source_url ?? undefined,
    }));
  const blob = new Blob([generateIcs(events, calendarName)], {
    type: "text/calendar;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${fileSlug}-${anchorDate}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}
