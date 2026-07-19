import { describe, expect, it } from "vitest";
import { resolution, resolveMonthWindow } from "./date";

describe("resolution", () => {
  it("recognizes month", () => {
    expect(resolution("--08")).toBe("month");
  });
  it("recognizes day", () => {
    expect(resolution("2027-07-29")).toBe("day");
  });
  it("recognizes minute", () => {
    expect(resolution("2026-05-01T06:30")).toBe("minute");
  });
  it("throws on unknown format", () => {
    expect(() => resolution("29.07.2027")).toThrow();
  });
});

describe("resolveMonthWindow", () => {
  it("resolves a normal window within one year", () => {
    expect(resolveMonthWindow("--08", "--11", 2027)).toEqual({
      from: "2027-08-01",
      to: "2027-11-30",
    });
  });

  it("handles year rollover (to < from)", () => {
    expect(resolveMonthWindow("--12", "--04", 2026)).toEqual({
      from: "2026-12-01",
      to: "2027-04-30",
    });
  });

  it("sets to to the last day of the month (including leap years)", () => {
    expect(resolveMonthWindow("--02", "--02", 2028)).toEqual({
      from: "2028-02-01",
      to: "2028-02-29",
    });
  });
});
