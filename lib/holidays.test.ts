import { describe, expect, it } from "vitest";
import { holidaysFor } from "./holidays";

describe("holidaysFor", () => {
  it("includes nationwide holidays (country + region)", () => {
    const f = holidaysFor(2027, "DE", "BW");
    expect(f.find((x) => x.name === "Neujahr")?.date).toBe("2027-01-01");
    expect(f.find((x) => x.name === "Tag der Deutschen Einheit")?.date).toBe("2027-10-03");
  });

  it("accounts for state-specific holidays", () => {
    const bw = holidaysFor(2027, "DE", "BW");
    expect(bw.some((x) => x.name === "Fronleichnam")).toBe(true);

    const hh = holidaysFor(2027, "DE", "HH");
    expect(hh.some((x) => x.name === "Fronleichnam")).toBe(false);
  });

  it("works for other countries without a region", () => {
    const fr = holidaysFor(2027, "FR");
    expect(fr.some((x) => x.name === "Fête du travail" && x.date === "2027-05-01")).toBe(true);
  });
});
