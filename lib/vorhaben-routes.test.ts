import { describe, expect, it } from "vitest";
import { vorhabenRoutes } from "./vorhaben-routes";
import { PLAN_SEGMENT } from "./plan-url";

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
