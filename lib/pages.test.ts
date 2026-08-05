import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { rollingYears } from "./materialization";
import {
  getAllPages,
  getCategoryMeta,
  getPageDates,
  getPageEvents,
  loadCategoryTreeForTests,
  pageLocation,
  RESERVED_CATEGORIES,
  type Page,
} from "./pages";

const FIXTURE_ROOT = join(process.cwd(), "lib/fixtures/category-tree");

// Loaded once and reused by every describe block below instead of the
// getAllPages()-family singletons, which are hardwired to the real
// DATA_ROOT (see loadCategoryTreeForTests()'s doc comment in lib/pages.ts) -
// a checked-in fixture tree outside data/ means these tests never depend on
// what real content happens to exist.
const { pages: fixturePages, nodes: fixtureNodes } = loadCategoryTreeForTests(FIXTURE_ROOT);

// Reserved from the directory WALK (so the walk and a generator never
// double-produce the same category), but still populated via GENERATORS
// (lib/pages.ts) - the one deliberate exception to "no page's category is
// reserved" below.
const GENERATOR_BACKED_CATEGORIES = ["feiertage", "urlaubsfenster"];

// Minimal literal Page fixtures for the pure getPageDates()/getPageEvents()
// functions below - no disk fixture needed since these take a Page value
// directly.
const fixtureDatesPage: Page = {
  category: "fixture",
  slug: "dates-fixture",
  meta: { title: "Dates Fixture", description: "", intro: "", tags: [], featured: true },
  data: {
    subject: { slug: "dates-fixture", category: "fixture" },
    source: [
      {
        url: "https://example.invalid/dates-fixture",
        license: "own_derivation",
        retrieved_at: "2026-01-01",
        extraction: "manual",
      },
    ],
    windows: [],
    raw_data: { kind: "html_page", dates: ["12.08.2026", "02.08.27", "2028-01-01", "not-a-date"] },
  },
};

const emptyPage: Page = {
  category: "fixture",
  slug: "empty-fixture",
  meta: { title: "Empty Fixture", description: "", intro: "", tags: [], featured: true },
  data: {
    subject: { slug: "empty-fixture", category: "fixture" },
    source: [
      {
        url: "https://example.invalid/empty-fixture",
        license: "own_derivation",
        retrieved_at: "2026-01-01",
        extraction: "manual",
      },
    ],
    windows: [],
    raw_data: {},
  },
};

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

  it("finds a fixture page by category and slug", () => {
    const page = fixturePages.find(
      (p) => p.category === "fixture/nested/deep-category" && p.slug === "example-page",
    );
    expect(page).toBeDefined();
    expect(page!.data.source[0].url).toBe("https://example.invalid/fixture");
    expect(page!.data.raw_data.kind).toBe("html_page");
  });
});

