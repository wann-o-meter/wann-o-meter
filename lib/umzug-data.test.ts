import { describe, expect, it } from "vitest";
import { listUmzugKommunen, loadAllUmzugKommunen, loadUmzugKommune } from "./umzug-data";

describe("umzug data", () => {
  it("lists the pilot Kommunen", () => {
    const slugs = listUmzugKommunen().map((k) => k.slug);
    expect(slugs).toContain("rottenburg");
  });

  it("combines bundesweit and local deadlines for one Kommune", () => {
    const rottenburg = loadUmzugKommune("rottenburg");
    expect(rottenburg?.deadlines.some((d) => d.id === "ummeldung-einwohnermeldeamt")).toBe(true);
    expect(rottenburg?.deadlines.some((d) => d.id.startsWith("rottenburg-"))).toBe(true);
  });

  it("returns null for an unknown Kommune", () => {
    expect(loadUmzugKommune("nicht-existent")).toBeNull();
  });

  it("loads every Kommune with its slug attached", () => {
    const all = loadAllUmzugKommunen();
    expect(all.length).toBe(listUmzugKommunen().length);
    expect(all.find((k) => k.slug === "rottenburg")?.name).toBe("Rottenburg am Neckar");
  });
});
