import { describe, expect, it } from "vitest";
import { pickTodayTeaser } from "./today-teaser";
import type { CalendarEntry } from "./calendar-sources";

function entry(id: string, label: string, windows: { from: string; to: string; description: string }[]): CalendarEntry {
  return { id, group: "", label, url: "", feedUrl: "", windows };
}

describe("pickTodayTeaser", () => {
  it("uses the active season alone when nothing else is active", () => {
    const entries = [entry("saisonkalender--spargel", "Spargel", [{ from: "2026-04-01", to: "2026-06-24", description: "Hauptsaison" }])];
    const teaser = pickTodayTeaser(entries, "2026-05-01");
    expect(teaser?.text).toBe("Heute: Spargelsaison");
    expect(teaser?.entryId).toBe("saisonkalender--spargel");
  });

  it("drops the trailing e before 'saison' (Erdbeere -> Erdbeersaison)", () => {
    const entries = [entry("saisonkalender--erdbeere", "Erdbeere", [{ from: "2026-05-01", to: "2026-06-30", description: "Hauptsaison" }])];
    expect(pickTodayTeaser(entries, "2026-05-15")?.text).toBe("Heute: Erdbeersaison");
  });

  it("layers a same-day Feiertag on top of the season backbone", () => {
    const entries = [
      entry("saisonkalender--spargel", "Spargel", [{ from: "2026-04-01", to: "2026-06-24", description: "Hauptsaison" }]),
      entry("feiertage--de-by", "Deutschland – Bayern", [{ from: "2026-05-01", to: "2026-05-01", description: "Tag der Arbeit" }]),
    ];
    const teaser = pickTodayTeaser(entries, "2026-05-01");
    expect(teaser?.text).toBe("Heute: Spargelsaison · Feiertag in Bayern");
    expect(teaser?.entryId).toBe("feiertage--de-by");
  });

  it("prefers a Feiertag over an Urlaubsfenster when both are active the same day", () => {
    const entries = [
      entry("feiertage--de-by", "Deutschland – Bayern", [{ from: "2026-05-01", to: "2026-05-01", description: "Tag der Arbeit" }]),
      entry("urlaubsfenster--by", "Bayern", [{ from: "2026-04-29", to: "2026-05-03", description: "Mit 2 Urlaubstagen frei." }]),
    ];
    expect(pickTodayTeaser(entries, "2026-05-01")?.text).toBe("Heute: Feiertag in Bayern");
  });

  it("falls back to the soonest upcoming window when nothing is active today", () => {
    const entries = [
      entry("saisonkalender--kuerbis", "Kürbis", [{ from: "2026-09-01", to: "2026-10-31", description: "Hauptsaison" }]),
      entry("feiertage--de-by", "Deutschland – Bayern", [{ from: "2026-08-15", to: "2026-08-15", description: "Mariä Himmelfahrt" }]),
    ];
    const teaser = pickTodayTeaser(entries, "2026-07-20");
    expect(teaser?.text).toBe("Feiertag in Bayern ab 15.08.");
    expect(teaser?.day).toBe("2026-08-15");
  });

  it("never claims 'nichts' - returns null instead when there is no future window to fall back on", () => {
    const entries = [entry("saisonkalender--kuerbis", "Kürbis", [{ from: "2025-09-01", to: "2025-10-31", description: "Hauptsaison" }])];
    expect(pickTodayTeaser(entries, "2026-07-20")).toBeNull();
  });
});