describe("getAllCategories / getPagesInCategory", () => {
  it("discovers categories from the walked fixture tree", () => {
    const categories = [...new Set(fixturePages.map((p) => p.category))];
    expect(categories).toContain("fixture/nested/deep-category");
  });

  it("scopes pages to their category", () => {
    const pages = fixturePages.filter((p) => p.category === "fixture/nested/deep-category");
    expect(pages.length).toBeGreaterThan(0);
    expect(pages.every((p) => p.category === "fixture/nested/deep-category")).toBe(true);
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
    expect(getCategoryMeta("religioese-feiertage", FIXTURE_ROOT).name).toBe("Religiöse Feiertage");
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
  it("loads a page 3 levels deep with the full '/'-joined path as its category", () => {
    const page = fixturePages.find(
      (p) => p.category === "fixture/nested/deep-category" && p.slug === "example-page",
    );
    expect(page).toBeDefined();
    expect(page!.meta.tags).toContain("fixture");
  });

  it("reports only the leaf-with-pages path in the page list, not intermediate nodes", () => {
    const categories = [...new Set(fixturePages.map((p) => p.category))];
    expect(categories).toContain("fixture/nested/deep-category");
    expect(categories).not.toContain("fixture");
    expect(categories).not.toContain("fixture/nested");
  });

  it("does not treat a _-prefixed directory as a category", () => {
    expect([...fixtureNodes.keys()]).not.toContain("_sources");
    expect(fixturePages.map((p) => p.category)).not.toContain("_sources");
  });

  it("exposes every node, intermediate and leaf, via the returned node map", () => {
    const paths = [...fixtureNodes.keys()];
    expect(paths).toEqual(expect.arrayContaining(["fixture", "fixture/nested", "fixture/nested/deep-category"]));

    const top = fixtureNodes.get("fixture")!;
    expect(top.pages).toEqual([]);
    expect(top.childPaths).toEqual(["fixture/nested"]);

    const mid = fixtureNodes.get("fixture/nested")!;
    expect(mid.pages).toEqual([]);
    expect(mid.childPaths).toEqual(["fixture/nested/deep-category"]);

    const leaf = fixtureNodes.get("fixture/nested/deep-category")!;
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
    expect(fixturePages.filter((p) => p.category === "fixture")).toEqual([]);
    expect(fixturePages.filter((p) => p.category === "fixture/nested/deep-category")).toHaveLength(1);
  });
});

describe("getAllTags / getPagesByTag", () => {
  it("collects tags across all pages and filters by them", () => {
    const tags = [...new Set(fixturePages.flatMap((p) => p.meta.tags))];
    expect(tags).toContain("fixture");
    const matches = fixturePages.filter((p) => p.meta.tags.includes("fixture"));
    expect(matches.length).toBeGreaterThan(0);
    expect(matches.every((p) => p.meta.tags.includes("fixture"))).toBe(true);
  });
});

describe("pageLocation", () => {
  const page = (category: string, slug: string): Page => ({
    ...emptyPage,
    category,
    slug,
  });

  it("resolves a German feiertage state page from its de-{code} slug", () => {
    expect(pageLocation(page("feiertage", "de-by"))).toEqual({ name: "Bayern", addressRegion: "Bayern", addressCountry: "DE" });
  });

  it("resolves a schulferien/urlaubsfenster page from its bare state-code slug", () => {
    expect(pageLocation(page("schulferien", "by"))?.name).toBe("Bayern");
    expect(pageLocation(page("urlaubsfenster", "by"))?.name).toBe("Bayern");
  });

  it("falls back to the country name for feiertage's non-German country pages", () => {
    const tn = pageLocation(page("feiertage", "tn"));
    expect(tn?.name).toBeTruthy();
    expect(tn?.addressCountry).toBe("TN");
    expect(tn).not.toHaveProperty("addressRegion");
  });

  it("returns undefined for categories with no real region", () => {
    expect(pageLocation(page("fixture", "empty-fixture"))).toBeUndefined();
    expect(pageLocation(page("saisonkalender", "gruenkohl"))).toBeUndefined();
  });
});

describe("getPageDates", () => {
  it("normalizes found dd.mm.yyyy / dd.mm.yy / iso strings into sorted ISO dates", () => {
    const dates = getPageDates(fixtureDatesPage);
    expect(dates).toEqual(["2026-08-12", "2027-08-02", "2028-01-01"]);
    for (const d of dates) expect(d).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(dates).toEqual([...dates].sort());
  });
});

describe("getPageEvents", () => {
  it("returns no events for a page with neither windows nor raw dates", () => {
    expect(getPageEvents(emptyPage)).toEqual([]);
  });

  it("falls back to getPageDates with a generic label when raw_data has no llm_events", () => {
    const events = getPageEvents(fixtureDatesPage);
    expect(events.map((e) => e.date)).toEqual(getPageDates(fixtureDatesPage));
    expect(events.every((e) => e.label === "im Quelltext gefundenes Datum")).toBe(true);
  });

  it("prefers valid llm_events over the raw dates fallback, sorted and filtered", () => {
    const withLlmEvents: Page = {
      ...fixtureDatesPage,
      data: {
        ...fixtureDatesPage.data,
        raw_data: {
          ...fixtureDatesPage.data.raw_data,
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

  // The rolling year set is for TEMPLATES, not for facts. Long-range sources
  // exist (data/astronomie/sonnenfinsternis: 452 eclipses, 1901-2100) and a
  // window that names its own year must survive regardless of how far outside
  // the rolling window it sits - it used to be silently dropped, which made
  // such a page show three rows instead of 452. Guards line 347's per-window
  // year set against being "simplified" back to a single rollingYears().
  it("keeps a dated window outside the rolling years while still rolling out a recurring one", () => {
    const windowsPage: Page = {
      ...emptyPage,
      data: {
        ...emptyPage.data,
        windows: [
          {
            type: "event",
            year: 1901,
            from: "1901-05-18",
            to: "1901-05-18",
            precision: "exact",
            ics: true,
            name: "Sonnenfinsternis",
          },
          { type: "main_season", year: null, from: "--08", to: "--09", precision: "approximate", ics: false },
        ],
      },
    };

    const events = getPageEvents(windowsPage);
    expect(events.filter((e) => e.date.startsWith("1901"))).toEqual([
      { date: "1901-05-18", to: undefined, label: "Sonnenfinsternis", value: undefined },
    ]);
    // The recurring window is a template with no year of its own, so it still
    // resolves once per rolling year and no further.
    const recurring = events.filter((e) => e.label === "main_season");
    expect(recurring.map((e) => e.date.slice(0, 4))).toEqual(rollingYears().map(String));
  });
});
