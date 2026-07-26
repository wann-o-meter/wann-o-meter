import { describe, expect, it } from "vitest";
import { formatTodayLabel, isoWeekNumber } from "./date-display";

describe("isoWeekNumber", () => {
  it("computes ISO-8601 week numbers using the Thursday rule", () => {
    expect(isoWeekNumber(new Date("2026-01-01T00:00:00Z"))).toBe(1);
    expect(isoWeekNumber(new Date("2026-07-13T00:00:00Z"))).toBe(29);
  });

  it("assigns the last days of December to week 1 of the following year when applicable", () => {
    // 2025-12-29 is a Monday, ISO week 1 of 2026.
    expect(isoWeekNumber(new Date("2025-12-29T00:00:00Z"))).toBe(1);
  });
});

describe("formatTodayLabel", () => {
  it("formats a short '<Wd>., <DD>.<MM>.' label for the header", () => {
    expect(formatTodayLabel(new Date("2026-07-13T12:00:00"))).toBe("Mo., 13.07.");
  });

  it("zero-pads day and month", () => {
    expect(formatTodayLabel(new Date("2026-01-04T12:00:00"))).toBe("So., 04.01.");
  });
});
