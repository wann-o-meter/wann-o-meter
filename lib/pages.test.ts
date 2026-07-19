import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  getAllCategories,
  getAllPages,
  getAllTags,
  getCategoryMeta,
  getPageByCategoryAndSlug,
  getPageDates,
  getPageEvents,
  getPagesByTag,
  getPagesInCategory,
  loadCategoryTreeForTests,
  RESERVED_CATEGORIES,
  type Page,
} from "./pages";

const FIXTURE_ROOT = join(process.cwd(), "lib/fixtures/category-tree");

// Reserved from the directory WALK (so the walk and a generator never
// double-produce the same category), but still populated via GENERATORS
// (lib/pages.ts) - the one deliberate exception to "no page's category is
// reserved" below.
const GENERATOR_BACKED_CATEGORIES = ["feiertage", "urlaubsfenster"];

describe("getAllPages", () => {
  it("loads and validates every page.yaml + data.yaml pair, skipping reserved category folders", () => {
    const pages = getAllPages();
    expect(pages.length).toBeGreaterThan(0);
    for (const p of pages) {
      expect(p.meta.title.length).toBeGreaterThan(0);
      expect(p.data.source[0].url.length).toBeGreaterThan(0);
      if (!GENERATOR_BACKED_CATEGORIES.includes(p.category)) {
        expect(RESERVED_CATEGORIES).not.toContain(p.category);
      }
    }
  });

  it("includes generator-backed categories even though they're excluded from the directory walk", () => {
    const categories = new Set(getAllPages().map((p) => p.category));
    for (const category of GENERATOR_BACKED_CATEGORIES) {
      expect(categories).toContain(category);
      expect(RESERVED_CATEGORIES).toContain(category);
    }
  });

  it("finds the real seeded eclipse page by category and slug, routed without a generic wrapper", () => {
    const page = getPageByCategoryAndSlug("naturphaenomene", "totale-sonnenfinsternisse");
    expect(page).toBeDefined();
    expect(page!.data.source[0].url).toBe("http://www.sonnenfinsternis.org/total_eu.htm");
    expect(page!.data.raw_data.kind).toBe("html_page");
  });
});

describe("getAllCategories / getPagesInCategory", () => {
  it("discovers categories from the data/ folder structure", () => {
    expect(getAllCategories()).toContain("naturphaenomene");
  });

  it("scopes pages to their category", () => {
    const pages = getPagesInCategory("naturphaenomene");
    expect(pages.length).toBeGreaterThan(0);
    expect(pages.every((p) => p.category === "naturphaenomene")).toBe(true);
  });
});

describe("getCategoryMeta", () => {
  it("reads the display name and description from data/{category}/_category.yaml", () => {
    expect(getCategoryMeta("schulferien")).toEqual({
      name: "Schulferien",
      description: "Schulferientermine je Bundesland (Kultusministerkonferenz).",
    });
  });

  it("preserves special characters a slugified name would lose", () => {
    expect(getCategoryMeta("religioese-feiertage").name).toBe("Religiöse Feiertage");
  });

  it("falls back to a capitalized slug for a category with no _category.yaml", () => {
    expect(getCategoryMeta("does-not-exist")).toEqual({ name: "Does-not-exist", description: "" });
  });
});

