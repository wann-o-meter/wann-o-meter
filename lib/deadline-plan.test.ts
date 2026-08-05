import { describe, expect, it } from "vitest";
import { computeSchedule } from "./deadline-plan";
import type { Deadline } from "./deadline-plan";

const deadline = (over: Partial<Deadline>): Deadline => ({
  id: "x",
  label: "x",
  offset_days: 0,
  source_url: null,
  ...over,
});

describe("computeSchedule", () => {
  it("resolves offsets before and after the anchor day", () => {
    const [before, onDay, after] = computeSchedule(
      "2027-06-15",
      [
        deadline({ id: "after", offset_days: 14 }),
        deadline({ id: "before", offset_days: -7 }),
        deadline({ id: "on", offset_days: 0 }),
      ],
      "DE",
      "BW",
    );
    expect(before.id).toBe("before");
    expect(before.date).toBe("2027-06-08");
    expect(onDay.id).toBe("on");
    expect(onDay.date).toBe("2027-06-15");
    expect(after.id).toBe("after");
    expect(after.date).toBe("2027-06-29");
  });

  it("sorts unknown offsets last without dropping them", () => {
    const result = computeSchedule(
      "2027-06-15",
      [deadline({ id: "known", offset_days: -1 }), deadline({ id: "unknown", offset_days: null })],
      "DE",
      "BW",
    );
    expect(result.map((r) => r.id)).toEqual(["known", "unknown"]);
    expect(result[1].date).toBeNull();
  });

  it("flags a date that lands on a public holiday", () => {
    const [entry] = computeSchedule("2027-10-03", [deadline({ id: "tag-der-einheit", offset_days: 0 })], "DE", "BW");
    expect(entry.collision).toBe("Tag der Deutschen Einheit");
  });

  it("flags a date that lands on a weekend", () => {
    // 2027-06-13 is a Sunday
    const [entry] = computeSchedule("2027-06-13", [deadline({ id: "sonntag", offset_days: 0 })], "DE", "BW");
    expect(entry.weekend).toBe(true);
  });
});
