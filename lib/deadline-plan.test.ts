import { describe, expect, it } from "vitest";
import { computeSchedule, deadlineSchema } from "./deadline-plan";
import type { Deadline } from "./deadline-plan";

const task = (over: Partial<Deadline>): Deadline => ({
  id: "x",
  kind: "soft",
  belongsTo: [],
  tags: [],
  label: "x",
  offset_days: 0,
  source_url: null,
  ...over,
});

describe("deadlineSchema", () => {
  const base = { id: "x", label: "x", offset_days: 0, source_url: null };
  const accepts = (over: object) =>
    deadlineSchema.safeParse({ ...base, ...over }).success;

  it("requires a direction on statutory tasks and forbids one on soft", () => {
    expect(accepts({ kind: "soft" })).toBe(true);
    expect(accepts({ kind: "soft", direction: "before" })).toBe(false);
    expect(accepts({ kind: "statutory-relative" })).toBe(false);
    expect(accepts({ kind: "statutory-relative", direction: "after" })).toBe(
      true,
    );
  });

  it("rejects a task without a kind", () => {
    expect(accepts({})).toBe(false);
    expect(accepts({ kind: "erfahrungswert" })).toBe(false);
  });
});

describe("computeSchedule", () => {
  it("resolves offsets around the anchor and sorts undated last", () => {
    const result = computeSchedule(
      "2027-06-15",
      [
        task({ id: "after", offset_days: 14 }),
        task({ id: "undated", offset_days: null }),
        task({ id: "before", offset_days: -7 }),
      ],
      "DE",
      "BW",
    );
    expect(result.map((r) => [r.id, r.date])).toEqual([
      ["before", "2027-06-08"],
      ["after", "2027-06-29"],
      ["undated", null],
    ]);
  });

  it("rolls a deadline at an Amt off a Feiertag onto the next working day", () => {
    // Neujahr 2027 is a Friday, so the next day anyone can go is the Monday.
    const [entry] = computeSchedule(
      "2026-12-31",
      [task({ offset_days: 1, needs_office: true })],
      "DE",
      "BW",
    );
    expect(entry.movedFrom).toBe("2027-01-01");
    expect(entry.date).toBe("2027-01-04");
  });

  it("leaves a deadline without an Amt on its Feiertag", () => {
    const [entry] = computeSchedule(
      "2026-12-31",
      [task({ offset_days: 1 })],
      "DE",
      "BW",
    );
    expect(entry.date).toBe("2027-01-01");
    expect(entry.collision).toBe("Neujahr");
  });

  it("derives the Kündigungsfrist from § 573c BGB, not from the offset", () => {
    // Ende Juni 2027 kündigen heißt: bis zum dritten Werktag im April 2027.
    // Der fällt auf einen Samstag, also zählt der folgende Werktag.
    const [entry] = computeSchedule(
      "2027-06-15",
      [
        task({
          kind: "statutory-relative",
          direction: "before",
          offset_days: -90,
          offset_rule: "bgb-573c-notice",
        }),
      ],
      "DE",
      "BW",
      "2027-01-01",
    );
    expect(entry.date).toBe("2027-04-05");
    expect(entry.derivation?.length).toBeGreaterThan(0);
  });
});
