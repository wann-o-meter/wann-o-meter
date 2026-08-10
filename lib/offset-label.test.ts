import { describe, expect, it } from "vitest";
import { byOffset, offsetLabel, sourceLabel } from "./offset-label";
import type { Deadline } from "./deadline-plan";

const base: Deadline = {
  id: "x",
  label: "X",
  offset_days: 0,
  source_url: null,
};
const d = (over: Partial<Deadline>): Deadline => ({ ...base, ...over });

describe("offsetLabel", () => {
  it("scales the unit to the distance", () => {
    expect(offsetLabel(d({ offset_days: -120 }), "Umzugstag")).toBe(
      "4 Monate vorher",
    );
    expect(offsetLabel(d({ offset_days: -42 }), "Umzugstag")).toBe(
      "6 Wochen vorher",
    );
    expect(offsetLabel(d({ offset_days: 7 }), "Umzugstag")).toBe(
      "7 Tage danach",
    );
    expect(offsetLabel(d({ offset_days: 1 }), "Umzugstag")).toBe(
      "1 Tag danach",
    );
    expect(offsetLabel(d({ offset_days: 0 }), "Umzugstag")).toBe("Umzugstag");
    expect(offsetLabel(d({ offset_days: 0 }), "Letzter Arbeitstag")).toBe(
      "Letzter Arbeitstag",
    );
  });

  it("names the rule instead of its sorting approximation", () => {
    const rule = d({ offset_days: -90, offset_rule: "bgb-573c-notice" });
    expect(offsetLabel(rule, "Umzugstag")).toContain("573c");
    expect(offsetLabel(rule, "Umzugstag")).not.toContain("Monate");
  });

  it("never invents a number for an unresearched deadline", () => {
    expect(offsetLabel(d({ offset_days: null }), "Umzugstag")).toBe(
      "Frist noch nicht recherchiert",
    );
  });
});

describe("sourceLabel", () => {
  it("distinguishes missing from not-applicable", () => {
    expect(sourceLabel(d({}))).toBe("Erfahrungswert");
    expect(sourceLabel(d({ no_source_needed: true }))).toBe(
      "Keine gesetzliche Frist",
    );
    expect(
      sourceLabel(d({ source_url: "https://e.de", source_label: "§ 1" })),
    ).toBe("§ 1");
  });
});

describe("byOffset", () => {
  it("sorts unresearched deadlines last", () => {
    const sorted = [
      d({ offset_days: null, id: "u" }),
      d({ offset_days: 5, id: "b" }),
      d({ offset_days: -5, id: "a" }),
    ]
      .sort(byOffset)
      .map((x) => x.id);
    expect(sorted).toEqual(["a", "b", "u"]);
  });
});
