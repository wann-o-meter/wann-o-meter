import { readFileSync } from "node:fs";
import { load } from "js-yaml";
import { describe, expect, it } from "vitest";
import { evaluateRule, nextOccurrence } from "./calendar-rule";
import { computeSchedule, deadlineSchema } from "./deadline-plan";

// Straight from the yaml, so a wrong rule fails here and not only in the
// browser.
const task = deadlineSchema.parse(
  (load(readFileSync("data/fristen/steuererklaerung.yaml", "utf8")) as any)
    .deadlines[0],
);
const rule = task.rule!;
const due = (year: number, region?: string) =>
  evaluateRule(rule, year, "DE", region)?.date;

describe("Steuererklärung, § 149 Abs. 2 AO", () => {
  it("falls seven months after the end of the calendar year", () => {
    expect(due(2024)).toBe("2025-07-31"); // Thursday
    expect(due(2025)).toBe("2026-07-31"); // Friday
    expect(due(2027)).toBe("2028-07-31"); // Monday
  });

  it("runs to the next working day when it lands on a Saturday", () => {
    expect(due(2026)).toBe("2027-08-02"); // 31.07.2027 is a Saturday
  });

  it("answers nothing for the years Art. 97 § 36 EGAO stretched", () => {
    expect(due(2023)).toBeUndefined();
    expect(due(2020)).toBeUndefined();
  });

  // This is why the task needs no Bundesland: over every year the holiday table
  // covers, the roll only ever steps off a weekend, never off a holiday that
  // some Bundesländer have and others do not.
  it("lands on the same day in every Bundesland", () => {
    for (let year = 2024; year <= 2028; year++)
      for (const state of ["BW", "BY", "BE", "SN", "NW", "SL", "TH", "HH"])
        expect(due(year, state)).toBe(due(year));
  });
});

describe("evaluateRule", () => {
  it("walks only the steps the yaml names", () => {
    const plain = { from: "end-of-year" as const, add_months: 7 };
    // No roll step, so the Saturday stands.
    expect(evaluateRule(plain, 2026, "DE")?.date).toBe("2027-07-31");
  });

  it("snaps to the end of the month it landed in", () => {
    const advised = {
      from: "end-of-year" as const,
      add_months: 14,
      snap: "end-of-month" as const,
    };
    expect(evaluateRule(advised, 2026, "DE")?.date).toBe("2028-02-29");
  });

  it("records every step it took", () => {
    expect(evaluateRule(rule, 2026, "DE")?.derivation.map((s) => s.step)).toEqual(
      ["start", "add-months", "next-working-day"],
    );
  });
});

describe("nextOccurrence", () => {
  const next = (from: string) => nextOccurrence(rule, from, "DE")?.date;

  it("finds the next deadline on or after a day", () => {
    expect(next("2027-03-01")).toBe("2027-08-02");
    expect(next("2027-08-02")).toBe("2027-08-02");
    expect(next("2027-08-03")).toBe("2028-07-31");
  });

  it("keeps a deadline open until its rolled day, not its raw one", () => {
    expect(next("2027-08-01")).toBe("2027-08-02");
  });
});

describe("an absolute task inside a plan", () => {
  it("ignores the anchor and states the statutory day", () => {
    const [entry] = computeSchedule("2027-03-01", [task], "DE", "BW");
    expect(entry.date).toBe("2027-08-02");
  });

  it("moves on once this year's deadline has run out", () => {
    const [entry] = computeSchedule("2027-09-01", [task], "DE", "BW");
    expect(entry.date).toBe("2028-07-31");
  });
});

describe("deadlineSchema", () => {
  it("ties the rule to the absolute kind", () => {
    expect(task.kind).toBe("statutory-absolute");
    expect(
      deadlineSchema.safeParse({ ...task, kind: "statutory-relative" }).success,
    ).toBe(false);
    expect(deadlineSchema.safeParse({ ...task, rule: undefined }).success).toBe(
      false,
    );
  });
});
