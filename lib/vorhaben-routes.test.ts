import { describe, expect, it } from "vitest";
import { vorhabenRoutes } from "./vorhaben-routes";
import { PLAN_SEGMENT } from "./plan-url";
import { appliesTo } from "./facets";

// /<vorhaben>/<ort>/ and /<vorhaben>/plan/ share a path segment, so a Gemeinde
// named like a reserved word would take the plan page's address. The build has
// to fail here, not in production.
describe("reserved path segments", () => {
  const RESERVED = [PLAN_SEGMENT];

  it("never gives a variant a reserved slug", () => {
    const clashes = vorhabenRoutes()
      .map((r) => r.variant.slug)
      .filter((slug) => RESERVED.includes(slug));
    expect(clashes).toEqual([]);
  });
});

// A page without a single Paragraf may not call its steps Fristen. Nothing else
// on the page can say it either, so title and description are checked together.
describe("a plan without statutes never promises a Frist", () => {
  it("says Schritte instead", () => {
    const lying = vorhabenRoutes()
      .filter(
        (r) =>
          !r.variant.deadlines.some(
            (d) => appliesTo(d, []) && d.kind !== "soft" && d.source_label,
          ),
      )
      .filter((r) => /Frist/.test(`${r.title} ${r.description}`))
      .map((r) => r.path);
    expect(lying).toEqual([]);
  });
});
