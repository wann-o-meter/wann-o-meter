import { describe, expect, it } from "vitest";
import { currentWindow, nextWindow } from "./windows";
import type { MaterializedWindow } from "./schema";

function window(from: string, to: string): MaterializedWindow {
  return {
    subject_id: "s",
    year: 2027,
    from,
    to,
    type: "optimal",
    precision: "exact",
    ics: true,
    description: "",
    source: [],
  };
}

const list = [window("2027-01-01", "2027-01-05"), window("2027-03-01", "2027-03-10")];

describe("currentWindow", () => {
  it("finds the window that contains the date", () => {
    expect(currentWindow(list, new Date("2027-01-03T12:00:00Z"))?.from).toBe("2027-01-01");
  });

  it("returns undefined when no window matches", () => {
    expect(currentWindow(list, new Date("2027-02-01T12:00:00Z"))).toBeUndefined();
  });
});

describe("nextWindow", () => {
  it("finds the next future window", () => {
    expect(nextWindow(list, new Date("2027-01-06T12:00:00Z"))?.from).toBe("2027-03-01");
  });

  it("returns undefined when no future window exists", () => {
    expect(nextWindow(list, new Date("2027-12-01T12:00:00Z"))).toBeUndefined();
  });
});
