import { generateIcs } from "./ics";
import type { IcsEvent } from "./ics";
import type { ScheduleEntry } from "./deadline-plan";

// Enough head start to book an appointment, short enough to still be about this
// deadline.
const ALARM_DAYS = 3;

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
      // The Paragraf travels with the event: in the calendar, months later,
      // that is the only place the source is still at hand.
      description: [e.source_label, e.note].filter(Boolean).join(" - ") || undefined,
      url: e.source_url ?? undefined,
      alarmDays: ALARM_DAYS,
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
