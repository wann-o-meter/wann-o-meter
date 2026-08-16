import { describe, expect, it } from "vitest";
import { searchGemeinden } from "./gemeinde-search";
import type { Gemeinde } from "./gemeinde-search";

const list: Gemeinde[] = [
  { name: "Singen (Hohentwiel)", plz: "78224", state: "BW" },
  { name: "Usingen", plz: "61250", state: "HE" },
  { name: "Bisingen", plz: "72406", state: "BW" },
  { name: "München", plz: "80331", state: "BY" },
  { name: "Grafing bei München", plz: "85567", state: "BY" },
  { name: "Tübingen", plz: "72070", state: "BW" },
];

const found = (q: string) => searchGemeinden(list, q, 10).map((g) => g.name);

describe("searchGemeinden", () => {
  it("puts the name that starts with the query above ones that only contain it", () => {
    expect(found("singen")[0]).toBe("Singen (Hohentwiel)");
  });

  it("prefers the shorter name when both start with the query", () => {
    expect(found("münchen")).toEqual(["München", "Grafing bei München"]);
  });

  it("finds a name through umlauts either way round", () => {
    expect(found("munchen")[0]).toBe("München");
    expect(found("tubingen")).toEqual(["Tübingen"]);
  });

  it("matches on the start of a PLZ", () => {
    expect(found("7207")).toEqual(["Tübingen"]);
  });

  it("answers an empty query with nothing", () => {
    expect(found("  ")).toEqual([]);
  });
});
