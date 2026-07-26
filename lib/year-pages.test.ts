import { describe, expect, it } from "vitest";
import {
  buildYearIndex,
  eventYears,
  eventsInYear,
  siblingPages,
  stateSlug,
  yearCopy,
  yearHref,
  yearIndex,
  yearLabel,
  yearSubject,
  yearSubjectCode,
  yearsForPage,
} from "./year-pages";
import { parsePageData, parsePageMeta } from "./pages-schema";
import { holidaySource } from "./materialization";
import type { Page, PageEvent } from "./pages";

const weihnachtsferien: PageEvent = { date: "2026-12-23", to: "2027-01-06", label: "Weihnachtsferien" };
const sommerferien: PageEvent = { date: "2026-07-19", to: "2026-08-31", label: "Sommerferien" };

// Minimal real Page, so the copy/subject helpers are exercised through the
// same shape the route passes them.
function page(category: string, slug: string, title: string, windows: unknown[] = []): Page {
  return {
    category,
    slug,
    meta: parsePageMeta({ title }),
    data: parsePageData({ subject: { slug, category }, source: [holidaySource()], windows }),
  };
}

function window(from: string, to: string, name = "Termin") {
  return { type: "holiday", year: Number(from.slice(0, 4)), from, to, precision: "exact", ics: true, name };
}

describe("a window that straddles New Year belongs to both years", () => {
  // The one defect a passing `astro build` cannot reveal: NW's Weihnachtsferien
  // carry `year: 2026` and start in 2026, so start-year filtering drops them
  // from "Schulferien NRW 2027" and January looks empty.
  it("counts both years it touches", () => {
    expect(eventYears([weihnachtsferien])).toEqual([2026, 2027]);
  });

  it("shows up on the later year's page too", () => {
    expect(eventsInYear([sommerferien, weihnachtsferien], 2027)).toEqual([weihnachtsferien]);
  });

  it("still shows up on the earlier year's page", () => {
    expect(eventsInYear([sommerferien, weihnachtsferien], 2026)).toEqual([sommerferien, weihnachtsferien]);
  });

  it("leaves untouched years empty", () => {
    expect(eventsInYear([sommerferien, weihnachtsferien], 2028)).toEqual([]);
  });
});

describe("state slugs never collide with a country", () => {
  // /feiertage/bw/ is Botswana and /feiertage/by/ is Belarus - both real pages
  // in data/feiertage/generator.ts. A bare code here would send every sibling
  // link to the wrong country.
  it("namespaces Feiertage's German pages", () => {
    expect(stateSlug("feiertage", "BW")).toBe("de-bw");
  });

  it("round-trips back to the state code", () => {
    expect(yearSubjectCode("feiertage", "de-bw")).toBe("BW");
    expect(yearSubjectCode("urlaubsfenster", "nw")).toBe("NW");
  });

  it("treats a Feiertage country page as a non-state subject", () => {
    expect(yearSubjectCode("feiertage", "bw")).toBeUndefined(); // Botswana
    expect(yearSubjectCode("saisonkalender", "spargel")).toBeUndefined();
  });
});

describe("titles carry the abbreviation people actually search for", () => {
  it("uses the abbreviation in H1 and title", () => {
    const p = page("urlaubsfenster", "nw", "Brückentage Nordrhein-Westfalen");
    const copy = yearCopy(p, 2027, [{ date: "2027-05-14", label: "x", value: 4 }]);
    expect(copy.h1).toBe("Brückentage NRW 2027");
    expect(copy.title).toBe("Brückentage NRW 2027 – optimale Urlaubsfenster Nordrhein-Westfalen");
    expect(copy.description).toContain("Nordrhein-Westfalen");
  });

  it("drops the redundant tail when the state has no abbreviation", () => {
    const copy = yearCopy(page("schulferien", "by", "Schulferien Bayern"), 2027, [sommerferien]);
    expect(copy.h1).toBe("Schulferien Bayern 2027");
    expect(copy.title).toBe("Schulferien Bayern 2027 – Ferientermine");
  });

  it("falls back to the page's own title for a non-state page", () => {
    const p = page("astronomie", "sonnenfinsternis", "Sonnenfinsternis");
    expect(yearSubject(p).label).toBe("Sonnenfinsternis");
    expect(yearLabel(p, 2027)).toBe("Sonnenfinsternis 2027");
    const copy = yearCopy(p, 2027, [{ date: "2027-08-02", label: "Sonnenfinsternis" }]);
    expect(copy.h1).toBe("Sonnenfinsternis 2027");
    expect(copy.intro).toContain("02.08.2027");
    expect(copy.faq[0].question).toBe("Wann ist Sonnenfinsternis 2027?");
  });
});

