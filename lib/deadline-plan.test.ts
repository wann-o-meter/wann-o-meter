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
      [
        deadline({ id: "known", offset_days: -1 }),
        deadline({ id: "unknown", offset_days: null }),
      ],
      "DE",
      "BW",
    );
    expect(result.map((r) => r.id)).toEqual(["known", "unknown"]);
    expect(result[1].date).toBeNull();
  });

  it("flags a date that lands on a public holiday", () => {
    const [entry] = computeSchedule(
      "2027-10-03",
      [deadline({ id: "tag-der-einheit", offset_days: 0 })],
      "DE",
      "BW",
    );
    expect(entry.collision).toBe("Tag der Deutschen Einheit");
  });

  it("flags a date that lands on a weekend", () => {
    // 2027-06-13 is a Sunday
    const [entry] = computeSchedule(
      "2027-06-13",
      [deadline({ id: "sonntag", offset_days: 0 })],
      "DE",
      "BW",
    );
    expect(entry.weekend).toBe(true);
  });

  it("defaults earliestDate/startByDate to the deadline itself when unresearched", () => {
    const [entry] = computeSchedule(
      "2027-06-15",
      [deadline({ id: "plain", offset_days: 14 })],
      "DE",
      "BW",
    );
    expect(entry.earliestDate).toBe(entry.date);
    expect(entry.startByDate).toBe(entry.date);
    expect(entry.impossible).toBe(false);
  });

  it("resolves an earlier earliestDate when earliest_offset_days is set", () => {
    const [entry] = computeSchedule(
      "2027-06-15",
      [deadline({ id: "ummeldung", offset_days: 14, earliest_offset_days: 0 })],
      "DE",
      "BW",
    );
    expect(entry.earliestDate).toBe("2027-06-15");
    expect(entry.date).toBe("2027-06-29");
    expect(entry.startByDate).toBe(entry.date);
  });

  it("flags impossible when the lead time pushes startByDate before earliestDate", () => {
    const [entry] = computeSchedule(
      "2027-06-15",
      [
        deadline({
          id: "kfz",
          offset_days: 7, // deadline 2027-06-22
          earliest_offset_days: 0, // earliest 2027-06-15
          lead_time_days: 21, // startBy 2027-06-01, before earliest
        }),
      ],
      "DE",
      "BW",
    );
    expect(entry.startByDate).toBe("2027-06-01");
    expect(entry.earliestDate).toBe("2027-06-15");
    expect(entry.impossible).toBe(true);
  });

  it("uses offset_rule's computed date instead of offset_days when set", () => {
    // Move date in March 2024 -> § 573c notice deadline is 2024-01-04 (see notice-period.test.ts).
    // Explicit `today` keeps this deterministic - the real current date is
    // long past 2024-01-04, which would otherwise trigger the rescue path.
    const [entry] = computeSchedule(
      "2024-03-15",
      [
        deadline({
          id: "wohnung-kuendigen",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
      ],
      "DE",
      undefined,
      "2023-12-01",
    );
    expect(entry.date).toBe("2024-01-04");
    expect(entry.derivation?.length).toBeGreaterThan(0);
    expect(entry.pastDeadline).toBe(false);
  });

  it("pushes the notice deadline a month back when an overlap month is kept", () => {
    // Same move as above, but the old flat is kept through April: the notice
    // deadline moves from the January window to the February one.
    const [entry] = computeSchedule(
      "2024-03-15",
      [
        deadline({
          id: "wohnung-kuendigen",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
      ],
      "DE",
      undefined,
      "2023-12-01",
      1,
    );
    expect(entry.date).toBe("2024-02-05");
  });

  it("orders by the day an entry lands on, not by its offset approximation", () => {
    // The rule's offset_days (-90) would sort it first, but its computed date
    // (2024-01-04) falls after the -120 day entry (2023-11-16).
    const result = computeSchedule(
      "2024-03-15",
      [
        deadline({
          id: "kuendigen",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
        deadline({ id: "frueher", offset_days: -120 }),
      ],
      "DE",
      undefined,
      "2023-10-01",
    );
    expect(result.map((e) => e.id)).toEqual(["frueher", "kuendigen"]);
  });

  it("keeps an expired entry at its own date, not at its rescue date", () => {
    // Notice deadline 2024-01-04 is gone by 2024-02-01, rescue is 2024-02-05.
    // The missed deadline still belongs before the 2024-01-20 entry.
    const result = computeSchedule(
      "2024-03-15",
      [
        deadline({ id: "spaeter", offset_days: -55 }),
        deadline({
          id: "kuendigen",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
      ],
      "DE",
      undefined,
      "2024-02-01",
    );
    expect(result.map((e) => e.id)).toEqual(["kuendigen", "spaeter"]);
    expect(result[0].rescue?.date).toBe("2024-02-05");
  });

  it("reports the tenancy end the rescue month brings, and its overlap", () => {
    // Same expired case: the notice now only works for an end of April, so
    // the old flat runs 46 days past the 15 March move.
    const [entry] = computeSchedule(
      "2024-03-15",
      [
        deadline({
          id: "kuendigen",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
      ],
      "DE",
      undefined,
      "2024-02-01",
    );
    expect(entry.leaseEnd).toEqual({ date: "2024-04-30", overlapDays: 46 });
  });

  it("ends the tenancy with the anchor month when the notice is still in time", () => {
    const [entry] = computeSchedule(
      "2024-03-15",
      [
        deadline({
          id: "kuendigen",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
      ],
      "DE",
      undefined,
      "2023-12-01",
    );
    expect(entry.leaseEnd).toEqual({ date: "2024-03-31", overlapDays: 16 });
  });

  it("rolls a needs_office step off a closed day and remembers the day it left", () => {
    // 2027-06-13 is a Sunday. Only the office step moves.
    const result = computeSchedule(
      "2027-06-13",
      [
        deadline({ id: "amt", offset_days: 7, needs_office: true }),
        deadline({ id: "privat", offset_days: 7 }),
      ],
      "DE",
      "BW",
    );
    const amt = result.find((e) => e.id === "amt")!;
    const privat = result.find((e) => e.id === "privat")!;
    expect(amt.date).toBe("2027-06-21");
    expect(amt.movedFrom).toBe("2027-06-20");
    expect(amt.weekend).toBe(false);
    expect(privat.date).toBe("2027-06-20");
    expect(privat.movedFrom).toBeUndefined();
  });

  it("keeps a needs_office step on the anchor day where it belongs", () => {
    const [entry] = computeSchedule(
      "2027-06-13",
      [deadline({ id: "amt", offset_days: 0, needs_office: true })],
      "DE",
      "BW",
    );
    expect(entry.date).toBe("2027-06-13");
    expect(entry.weekend).toBe(true);
  });

  it("rolls past a public holiday, not just past the weekend", () => {
    // A day after 2027-10-02 is Tag der Deutschen Einheit, so the step lands
    // on the Monday after it.
    const [entry] = computeSchedule(
      "2027-10-02",
      [deadline({ id: "amt", offset_days: 1, needs_office: true })],
      "DE",
      "BW",
    );
    expect(entry.date).toBe("2027-10-04");
    expect(entry.movedFrom).toBe("2027-10-03");
  });

  it("leaves derivation/pastDeadline undefined for plain offset-based entries", () => {
    const [entry] = computeSchedule(
      "2027-06-15",
      [deadline({ id: "plain", offset_days: 14 })],
      "DE",
      "BW",
    );
    expect(entry.derivation).toBeUndefined();
    expect(entry.pastDeadline).toBeUndefined();
  });
});
