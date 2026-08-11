import { getAllPages, getCategoryMeta, getPageEvents } from "./pages";

interface CalendarWindow {
  from: string;
  to: string;
  description: string;
}

interface CalendarEntry {
  id: string;
  group: string;
  label: string;
  url: string;
  feedUrl: string;
  windows: CalendarWindow[];
}

export function getAllCalendarEntries(): CalendarEntry[] {
  return getAllPages()
    .map((p) => ({
      id: `${p.category.replace(/\//g, "-")}--${p.slug}`,
      group: getCategoryMeta(p.category).name,
      label: p.meta.title,
      url: `/${p.category}/${p.slug}/`,
      feedUrl: `/feeds/${p.category}/${p.slug}.ics`,
      windows: getPageEvents(p).map((e) => ({ from: e.date, to: e.to ?? e.date, description: e.label })),
    }))
    .filter((entry) => entry.windows.length > 0);
}

