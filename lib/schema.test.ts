import { describe, expect, it } from "vitest";
import { rawWindowSchema } from "./schema";

const valid = { type: "school_holidays", year: 2026, from: "2026-07-29", to: "2026-09-11", precision: "exact", ics: false };

describe("rawWindowSchema", () => {
  it("accepts a valid window", () => {
    expect(() => rawWindowSchema.parse(valid)).not.toThrow();
  });

  it("accepts recurring month windows (year: null)", () => {
    expect(() =>
      rawWindowSchema.parse({ type: "main_season", year: null, from: "--08", to: "--11", precision: "approximate", ics: false }),
    ).not.toThrow();
  });

  it("rejects an invalid date format", () => {
    expect(() => rawWindowSchema.parse({ ...valid, from: "29.07.2026" })).toThrow();
  });

  it("accepts a window with value and unit", () => {
    expect(() => rawWindowSchema.parse({ ...valid, value: 12.3, unit: "°C" })).not.toThrow();
  });

  it("accepts a window without value and without unit", () => {
    expect(() => rawWindowSchema.parse(valid)).not.toThrow();
  });

  it("rejects value without unit", () => {
    expect(() => rawWindowSchema.parse({ ...valid, value: 12.3 })).toThrow();
  });

  it("rejects unit without value", () => {
    expect(() => rawWindowSchema.parse({ ...valid, unit: "°C" })).toThrow();
  });

  it("accepts a window without source_urls (legacy shape, backward compat)", () => {
    expect(() => rawWindowSchema.parse(valid)).not.toThrow();
  });

  it("rejects an empty source_urls array", () => {
    expect(() => rawWindowSchema.parse({ ...valid, source_urls: [] })).toThrow();
  });

  it("accepts a window with last_verified", () => {
    expect(() => rawWindowSchema.parse({ ...valid, last_verified: "2026-07-24" })).not.toThrow();
  });

  it("rejects an invalid last_verified date", () => {
    expect(() => rawWindowSchema.parse({ ...valid, last_verified: "24.07.2026" })).toThrow();
  });

  it("accepts a window with an rrule", () => {
    expect(() => rawWindowSchema.parse({ ...valid, rrule: "FREQ=YEARLY;BYMONTH=8;BYDAY=2SA" })).not.toThrow();
  });

  it("accepts a window with notes", () => {
    expect(() => rawWindowSchema.parse({ ...valid, notes: "Ort: Marktplatz" })).not.toThrow();
  });

  it("accepts a window without last_verified, rrule, or notes (backward compat)", () => {
    expect(() => rawWindowSchema.parse(valid)).not.toThrow();
  });
});
