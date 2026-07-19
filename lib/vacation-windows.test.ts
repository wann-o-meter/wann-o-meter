import { describe, expect, it } from "vitest";
import { calculateOptimalWindows, overlapsRange } from "./vacation-windows";
import { holidaysFor } from "./holidays";

describe("calculateOptimalWindows", () => {
  it("recognizes a classic one-day bridge (Thursday holiday -> Friday off)", () => {
    // 2027-05-06 is a Thursday (synthetic holiday)
    const windows = calculateOptimalWindows(2027, [{ date: "2027-05-06", name: "Test" }]);
    const bridge = windows.find((f) => f.from === "2027-05-06");
    expect(bridge).toEqual({
      from: "2027-05-06",
      to: "2027-05-09",
      requiredVacationDays: 1,
      totalDaysOff: 4,
      efficiency: 4,
    });
  });

  it("finds the real Ascension Day bridge via date-holidays data", () => {
    const holidays = holidaysFor(2027, "BW");
    const windows = calculateOptimalWindows(2027, holidays);
    const ascension = windows.find((f) => f.from === "2027-05-06");
    expect(ascension?.requiredVacationDays).toBe(1);
    expect(ascension?.to).toBe("2027-05-09");
  });

  it("ignores workday blocks longer than maxVacationDays", () => {
    const windows = calculateOptimalWindows(2027, [], 4);
    // no holidays -> every workday block between weekends is 5 days long
    expect(windows).toHaveLength(0);
  });

  it("sorts by efficiency descending", () => {
    const holidays = holidaysFor(2027, "BW");
    const windows = calculateOptimalWindows(2027, holidays);
    for (let i = 1; i < windows.length; i++) {
      expect(windows[i - 1].efficiency).toBeGreaterThanOrEqual(windows[i].efficiency);
    }
  });
});

describe("overlapsRange", () => {
  it("detects overlap", () => {
    expect(
      overlapsRange("2027-05-06", "2027-05-09", { from: "2027-05-08", to: "2027-05-20" }),
    ).toBe(true);
  });

  it("detects no overlap", () => {
    expect(
      overlapsRange("2027-05-06", "2027-05-09", { from: "2027-06-01", to: "2027-06-10" }),
    ).toBe(false);
  });
});
