import { describe, expect, it } from "vitest";
import { getAllPages, getCategoryMeta } from "./pages";
import { getAllCalendarEntries, getCalendarEntry } from "./calendar-sources";

describe("getAllCalendarEntries", () => {
  it("returns entries for every content type, grouped by the page's real category rather than a generic bucket", () => {
    const groups = new Set(getAllCalendarEntries().map((e) => e.group));
    const pageCategories = new Set(getAllPages().map((p) => getCategoryMeta(p.category).name));
    expect(groups).toEqual(pageCategories);
  });

  it("gives every entry a unique id with no colons or slashes (both break Astro's static build)", () => {
    const ids = getAllCalendarEntries().map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) {
      expect(id).not.toContain(":");
      expect(id).not.toContain("/");
    }
  });

  it("only includes pages that actually have events", () => {
    const entries = getAllCalendarEntries();
    expect(entries.length).toBeGreaterThan(0);
    for (const e of entries) expect(e.windows.length).toBeGreaterThan(0);
  });

  it("builds a resolvable saisonkalender entry with url/feedUrl matching the real routes", () => {
    const apfel = getCalendarEntry("saisonkalender--apfel");
    expect(apfel).toBeDefined();
    expect(apfel!.url).toBe("/saisonkalender/apfel/");
    expect(apfel!.feedUrl).toBe("/feeds/saisonkalender/apfel.ics");
    expect(apfel!.windows.length).toBeGreaterThan(0);
  });

  it("builds a resolvable feiertage entry for a purely computed subject", () => {
    const holiday = getCalendarEntry("feiertage--de-bw");
    expect(holiday).toBeDefined();
    expect(holiday!.url).toBe("/feiertage/de-bw/");
    expect(holiday!.windows.length).toBeGreaterThan(0);
  });

  it("builds a resolvable schulferien entry, separate from urlaubsfenster", () => {
    const schulferien = getCalendarEntry("schulferien--nw");
    expect(schulferien).toBeDefined();
    expect(schulferien!.url).toBe("/schulferien/nw/");
    expect(schulferien!.windows.length).toBeGreaterThan(0);
  });
});
