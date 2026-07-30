import { describe, expect, it } from "vitest";
import { buildScopeMatrix } from "./scope-matrix";
import { parsePageData, parsePageMeta } from "./pages-schema";
import { holidaySource } from "./materialization";
import type { Page } from "./pages";

function window(from: string, name: string) {
  return { type: "holiday", year: Number(from.slice(0, 4)), from, to: from, precision: "exact", ics: true, name };
}

function feiertagePage(code: string, name: string, windows: unknown[]): Page {
  const slug = `de-${code.toLowerCase()}`;
  return {
    category: "feiertage",
    slug,
    meta: parsePageMeta({ title: `Deutschland – ${name}` }),
    data: parsePageData({ subject: { slug, category: "feiertage" }, source: [holidaySource()], windows }),
  };
}

const bw = feiertagePage("BW", "Baden-Württemberg", [
  window("2026-01-01", "Neujahr"),
  window("2026-06-04", "Fronleichnam"),
]);
const be = feiertagePage("BE", "Berlin", [window("2026-01-01", "Neujahr")]);

describe("buildScopeMatrix", () => {
  it("lists a scope column per state page, sorted by full name", () => {
    const { scopes } = buildScopeMatrix([be, bw], 2026);
    expect(scopes.map((s) => s.name)).toEqual(["Baden-Württemberg", "Berlin"]);
  });

  it("derives a short label from STATE_ABBREVIATIONS where one exists, the code otherwise", () => {
    const { scopes } = buildScopeMatrix([be, bw], 2026);
    expect(scopes.find((s) => s.code === "BW")?.label).toBe("BW");
    expect(scopes.find((s) => s.code === "BE")?.label).toBe("BE");
  });

  it("builds a resolvable href and layer id per scope", () => {
    const { scopes } = buildScopeMatrix([bw], 2026);
    expect(scopes[0]).toMatchObject({ href: "/feiertage/de-bw/", layerId: "feiertage--de-bw" });
  });

  it("groups same-name holidays from different pages into one row", () => {
    const { rows } = buildScopeMatrix([be, bw], 2026);
    const neujahr = rows.find((r) => r.title === "Neujahr");
    expect(neujahr?.dateByScope).toEqual({ BW: "2026-01-01", BE: "2026-01-01" });
  });

  it("leaves a scope's cell null when that state doesn't observe the holiday", () => {
    const { rows } = buildScopeMatrix([be, bw], 2026);
    const fronleichnam = rows.find((r) => r.title === "Fronleichnam");
    expect(fronleichnam?.dateByScope.BW).toBe("2026-06-04");
    expect(fronleichnam?.dateByScope.BE).toBeUndefined();
  });

  it("orders rows chronologically by their earliest date", () => {
    const { rows } = buildScopeMatrix([bw], 2026);
    expect(rows.map((r) => r.title)).toEqual(["Neujahr", "Fronleichnam"]);
  });

  it("ignores a page that isn't state-coded (e.g. a country page, no de- prefix)", () => {
    const at: Page = {
      category: "feiertage",
      slug: "at",
      meta: parsePageMeta({ title: "Österreich" }),
      data: parsePageData({
        subject: { slug: "at", category: "feiertage" },
        source: [holidaySource()],
        windows: [window("2026-01-01", "Neujahr")],
      }),
    };
    const { scopes } = buildScopeMatrix([bw, at], 2026);
    expect(scopes).toHaveLength(1);
  });
});
