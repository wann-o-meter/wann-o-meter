import { describe, expect, it } from "vitest";
import { applyPatches } from "./vorhaben-data";
import type { Deadline } from "./deadline-schema";

const shared = [
  {
    id: "ummeldung-einwohnermeldeamt",
    kind: "statutory-relative",
    direction: "after",
    label: "Ummeldung beim Einwohnermeldeamt",
    offset_days: 14,
    authority: "Meldebehörde der neuen Gemeinde",
    source_url: "https://www.gesetze-im-internet.de/bmg/__17.html",
    source_label: "§ 17 BMG",
    belongsTo: ["umzug"],
    tags: [],
  },
  {
    id: "hundesteuer-ummelden",
    kind: "soft",
    label: "Hundesteuer ummelden",
    offset_days: 14,
    source_url: null,
    belongsTo: ["umzug"],
    tags: [],
  },
] as unknown as Deadline[];

describe("applyPatches", () => {
  it("fills a shared task in without adding a second row", () => {
    const { all } = applyPatches(
      shared,
      [{ id: "ummeldung-einwohnermeldeamt", authority: "Bürgerbüro Stadtmitte" }],
      "umzug/tuebingen.yaml",
    );
    expect(all).toHaveLength(2);
    expect(all[0].authority).toBe("Bürgerbüro Stadtmitte");
  });

  it("keeps the Frist the statute sets, whatever a Gemeinde says about itself", () => {
    const { all } = applyPatches(
      shared,
      [{ id: "ummeldung-einwohnermeldeamt", authority: "Bürgerbüro Stadtmitte" }],
      "umzug/tuebingen.yaml",
    );
    expect(all[0].offset_days).toBe(14);
    expect(all[0].source_label).toBe("§ 17 BMG");
    expect(all[0].kind).toBe("statutory-relative");
  });

  it("counts a patched task as the local fact that decides indexing", () => {
    const { local } = applyPatches(
      shared,
      [{ id: "hundesteuer-ummelden", source_url: "https://www.tuebingen.de/hundesteuer" }],
      "umzug/tuebingen.yaml",
    );
    expect(local.map((d) => d.id)).toEqual(["hundesteuer-ummelden"]);
  });

  it("leaves the order and the untouched tasks alone", () => {
    const { all, local } = applyPatches(shared, [], "umzug/tuebingen.yaml");
    expect(all.map((d) => d.id)).toEqual(["ummeldung-einwohnermeldeamt", "hundesteuer-ummelden"]);
    expect(local).toEqual([]);
  });

  // A typo would otherwise read as a Gemeinde nobody has researched yet.
  it("refuses a patch for a task the plan does not have", () => {
    expect(() =>
      applyPatches(shared, [{ id: "tippfehler-ummelden" }], "umzug/tuebingen.yaml"),
    ).toThrow(/unknown task tippfehler-ummelden/);
  });
});
