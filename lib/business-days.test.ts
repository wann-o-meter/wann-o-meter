import { describe, expect, it } from "vitest";
import { isCountingDay, loadHolidays, nthCountingDayOfMonth, rollToLandingDay } from "./business-days";

// Source for the rule itself: § 573c Abs. 1 BGB (implicit context: "der
// dritte Werktag") + BGH, Urt. v. 27.4.2005 - VIII ZR 206/04 (Saturday
// counts when counting, but is never the landing day - see business-days.ts).
// Each fixture applies that rule mechanically to a real calendar (the
// date-holidays package) - the specific holiday(s) load-bearing for each
// case are named below so a fixture can be re-checked against a
// Feiertagskalender directly, not just against this file's own logic.
describe("nthCountingDayOfMonth", () => {
  it("Jan 2024: Neujahr (Jan 1) excluded, third counting day is Jan 4 (Thu) - no roll needed", () => {
    const { date, rolled } = nthCountingDayOfMonth(2024, 0, 3, loadHolidays(2024, "DE"));
    expect(date.toISOString().slice(0, 10)).toBe("2024-01-04");
    expect(rolled).toBe(false);
  });

  it("Jan 2025, nationwide: raw third counting day Jan 4 is a Saturday, rolls to Jan 6 (Mon)", () => {
    const { date, raw, rolled } = nthCountingDayOfMonth(2025, 0, 3, loadHolidays(2025, "DE"));
    expect(raw.toISOString().slice(0, 10)).toBe("2025-01-04");
    expect(rolled).toBe(true);
    expect(date.toISOString().slice(0, 10)).toBe("2025-01-06");
  });

  it("Jan 2025, Baden-Württemberg: Heilige Drei Könige (Jan 6) is ALSO a holiday there, so the roll continues to Jan 7 (Tue) - the region matters", () => {
    const { date, rolled } = nthCountingDayOfMonth(2025, 0, 3, loadHolidays(2025, "DE", "BW"));
    expect(rolled).toBe(true);
    expect(date.toISOString().slice(0, 10)).toBe("2025-01-07");
  });

  it("Jan 2031: same nationwide-vs-BW split as 2025 (Jan 4 is a Saturday again, Jan 6 is Heilige Drei Könige again)", () => {
    const nationwide = nthCountingDayOfMonth(2031, 0, 3, loadHolidays(2031, "DE"));
    const bw = nthCountingDayOfMonth(2031, 0, 3, loadHolidays(2031, "DE", "BW"));
    expect(nationwide.date.toISOString().slice(0, 10)).toBe("2031-01-06");
    expect(bw.date.toISOString().slice(0, 10)).toBe("2031-01-07");
  });

  it("May 2024: Tag der Arbeit (May 1) excluded, raw third counting day May 4 is a Saturday, rolls to May 6 (Mon)", () => {
    const { date, raw, rolled } = nthCountingDayOfMonth(2024, 4, 3, loadHolidays(2024, "DE"));
    expect(raw.toISOString().slice(0, 10)).toBe("2024-05-04");
    expect(rolled).toBe(true);
    expect(date.toISOString().slice(0, 10)).toBe("2024-05-06");
  });

  it("May 2027: May 1 is both a Saturday AND Tag der Arbeit - excluded as a holiday regardless of the weekday, lands cleanly on May 5 (Wed), no roll", () => {
    const { date, rolled } = nthCountingDayOfMonth(2027, 4, 3, loadHolidays(2027, "DE"));
    expect(rolled).toBe(false);
    expect(date.toISOString().slice(0, 10)).toBe("2027-05-05");
  });

  it("Oct 2024: Tag der Deutschen Einheit (Oct 3) falls where the count would otherwise land, pushing the third counting day to Oct 4 - a mid-count exclusion, not a Saturday roll", () => {
    const { date, rolled } = nthCountingDayOfMonth(2024, 9, 3, loadHolidays(2024, "DE"));
    expect(rolled).toBe(false); // Oct 4 is a Friday - the holiday shifted the count, nothing rolled
    expect(date.toISOString().slice(0, 10)).toBe("2024-10-04");
  });

  it("Dec 2026: clean case, no early-month holiday - used as a year-wrap fixture in notice-period.test.ts", () => {
    const { date, rolled } = nthCountingDayOfMonth(2026, 11, 3, loadHolidays(2026, "DE"));
    expect(rolled).toBe(false);
    expect(date.toISOString().slice(0, 10)).toBe("2026-12-03");
  });

  it("never lands on a Sunday, Saturday, or holiday, across a wide sweep of months/years/regions", () => {
    for (let year = 2025; year <= 2032; year++) {
      for (let month0 = 0; month0 < 12; month0++) {
        for (const region of [undefined, "BW"]) {
          const holidays = loadHolidays(year, "DE", region);
          const { date } = nthCountingDayOfMonth(year, month0, 3, holidays);
          const dow = date.getUTCDay();
          expect(dow).not.toBe(0);
          expect(dow).not.toBe(6);
          expect(holidays.dates.has(date.toISOString().slice(0, 10))).toBe(false);
        }
      }
    }
  });
});

describe("rollToLandingDay", () => {
  it("leaves an already-valid landing day untouched", () => {
    const holidays = loadHolidays(2027, "DE");
    const d = new Date(Date.UTC(2027, 0, 6)); // 2027-01-06 is a Wednesday, not a holiday
    expect(rollToLandingDay(d, holidays).getTime()).toBe(d.getTime());
  });

  it("rolls a Saturday forward to the following Monday when Monday is clear", () => {
    const holidays = loadHolidays(2027, "DE");
    const d = new Date(Date.UTC(2027, 0, 2)); // 2027-01-02 is a Saturday
    expect(rollToLandingDay(d, holidays).toISOString().slice(0, 10)).toBe("2027-01-04");
  });
});

describe("isCountingDay", () => {
  it("excludes Sunday and holidays but includes Saturday", () => {
    const holidays = loadHolidays(2024, "DE");
    expect(isCountingDay(new Date(Date.UTC(2024, 0, 6)), holidays)).toBe(true); // Saturday
    expect(isCountingDay(new Date(Date.UTC(2024, 0, 7)), holidays)).toBe(false); // Sunday
    expect(isCountingDay(new Date(Date.UTC(2024, 0, 1)), holidays)).toBe(false); // Neujahr
  });
});