describe("copy is driven by the data, not by the category", () => {
  it("leads with the best entry only when the rows carry a ratio", () => {
    const withRatio = yearCopy(page("urlaubsfenster", "nw", "Brückentage Nordrhein-Westfalen"), 2027, [
      { date: "2027-05-14", label: "Mit 1 Urlaubstag 4 Tage frei", value: 4 },
      { date: "2027-06-01", label: "Mit 2 Urlaubstagen 5 Tage frei", value: 2.5 },
    ]);
    expect(withRatio.intro).toContain("Der beste:");
    const withoutRatio = yearCopy(page("astronomie", "mondfinsternis", "Mondfinsternis"), 2027, [
      { date: "2027-07-18", label: "Mondfinsternis" },
    ]);
    expect(withoutRatio.intro).not.toContain("Der beste:");
    expect(withoutRatio.intro).toContain("18.07.2027");
  });

  it("says nothing rather than something false for an empty year", () => {
    const copy = yearCopy(page("feiertage", "de-nw", "Deutschland – Nordrhein-Westfalen"), 2099, []);
    expect(copy.faq).toEqual([]);
    expect(copy.intro).toContain("keine Termine");
  });

  it("every FAQ answer is non-empty, so the JSON-LD always has a visible counterpart", () => {
    const copy = yearCopy(page("schulferien", "nw", "Schulferien Nordrhein-Westfalen"), 2026, [
      sommerferien,
      weihnachtsferien,
    ]);
    expect(copy.faq.length).toBeGreaterThan(0);
    for (const item of copy.faq) {
      expect(item.question.trim()).not.toBe("");
      expect(item.answer.trim()).not.toBe("");
    }
  });
});

describe("which years get a page", () => {
  it("gives every year in the data a page, however far it reaches", () => {
    // Uncapped on purpose: a cap would mean some pills navigate and others
    // filter in place, which is the one thing a visitor must not be able to
    // feel. The wide row is handled by the pager, not by generating less.
    const eclipses = page(
      "astronomie",
      "sonnenfinsternis",
      "Sonnenfinsternis",
      [1901, 2020, 2026, 2027, 2036, 2100].map((y) => window(`${y}-08-02`, `${y}-08-02`)),
    );
    expect(yearsForPage(eclipses)).toEqual([1901, 2020, 2026, 2027, 2036, 2100]);
  });

  it("gives a single-year page no year pages at all - it would duplicate itself", () => {
    const oneYear = page("feste", "stadtfest", "Stadtfest", [window("2026-08-15", "2026-08-17")]);
    expect(yearsForPage(oneYear)).toEqual([]);
  });

  it("skips years the source has no data for", () => {
    const gappy = page("x", "y", "Y", [window("2026-01-01", "2026-01-01"), window("2029-01-01", "2029-01-01")]);
    expect(yearsForPage(gappy)).toEqual([2026, 2029]);
  });
});

describe("cross-links point at pages that exist", () => {
  const nwUrlaub = page("urlaubsfenster", "nw", "Brückentage Nordrhein-Westfalen");
  const all = [
    nwUrlaub,
    page("schulferien", "nw", "Schulferien Nordrhein-Westfalen"),
    page("feiertage", "de-nw", "Deutschland – Nordrhein-Westfalen"),
    page("feiertage", "nw", "Botswana-ish decoy"),
    page("astronomie", "sonnenfinsternis", "Sonnenfinsternis"),
    page("astronomie", "mondfinsternis", "Mondfinsternis"),
  ];

  it("links a state to the same state in the other topics, never to a country", () => {
    expect(siblingPages(nwUrlaub, all).map((p) => `${p.category}/${p.slug}`)).toEqual([
      "schulferien/nw",
      "feiertage/de-nw",
    ]);
  });

  it("links a non-state page to its neighbours in the same category", () => {
    const sun = all.find((p) => p.slug === "sonnenfinsternis")!;
    expect(siblingPages(sun, all).map((p) => p.slug)).toEqual(["mondfinsternis"]);
  });

  it("builds hrefs that match the generated paths", () => {
    expect(yearHref("feiertage", "de-nw", 2027)).toBe("/feiertage/de-nw/2027/");
    expect(yearHref("astronomie", "sonnenfinsternis", 2027)).toBe("/astronomie/sonnenfinsternis/2027/");
  });
});

describe("the real site's year index", () => {
  const index = yearIndex();

  it("covers all 16 states for each of the three state topics", () => {
    for (const topic of ["urlaubsfenster", "schulferien", "feiertage"] as const) {
      const keys = [...index.keys()].filter((k) => k.startsWith(`${topic}/`));
      expect(keys.length, topic).toBeGreaterThanOrEqual(16);
    }
  });

  it("generates no empty year pages", () => {
    for (const years of index.values()) expect(years.length).toBeGreaterThan(0);
  });

  it("covers the eclipse pages' full range, so every pill has a page", () => {
    const years = index.get("astronomie/sonnenfinsternis");
    expect(years, "sonnenfinsternis should have year pages").toBeDefined();
    expect(Math.min(...years!)).toBe(1901);
    expect(Math.max(...years!)).toBe(2100);
  });

  it("is empty for a fixture with nothing dated", () => {
    expect(buildYearIndex([page("x", "y", "Y")]).size).toBe(0);
  });
});