// Round-trip coverage for nested categories, against a fixture tree under
// lib/fixtures/category-tree/ (NOT data/ - a checked-in placeholder there
// would build and sitemap as a real, empty-looking page on the live site).
// Exercises loadCategoryTreeForTests()/getCategoryMeta(path, root) directly
// instead of the getAllPages()-family singletons, which are hardwired to the
// real DATA_ROOT. Depth-1 categories are covered above and must keep passing
// unmodified.
describe("nested categories (lib/fixtures/category-tree/fixture/nested/deep-category/)", () => {
  const { pages, nodes } = loadCategoryTreeForTests(FIXTURE_ROOT);

  it("loads a page 3 levels deep with the full '/'-joined path as its category", () => {
    const page = pages.find((p) => p.category === "fixture/nested/deep-category" && p.slug === "example-page");
    expect(page).toBeDefined();
    expect(page!.meta.tags).toContain("fixture");
  });

  it("reports only the leaf-with-pages path in the page list, not intermediate nodes", () => {
    const categories = [...new Set(pages.map((p) => p.category))];
    expect(categories).toContain("fixture/nested/deep-category");
    expect(categories).not.toContain("fixture");
    expect(categories).not.toContain("fixture/nested");
  });

  it("exposes every node, intermediate and leaf, via the returned node map", () => {
    const paths = [...nodes.keys()];
    expect(paths).toEqual(expect.arrayContaining(["fixture", "fixture/nested", "fixture/nested/deep-category"]));

    const top = nodes.get("fixture")!;
    expect(top.pages).toEqual([]);
    expect(top.childPaths).toEqual(["fixture/nested"]);

    const mid = nodes.get("fixture/nested")!;
    expect(mid.pages).toEqual([]);
    expect(mid.childPaths).toEqual(["fixture/nested/deep-category"]);

    const leaf = nodes.get("fixture/nested/deep-category")!;
    expect(leaf.childPaths).toEqual([]);
    expect(leaf.pages).toHaveLength(1);
    expect(leaf.pages[0].slug).toBe("example-page");
  });

  it("getCategoryMeta() reads a nested node's own _category.yaml and falls back per-segment otherwise", () => {
    expect(getCategoryMeta("fixture/nested/deep-category", FIXTURE_ROOT).name).toBe("Deep Category (test fixture)");
    // "fixture" and "fixture/nested" deliberately have no _category.yaml -
    // falls back to a capitalized LAST segment, not the whole joined path.
    expect(getCategoryMeta("fixture", FIXTURE_ROOT).name).toBe("Fixture");
    expect(getCategoryMeta("fixture/nested", FIXTURE_ROOT).name).toBe("Nested");
  });

  it("only matches the exact category path, not descendant pages", () => {
    expect(pages.filter((p) => p.category === "fixture")).toEqual([]);
    expect(pages.filter((p) => p.category === "fixture/nested/deep-category")).toHaveLength(1);
  });
});

describe("getAllTags / getPagesByTag", () => {
  it("collects tags across all pages and filters by them", () => {
    const tags = getAllTags();
    expect(tags).toContain("astronomie");
    const matches = getPagesByTag("astronomie");
    expect(matches.length).toBeGreaterThan(0);
    expect(matches.every((p) => p.meta.tags.includes("astronomie"))).toBe(true);
  });
});

describe("getPageDates", () => {
  it("normalizes found dd.mm.yyyy / dd.mm.yy / iso strings into sorted ISO dates", () => {
    const page = getPageByCategoryAndSlug("naturphaenomene", "totale-sonnenfinsternisse")!;
    const dates = getPageDates(page);
    expect(dates).toContain("2026-08-12");
    expect(dates).toContain("2027-08-02");
    for (const d of dates) expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(dates).toEqual([...dates].sort());
  });
});

describe("getPageEvents", () => {
  // The real seeded eclipse page has since been enriched with llm_events by
  // the pipeline (see the next test) - this test needs a page WITHOUT them
  // to exercise the fallback branch, so it constructs one explicitly rather
  // than assuming today's content state of a real page.
  it("falls back to getPageDates with a generic label when raw_data has no llm_events", () => {
    const page = getPageByCategoryAndSlug("naturphaenomene", "totale-sonnenfinsternisse")!;
    const withoutLlmEvents: Page = {
      ...page,
      data: { ...page.data, raw_data: { ...page.data.raw_data, llm_events: undefined } },
    };
    const events = getPageEvents(withoutLlmEvents);
    expect(events.map((e) => e.date)).toEqual(getPageDates(withoutLlmEvents));
    expect(events.every((e) => e.label === "im Quelltext gefundenes Datum")).toBe(true);
  });

  it("prefers valid llm_events over the raw dates fallback, sorted and filtered", () => {
    const page = getPageByCategoryAndSlug("naturphaenomene", "totale-sonnenfinsternisse")!;
    const withLlmEvents: Page = {
      ...page,
      data: {
        ...page.data,
        raw_data: {
          ...page.data.raw_data,
          llm_events: [
            { date: "2026-09-06", label: "Landtagswahl" },
            { date: "not-a-date", label: "invalid, must be dropped" },
            { date: "2026-01-01", label: "Neujahr" },
          ],
        },
      },
    };
    expect(getPageEvents(withLlmEvents)).toEqual([
      { date: "2026-01-01", label: "Neujahr" },
      { date: "2026-09-06", label: "Landtagswahl" },
    ]);
  });
});
