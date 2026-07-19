import { describe, expect, it } from "vitest";
import { materializeRawWindow, rollingYears } from "./materialization";
import type { RawWindow, Source } from "./schema";

const source: Source = {
  url: "https://www.kmk.org/service/ferien.html",
  license: "official_par5",
  retrieved_at: "2026-07-11",
  extraction: "manual",
};

describe("rollingYears", () => {
  it("returns the start year plus the given number of following years", () => {
    expect(rollingYears(2026, 2)).toEqual([2026, 2027, 2028]);
  });
});

describe("materializeRawWindow", () => {
  it("only carries over a concrete (decreed) window when its year is within the rolling window", () => {
    const raw: RawWindow = {
      type: "school_holidays",
      year: 2025,
      from: "2025-07-01",
      to: "2025-08-01",
      precision: "exact",
      ics: false,
    };
    expect(materializeRawWindow(raw, "bw", [source], [2026, 2027, 2028])).toHaveLength(0);
  });

  it("rolls out a recurring month window (year: null) for every year in the window", () => {
    const raw: RawWindow = {
      type: "main_season",
      year: null,
      from: "--08",
      to: "--09",
      precision: "approximate",
      ics: false,
    };
    const windows = materializeRawWindow(raw, "apfel", [source], [2026, 2027, 2028]);
    expect(windows.map((f) => f.from)).toEqual(["2026-08-01", "2027-08-01", "2028-08-01"]);
    expect(windows.map((f) => f.to)).toEqual(["2026-09-30", "2027-09-30", "2028-09-30"]);
  });

  it("carries value and unit over from the raw window", () => {
    const raw: RawWindow = {
      type: "temperature",
      year: 2026,
      from: "2026-07-01",
      to: "2026-07-01",
      precision: "approximate",
      ics: false,
      value: 22.5,
      unit: "°C",
    };
    const windows = materializeRawWindow(raw, "x", [source], [2026]);
    expect(windows[0].value).toBe(22.5);
    expect(windows[0].unit).toBe("°C");
  });

  it("omits value and unit when the raw window has none", () => {
    const raw: RawWindow = {
      type: "main_season",
      year: 2026,
      from: "2026-08-01",
      to: "2026-09-30",
      precision: "approximate",
      ics: false,
    };
    const windows = materializeRawWindow(raw, "x", [source], [2026]);
    expect(windows[0].value).toBeUndefined();
    expect(windows[0].unit).toBeUndefined();
  });

  it("falls back to the full source list when a window has no source_urls (legacy data)", () => {
    const secondSource = { ...source, url: "https://example.org/other-source" };
    const raw: RawWindow = {
      type: "main_season",
      year: 2026,
      from: "2026-08-01",
      to: "2026-09-30",
      precision: "approximate",
      ics: false,
    };
    const windows = materializeRawWindow(raw, "x", [source, secondSource], [2026]);
    expect(windows[0].source).toEqual([source, secondSource]);
  });

  it("attaches only the sources referenced by a window's source_urls", () => {
    const secondSource = { ...source, url: "https://example.org/other-source" };
    const raw: RawWindow = {
      type: "main_season",
      year: 2026,
      from: "2026-08-01",
      to: "2026-09-30",
      precision: "approximate",
      ics: false,
      source_urls: [secondSource.url],
    };
    const windows = materializeRawWindow(raw, "x", [source, secondSource], [2026]);
    expect(windows[0].source).toEqual([secondSource]);
  });

  it("attaches multiple resolved sources when a window's source_urls names more than one", () => {
    const secondSource = { ...source, url: "https://example.org/other-source" };
    const raw: RawWindow = {
      type: "main_season",
      year: 2026,
      from: "2026-08-01",
      to: "2026-09-30",
      precision: "approximate",
      ics: false,
      source_urls: [source.url, secondSource.url],
    };
    const windows = materializeRawWindow(raw, "x", [source, secondSource], [2026]);
    expect(windows[0].source).toEqual([source, secondSource]);
  });
});
