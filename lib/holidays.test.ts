import { describe, expect, it } from "vitest";
import { holidaysFor } from "./holidays";

const names = (year: number, region?: string) =>
  holidaysFor(year, "DE", region).map((h) => h.name);

describe("holidaysFor", () => {
  it("gives only the nationwide Feiertage without a Bundesland", () => {
    const all = names(2027);
    expect(all).toHaveLength(9);
    expect(all).toContain("Neujahr");
    expect(all).not.toContain("Fronleichnam");
  });

  it("adds what a Bundesland has on top", () => {
    expect(names(2027, "BW")).toContain("Fronleichnam");
    expect(names(2027, "SN")).toContain("Buß- und Bettag");
    expect(names(2027, "BE")).toContain("Internationaler Frauentag");
  });

  it("returns nothing outside the generated table", () => {
    expect(holidaysFor(1990, "DE", "BW")).toEqual([]);
    expect(holidaysFor(2027, "FR")).toEqual([]);
  });

  it("falls back to the nationwide set for an unknown region", () => {
    expect(names(2027, "XX")).toEqual(names(2027));
  });
});
