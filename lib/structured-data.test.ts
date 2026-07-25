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
  const BY = { name: "Bayern", addressRegion: "Bayern", addressCountry: "DE" };
  const place = {
    "@type": "Place",
    name: "Bayern",
    address: { "@type": "PostalAddress", addressRegion: "Bayern", addressCountry: "DE" },
  };

  it("omits endDate when it equals startDate", () => {
    expect(eventNode({ name: "Neujahr", startDate: "2027-01-01", endDate: "2027-01-01", location: BY })).toEqual({
      "@type": "Event",
      name: "Neujahr",
      startDate: "2027-01-01",
      location: place,
    });
  });

  it("includes endDate when it differs from startDate", () => {
    const node = eventNode({ name: "Sommerferien", startDate: "2027-07-29", endDate: "2027-09-11", location: BY });
    expect(node).toMatchObject({ startDate: "2027-07-29", endDate: "2027-09-11" });
  });

  it("includes url only when given", () => {
    expect(eventNode({ name: "X", startDate: "2027-01-01", location: BY })).not.toHaveProperty("url");
    expect(eventNode({ name: "X", startDate: "2027-01-01", location: BY, url: "/x/" })).toHaveProperty("url", "/x/");
  });

  it("includes description/image only when given", () => {
    const bare = eventNode({ name: "X", startDate: "2027-01-01", location: BY });
    expect(bare).not.toHaveProperty("description");
    expect(bare).not.toHaveProperty("image");
    const full = eventNode({ name: "X", startDate: "2027-01-01", location: BY, description: "d", image: "/og.png" });
    expect(full).toHaveProperty("description", "d");
    expect(full).toHaveProperty("image", "/og.png");
  });

  // Google counts location.address as required alongside location itself -
  // a Place with only a name is reported as an invalid item in Search Console.
  it("always emits a Place with a PostalAddress", () => {
    expect(eventNode({ name: "X", startDate: "2027-01-01", location: BY })).toHaveProperty("location", place);
  });

  it("omits addressRegion when the place is a whole country", () => {
    const node = eventNode({ name: "X", startDate: "2027-01-01", location: { name: "Tunesien", addressCountry: "TN" } });
    expect(node).toHaveProperty("location", {
      "@type": "Place",
      name: "Tunesien",
      address: { "@type": "PostalAddress", addressCountry: "TN" },
    });
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

  it("stamps the site's CC BY 4.0 license and creator", () => {
    const node = datasetNode({ name: "n", description: "d", url: "/u/", distributions: [] }) as {
      license: string;
      creator: { name: string };
    };
    expect(node.license).toBe("https://creativecommons.org/licenses/by/4.0/");
    expect(node.creator.name).toBe("Wann-O-Meter");
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
