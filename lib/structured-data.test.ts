import { describe, expect, it } from "vitest";
import { breadcrumbNode, datasetNode, eventNode, graph, websiteNode } from "./structured-data";

describe("graph", () => {
  it("wraps nodes in a single @context @graph document", () => {
    expect(graph([{ "@type": "Thing" }])).toEqual({
      "@context": "https://schema.org",
      "@graph": [{ "@type": "Thing" }],
    });
  });
});

describe("eventNode", () => {
  it("omits endDate when it equals startDate", () => {
    expect(eventNode({ name: "Neujahr", startDate: "2027-01-01", endDate: "2027-01-01" })).toEqual({
      "@type": "Event",
      name: "Neujahr",
      startDate: "2027-01-01",
    });
  });

  it("includes endDate when it differs from startDate", () => {
    const node = eventNode({ name: "Sommerferien", startDate: "2027-07-29", endDate: "2027-09-11" });
    expect(node).toMatchObject({ startDate: "2027-07-29", endDate: "2027-09-11" });
  });

  it("includes url only when given", () => {
    expect(eventNode({ name: "X", startDate: "2027-01-01" })).not.toHaveProperty("url");
    expect(eventNode({ name: "X", startDate: "2027-01-01", url: "/x/" })).toHaveProperty("url", "/x/");
  });
});

describe("breadcrumbNode", () => {
  it("numbers items starting at 1 in the given order", () => {
    const node = breadcrumbNode([
      { name: "wann", url: "/" },
      { name: "Feiertage", url: "/feiertage/" },
    ]) as { itemListElement: { position: number; name: string }[] };
    expect(node.itemListElement.map((i) => i.position)).toEqual([1, 2]);
    expect(node.itemListElement.map((i) => i.name)).toEqual(["wann", "Feiertage"]);
  });
});

describe("datasetNode", () => {
  it("maps distributions to DataDownload nodes", () => {
    const node = datasetNode({
      name: "Feiertage Baden-Württemberg",
      description: "d",
      url: "/feiertage/de-bw/",
      distributions: [
        { url: "/api/v1/feiertage/de-bw.json", encodingFormat: "application/json" },
        { url: "/feeds/feiertage/de-bw.ics", encodingFormat: "text/calendar" },
      ],
    }) as { distribution: { contentUrl: string }[] };
    expect(node.distribution).toHaveLength(2);
    expect(node.distribution[0].contentUrl).toBe("/api/v1/feiertage/de-bw.json");
  });
});

describe("websiteNode", () => {
  it("builds a WebSite node", () => {
    expect(websiteNode({ name: "wann", url: "https://wann.example", description: "d" })).toEqual({
      "@type": "WebSite",
      name: "wann",
      url: "https://wann.example",
      description: "d",
    });
  });
});
