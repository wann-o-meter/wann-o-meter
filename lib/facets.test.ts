import { describe, expect, it } from "vitest";
import type { Deadline } from "./deadline-plan";
import { appliesTo, facetsUsedBy } from "./facets";

function deadline(applies_if?: string[]): Deadline {
  return { id: "x", label: "X", offset_days: 0, source_url: null, applies_if };
}

describe("appliesTo", () => {
  it("always shows a deadline without applies_if", () => {
    expect(appliesTo(deadline(), [])).toBe(true);
    expect(appliesTo(deadline(), ["auto"])).toBe(true);
  });

  it("hides a tagged deadline until one of its facets is active", () => {
    const d = deadline(["auto", "gewerbe"]);
    expect(appliesTo(d, [])).toBe(false);
    expect(appliesTo(d, ["haustier_hund"])).toBe(false);
    expect(appliesTo(d, ["gewerbe"])).toBe(true);
  });
});

describe("facetsUsedBy", () => {
  it("offers only facets some deadline actually uses, in catalog order", () => {
    expect(
      facetsUsedBy([deadline(), deadline(["gewerbe"]), deadline(["auto"])]),
    ).toEqual(["auto", "gewerbe"]);
  });
});
