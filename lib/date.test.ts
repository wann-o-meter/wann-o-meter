import { describe, expect, it } from "vitest";
import { endOfMonth, monthKey, shiftMonth } from "./date";

const shifted = (yyyyMm: string, n: number) => {
  const { year, month0 } = shiftMonth(yyyyMm, n);
  return monthKey(year, month0);
};

describe("shiftMonth", () => {
  it("stays inside the year", () => {
    expect(shifted("2027-06", 1)).toBe("2027-07");
    expect(shifted("2027-06", -2)).toBe("2027-04");
  });

  // § 573c counts two months back, which in January and February lands in the
  // year before. Getting the sign wrong here moves a Kündigung by a year.
  it("wraps backwards across the year boundary", () => {
    expect(shifted("2027-01", -2)).toBe("2026-11");
    expect(shifted("2027-02", -2)).toBe("2026-12");
    expect(shifted("2027-01", -13)).toBe("2025-12");
  });

  it("wraps forwards across the year boundary", () => {
    expect(shifted("2027-12", 1)).toBe("2028-01");
    expect(shifted("2027-11", 14)).toBe("2029-01");
  });
});

describe("endOfMonth", () => {
  it("finds the last day, leap years included", () => {
    expect(endOfMonth("2027-04")).toBe("2027-04-30");
    expect(endOfMonth("2027-12")).toBe("2027-12-31");
    expect(endOfMonth("2028-02")).toBe("2028-02-29");
    expect(endOfMonth("2027-02")).toBe("2027-02-28");
  });
});
