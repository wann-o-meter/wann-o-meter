import { describe, expect, it } from "vitest";
import { formatDate, toDate } from "./format-date";

describe("toDate", () => {
  it("parses a day-resolution date at midnight UTC", () => {
    expect(toDate("2026-05-01").toISOString()).toBe("2026-05-01T00:00:00.000Z");
  });

  // rawWindowSchema (lib/schema.ts) has always accepted "YYYY-MM-DDTHH:MM" -
  // it just parsed to Invalid Date here, so a page grouped such a window
  // under a NaN year instead of 2026.
  it("parses a minute-resolution date without losing the clock time", () => {
    expect(toDate("2026-05-01T06:30").toISOString()).toBe("2026-05-01T06:30:00.000Z");
    expect(toDate("2026-05-01T06:30").getUTCFullYear()).toBe(2026);
  });

  it("formats both resolutions as the same day", () => {
    expect(formatDate("2026-05-01T06:30")).toBe(formatDate("2026-05-01"));
  });
});
