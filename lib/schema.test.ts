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
});
