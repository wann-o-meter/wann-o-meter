// Single place where "which content types exist" is known. The calendar
// component (src/components/Kalender.vue) has no category-specific logic at
// all - it only ever deals with CalendarEntry, fetched through one generic
// API route (src/pages/api/v1/calendar/[id].json.ts). Every category
// (Feiertage, Urlaubsfenster, Schulferien, Saisonkalender, and the generic
// scraped-content categories) now flows through lib/pages.ts's one model,
// so building the catalog is a single pass over getAllPages().
import { getAllPages, getCategoryMeta, getPageEvents } from "./pages";

// Field names (from/to/description) intentionally match the existing
// MaterializedWindow schema (lib/schema.ts) - this is a projection of that
// already-established data shape, not a new one.
export interface CalendarWindow {
  from: string;
  to: string;
  description: string;
}

export interface CalendarEntry {
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
      // "--" instead of ":" or "/" - colons in a route param break Astro's
      // static build (read as a URI scheme), and a category can now be a
      // "/"-joined nested path (lib/pages.ts) whose own "/" would too.
      id: `${p.category.replace(/\//g, "-")}--${p.slug}`,
      group: getCategoryMeta(p.category).name,
      label: p.meta.title,
      url: `/${p.category}/${p.slug}/`,
      feedUrl: `/feeds/${p.category}/${p.slug}.ics`,
      windows: getPageEvents(p).map((e) => ({ from: e.date, to: e.to ?? e.date, description: e.label })),
    }))
    .filter((entry) => entry.windows.length > 0);
}

export function getCalendarEntry(id: string): CalendarEntry | undefined {
  return getAllCalendarEntries().find((entry) => entry.id === id);
}

// Bounded subset for the homepage's "Heute ist..." teaser (src/pages/
// index.astro, computed client-side so "today" never freezes at build
// time) - region-agnostic Saisonkalender plus the 16 German states'
// Feiertage/Urlaubsfenster, never the 200+ country Feiertage entries the
// full catalog also has (too many to ship/fetch for a one-line teaser).
export function getTodayFeedEntries(): CalendarEntry[] {
  return getAllCalendarEntries().filter(
    (e) =>
      e.id.startsWith("saisonkalender--") ||
      e.id.startsWith("urlaubsfenster--") ||
      e.id.startsWith("feiertage--de-"),
  );
}
