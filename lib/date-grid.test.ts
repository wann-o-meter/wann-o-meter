import { describe, expect, it } from "vitest";
import { daysInMonth, isoDate, matchesForDay, weeksOfMonth } from "./date-grid";

describe("daysInMonth", () => {
  it("counts days in a regular month", () => {
    expect(daysInMonth(2026, 0)).toBe(31); // January
    expect(daysInMonth(2026, 3)).toBe(30); // April
  });

  it("handles leap-year February", () => {
    expect(daysInMonth(2024, 1)).toBe(29);
    expect(daysInMonth(2026, 1)).toBe(28);
  });
});

describe("isoDate", () => {
  it("formats year/month/day as an ISO date", () => {
    expect(isoDate(2026, 0, 5)).toBe("2026-01-05");
    expect(isoDate(2026, 11, 31)).toBe("2026-12-31");
  });
});

describe("weeksOfMonth", () => {
  it("covers a month with full Monday-Sunday rows, including adjacent-month days", () => {
    // February 2026: Sun Feb 1 - Sat Feb 28, 5 ISO weeks touch it.
    const weeks = weeksOfMonth(2026, 1);
    expect(weeks).toHaveLength(5);
    expect(weeks[0].days[0]).toBe("2026-01-26"); // leading Monday from January
    expect(weeks.at(-1)?.days.at(-1)).toBe("2026-03-01"); // trailing Sunday into March
  });

  it("spans however many ISO weeks a month actually touches", () => {
    // May 2026 starts on a Friday and ends on a Sunday - spans 5 ISO weeks.
    const weeks = weeksOfMonth(2026, 4);
    expect(weeks).toHaveLength(5);
  });

  it("assigns correct ISO week numbers across a Dec/Jan boundary", () => {
    const weeks = weeksOfMonth(2025, 11); // December 2025
    const last = weeks.at(-1);
    expect(last?.mondayIso).toBe("2025-12-29");
    expect(last?.number).toBe(1); // ISO week 1 of 2026
  });
});

describe("matchesForDay", () => {
  const layer = (over: Partial<Parameters<typeof matchesForDay>[1][number]> = {}) => ({
    color: "#000",
    label: "Layer",
    url: "/layer/",
    visible: true,
    windows: [{ start: "2026-07-01", end: "2026-07-05", description: "Window" }],
    ...over,
  });

  it("matches a day within an inclusive window range", () => {
    expect(matchesForDay("2026-07-01", [layer()])).toHaveLength(1);
    expect(matchesForDay("2026-07-05", [layer()])).toHaveLength(1);
    expect(matchesForDay("2026-06-30", [layer()])).toHaveLength(0);
    expect(matchesForDay("2026-07-06", [layer()])).toHaveLength(0);
  });

  it("excludes layers marked not visible", () => {
    expect(matchesForDay("2026-07-02", [layer({ visible: false })])).toHaveLength(0);
  });

  it("collects matches from multiple overlapping layers", () => {
    const matches = matchesForDay("2026-07-02", [layer({ label: "A" }), layer({ label: "B" })]);
    expect(matches.map((m) => m.title)).toEqual(["A: Window", "B: Window"]);
  });
});
