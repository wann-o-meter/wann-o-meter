import { describe, expect, it } from "vitest";
import { VORHABEN, loadAllVorhaben, loadVorhaben } from "./vorhaben-data";

describe("vorhaben data", () => {
  it("combines bundesweit and local deadlines for one Kommune", () => {
    const rottenburg = loadVorhaben("umzug")?.variants.find((v) => v.slug === "rottenburg");
    expect(rottenburg?.deadlines.some((d) => d.id === "ummeldung-einwohnermeldeamt")).toBe(true);
    expect(rottenburg?.deadlines.some((d) => d.id.startsWith("rottenburg-"))).toBe(true);
    expect(rottenburg?.regionCode).toBe("BW");
  });

  it("falls back to a single bundesweit variant where no local files exist", () => {
    const geburt = loadVorhaben("geburt");
    expect(geburt?.variants.map((v) => v.slug)).toEqual(["bundesweit"]);
    expect(geburt?.variants[0].deadlines.length).toBeGreaterThan(0);
  });

  it("returns null for an unknown Vorhaben", () => {
    expect(loadVorhaben("nicht-existent")).toBeNull();
  });

  it("loads every registered Vorhaben with deadlines", () => {
    const all = loadAllVorhaben();
    expect(all.length).toBe(VORHABEN.length);
    for (const v of all) {
      expect(v.variants.length, v.slug).toBeGreaterThan(0);
      expect(v.variants[0].deadlines.length, v.slug).toBeGreaterThan(0);
    }
  });
});
