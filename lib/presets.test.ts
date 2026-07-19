import { describe, expect, it } from "vitest";
import { allPresets, calendarUrl, presetBySlug } from "./presets";

describe("allPresets", () => {
  it("loads and validates all preset YAML files", () => {
    const presets = allPresets();
    expect(presets.length).toBeGreaterThanOrEqual(2);
    for (const p of presets) {
      expect(p.layers.length).toBeGreaterThan(0);
      expect(p.mode).toBe("overlay");
    }
  });

  it("finds a preset by slug", () => {
    expect(presetBySlug("bruecktage-bw")?.region).toBe("BW");
  });
});

describe("calendarUrl", () => {
  it("builds a pre-filled calendar URL from region and layers", () => {
    const preset = presetBySlug("bruecktage-bw")!;
    expect(calendarUrl(preset)).toBe("/kalender?region=BW&layers=holiday%2Cschool_holidays");
  });
});
