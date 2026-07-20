import type { CalendarEntry, CalendarWindow } from "./calendar-sources";

export interface TodayTeaser {
  text: string;
  entryId: string;
  day: string; // ISO date to deep-link the calendar to
}

function activeWindow(entry: CalendarEntry, today: string): CalendarWindow | undefined {
  return entry.windows.find((w) => w.from <= today && today <= w.to);
}

function upcomingWindow(entry: CalendarEntry, today: string): CalendarWindow | undefined {
  return [...entry.windows].filter((w) => w.from > today).sort((a, b) => a.from.localeCompare(b.from))[0];
}

// "Erdbeere" -> "Erdbeersaison", not "Erdbeeresaison" - the only produce name
// ending in "e" (see data/saisonkalender/*/data.yaml). Shared with
// lib/homepage-questions.ts's rotator so both phrasings stay in sync.
export function seasonNoun(produceLabel: string): string {
  const stem = produceLabel.endsWith("e") ? produceLabel.slice(0, -1) : produceLabel;
  return `${stem}saison`;
}

function describe(entry: CalendarEntry, w: CalendarWindow): string {
  if (entry.id.startsWith("saisonkalender--")) {
    return w.description === "Hauptsaison" ? seasonNoun(entry.label) : `${entry.label} als Lagerware`;
  }
  if (entry.id.startsWith("feiertage--de-")) return `Feiertag in ${entry.label.replace(/^Deutschland – /, "")}`;
  return `Brückenfenster in ${entry.label}`; // urlaubsfenster--*
}

function formatShort(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}.${m}.`;
}

type Hit = { e: CalendarEntry; w: CalendarWindow };

/**
 * Client-side "Heute ist X" teaser for the homepage - never computed at
 * build time (same staleness concern lib/date-display.ts's
 * formatTodayLabel already solves for the header's "today" label).
 * Backbone is the active Saisonkalender window (long-running, present most
 * days by design); a same-day Feiertag or Urlaubsfenster layers on top when
 * present. Falls back to the soonest upcoming window across all three
 * categories so the teaser is never empty - returns null only if the feed
 * has no future windows at all (a stale, un-rebuilt site), letting the
 * caller keep its static default text instead of claiming "heute ist
 * nichts".
 */
export function pickTodayTeaser(entries: CalendarEntry[], today: string): TodayTeaser | null {
  const hits = entries
    .map((e) => ({ e, w: activeWindow(e, today) }))
    .filter((h): h is Hit => h.w !== undefined);

  const season =
    hits.find((h) => h.e.id.startsWith("saisonkalender--") && h.w.description === "Hauptsaison") ??
    hits.find((h) => h.e.id.startsWith("saisonkalender--"));
  const special =
    hits.find((h) => h.e.id.startsWith("feiertage--de-")) ??
    hits.find((h) => h.e.id.startsWith("urlaubsfenster--"));

  const parts = [season, special].filter((h): h is Hit => h !== undefined);
  if (parts.length > 0) {
    const linkEntry = (special ?? season)!.e;
    return {
      text: `Heute: ${parts.map((h) => describe(h.e, h.w)).join(" · ")}`,
      entryId: linkEntry.id,
      day: today,
    };
  }

  let best: Hit | null = null;
  for (const e of entries) {
    const w = upcomingWindow(e, today);
    if (w && (!best || w.from < best.w.from)) best = { e, w };
  }
  if (!best) return null;
  return {
    text: `${describe(best.e, best.w)} ab ${formatShort(best.w.from)}`,
    entryId: best.e.id,
    day: best.w.from,
  };
}
