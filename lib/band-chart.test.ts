import { describe, expect, it } from "vitest";
import { buildBandChart, defaultWindow, hasCoverage } from "./band-chart";

describe("defaultWindow", () => {
  it("spans 10 days before today to 60 days after", () => {
    expect(defaultWindow("2026-07-30")).toEqual({ start: "2026-07-20", end: "2026-09-28" });
  });
});

describe("hasCoverage", () => {
  it("is false when every cell is plain or weekend", () => {
    const chart = buildBandChart([{ scopeId: "hb", label: "HB", href: "/x/hb/", layerId: "x--hb", ranges: [] }], "2026-07-30", "2026-08-02", "2026-07-30");
    expect(hasCoverage(chart)).toBe(false);
  });

  it("is true once at least one cell is primary or accent", () => {
    const chart = buildBandChart(
      [{ scopeId: "nw", label: "NW", href: "/x/nw/", layerId: "x--nw", ranges: [{ start: "2026-07-30", end: "2026-07-30", title: "x", kind: "primary" }] }],
      "2026-07-30",
      "2026-08-02",
      "2026-07-30",
    );
    expect(hasCoverage(chart)).toBe(true);
  });
});

describe("buildBandChart", () => {
  const row = (scopeId: string, ranges: Parameters<typeof buildBandChart>[0][number]["ranges"]) => ({
    scopeId,
    label: scopeId.toUpperCase(),
    href: `/x/${scopeId}/`,
    layerId: `x--${scopeId}`,
    ranges,
  });

  it("covers every day of the window inclusive, in order", () => {
    const chart = buildBandChart([], "2026-07-30", "2026-08-02", "2026-07-30");
    expect(chart.days.map((d) => d.iso)).toEqual(["2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02"]);
  });

  it("marks Saturdays and Sundays as weekend", () => {
    const chart = buildBandChart([], "2026-07-30", "2026-08-02", "2026-07-30");
    // 2026-08-01 is a Saturday, 2026-08-02 a Sunday.
    expect(chart.days.map((d) => d.weekend)).toEqual([false, false, true, true]);
  });

  it("flags exactly the day matching todayIso", () => {
    const chart = buildBandChart([], "2026-07-28", "2026-08-01", "2026-07-30");
    expect(chart.days.find((d) => d.today)?.iso).toBe("2026-07-30");
  });

  it("groups the day header into one segment per month", () => {
    const chart = buildBandChart([], "2026-07-30", "2026-08-02", "2026-07-30");
    expect(chart.months).toEqual([
      { label: "Juli 2026", days: 2 },
      { label: "August 2026", days: 2 },
    ]);
  });

  it("fills a row's cells for the days a range covers, weekday beats weekend", () => {
    const chart = buildBandChart(
      [row("nw", [{ start: "2026-07-30", end: "2026-08-02", title: "Sommerferien", kind: "primary" }])],
      "2026-07-29",
      "2026-08-03",
      "2026-07-30",
    );
    expect(chart.rows[0].cells.map((c) => c.state)).toEqual(["plain", "primary", "primary", "primary", "primary", "plain"]);
  });

  it("lets an accent range (e.g. a Feiertag) override a primary one on the same day", () => {
    const chart = buildBandChart(
      [
        row("by", [
          { start: "2026-08-01", end: "2026-09-15", title: "Sommerferien", kind: "primary" },
          { start: "2026-08-15", end: "2026-08-15", title: "Mariä Himmelfahrt", kind: "accent" },
        ]),
      ],
      "2026-08-14",
      "2026-08-16",
      "2026-08-14",
    );
    expect(chart.rows[0].cells.map((c) => c.state)).toEqual(["primary", "accent", "primary"]);
    expect(chart.rows[0].cells[1].title).toBe("Mariä Himmelfahrt");
  });

  it("leaves a scope's day plain when no range covers it", () => {
    const chart = buildBandChart([row("hb", [])], "2026-07-30", "2026-07-30", "2026-07-30");
    expect(chart.rows[0].cells[0].state).toBe("plain");
  });
});
