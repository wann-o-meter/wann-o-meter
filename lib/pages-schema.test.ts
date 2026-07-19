import { describe, expect, it } from "vitest";
import { parsePageData, parsePageMeta } from "./pages-schema";

describe("parsePageMeta", () => {
  it("accepts a title alone, filling description/tags with defaults", () => {
    const meta = parsePageMeta({ title: "Total Solar Eclipses" });
    expect(meta).toEqual({ title: "Total Solar Eclipses", description: "", tags: [], featured: true });
  });

  it("rejects a missing title", () => {
    expect(() => parsePageMeta({ description: "x" })).toThrow();
  });
});

describe("parsePageData", () => {
  const valid = {
    subject: { slug: "total-solar-eclipses-europe", category: "astronomie" },
    source: {
      url: "http://www.sonnenfinsternis.org/total_eu.htm",
      license: "tos_checked",
      retrieved_at: "2026-07-12",
      extraction: "parser",
    },
    raw_data: { kind: "html_page", dates: ["12.08.2026"] },
  };

  it("accepts a valid file with freeform raw_data", () => {
    expect(() => parsePageData(valid)).not.toThrow();
  });

  it("rejects a missing category", () => {
    const doc = { ...valid, subject: { slug: valid.subject.slug } };
    expect(() => parsePageData(doc)).toThrow();
  });

  it("rejects a missing source", () => {
    const { source, ...withoutSource } = valid;
    expect(() => parsePageData(withoutSource)).toThrow();
  });

  it("rejects an unknown license (reused sourceSchema)", () => {
    const doc = { ...valid, source: { ...valid.source, license: "something" } };
    expect(() => parsePageData(doc)).toThrow();
  });

  it("accepts an optional contributed_by on the source, absent by default", () => {
    expect(parsePageData(valid).source[0].contributed_by).toBeUndefined();
    const doc = { ...valid, source: { ...valid.source, contributed_by: "am9zZWY" } };
    expect(parsePageData(doc).source[0].contributed_by).toBe("am9zZWY");
  });

  it("accepts a nested, '/'-joined category path up to the max depth", () => {
    const doc = { ...valid, subject: { ...valid.subject, category: "sport/fussball/bundesliga" } };
    expect(() => parsePageData(doc)).not.toThrow();
  });

  it("rejects a category path deeper than the max depth", () => {
    const doc = { ...valid, subject: { ...valid.subject, category: "a/b/c/d/e" } };
    expect(() => parsePageData(doc)).toThrow();
  });

  it("rejects a category segment with invalid characters (uppercase, spaces, underscores)", () => {
    for (const category of ["Sport/Fussball", "sport fussball", "sport_fussball", "sport//fussball", "-sport"]) {
      const doc = { ...valid, subject: { ...valid.subject, category } };
      expect(() => parsePageData(doc), `expected "${category}" to be rejected`).toThrow();
    }
  });

  it("accepts a single source object and normalizes it to a one-element array", () => {
    const data = parsePageData(valid);
    expect(data.source).toEqual([valid.source]);
  });

  it("accepts an array of sources as-is", () => {
    const secondSource = { ...valid.source, url: "https://example.org/other-source" };
    const doc = { ...valid, source: [valid.source, secondSource] };
    const data = parsePageData(doc);
    expect(data.source).toEqual([valid.source, secondSource]);
  });

  const windowValid = { type: "main_season", year: 2026, from: "2026-08-01", to: "2026-09-30", precision: "approximate" as const, ics: false };

  it("accepts a calendar-style page with windows and no raw_data", () => {
    const doc = { subject: valid.subject, source: valid.source, windows: [windowValid] };
    expect(() => parsePageData(doc)).not.toThrow();
  });

  it("accepts a window whose source_urls reference an existing source", () => {
    const doc = { subject: valid.subject, source: valid.source, windows: [{ ...windowValid, source_urls: [valid.source.url] }] };
    expect(() => parsePageData(doc)).not.toThrow();
  });

  it("accepts a window with source_urls citing multiple sources", () => {
    const secondSource = { ...valid.source, url: "https://example.org/other-source" };
    const doc = {
      subject: valid.subject,
      source: [valid.source, secondSource],
      windows: [{ ...windowValid, source_urls: [valid.source.url, secondSource.url] }],
    };
    expect(() => parsePageData(doc)).not.toThrow();
  });

  it("rejects source_urls referencing a URL not present in source[]", () => {
    const doc = {
      subject: valid.subject,
      source: valid.source,
      windows: [{ ...windowValid, source_urls: ["https://example.org/unknown-source"] }],
    };
    expect(() => parsePageData(doc)).toThrow();
  });
});
