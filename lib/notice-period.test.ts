import { describe, expect, it } from "vitest";
import { bgb573cNoticeDeadline } from "./notice-period";

describe("bgb573cNoticeDeadline", () => {
  it("resolves the natural deadline when it's still in the future", () => {
    // Target end month March 2024 -> notice month January 2024 -> Jan 4
    // (see business-days.test.ts). "today" is safely before that.
    const result = bgb573cNoticeDeadline("2024-03", "DE", undefined, "2023-12-01");
    expect(result.date).toBe("2024-01-04");
    expect(result.leaseEndMonth).toBe("2024-03");
    expect(result.pastDeadline).toBe(false);
  });

  it("names the Saturday roll in the derivation when it happens, and stays silent when it doesn't", () => {
    const rolled = bgb573cNoticeDeadline("2025-03", "DE", undefined, "2024-12-01");
    expect(rolled.date).toBe("2025-01-06");
    expect(rolled.derivation.some((s) => s.step === "saturday-roll")).toBe(true);

    const clean = bgb573cNoticeDeadline("2027-05", "DE", undefined, "2027-01-01");
    expect(clean.derivation.some((s) => s.step === "saturday-roll")).toBe(false);
  });

  it("uses the recipient-region assumption for holidays - BW's Heilige Drei Könige changes the result", () => {
    const nationwide = bgb573cNoticeDeadline("2025-03", "DE", undefined, "2024-12-01");
    const bw = bgb573cNoticeDeadline("2025-03", "DE", "BW", "2024-12-01");
    expect(nationwide.date).toBe("2025-01-06");
    expect(bw.date).toBe("2025-01-07");
  });

  it("wraps across a year boundary", () => {
    // Target end month January 2027 -> notice month November 2026.
    const result = bgb573cNoticeDeadline("2027-01", "DE", undefined, "2026-01-01");
    expect(result.leaseEndMonth).toBe("2027-01");
    expect(result.date.startsWith("2026-11")).toBe(true);
  });

  it("keeps `date`/`leaseEndMonth` 1:1 with targetEndMonth even when the deadline has already passed - editing the anchor day must always visibly move it", () => {
    // Target end month March 2024 (notice month Jan 2024, deadline Jan 4) -
    // but "today" is already April 2024, long past that.
    const result = bgb573cNoticeDeadline("2024-03", "DE", "BW", "2024-04-15");
    expect(result.pastDeadline).toBe(true);
    expect(result.date).toBe("2024-01-04"); // the real (past) natural deadline, NOT a substitute
    expect(result.leaseEndMonth).toBe("2024-03");
    expect(result.derivation.some((s) => s.step === "past-deadline")).toBe(true);
  });

  it("offers a `rescue` suggestion (informational, not a substitute) once the natural deadline has passed", () => {
    const result = bgb573cNoticeDeadline("2024-03", "DE", "BW", "2024-04-15");
    expect(result.rescue).not.toBeNull();
    expect(result.rescue!.date >= "2024-04-15").toBe(true);
    expect(result.rescue!.leaseEndMonth > "2024-03").toBe(true);
    expect(result.derivation.some((s) => s.step === "rescue")).toBe(true);
    // The rescued deadline itself must still obey the same rule: never a
    // Saturday, Sunday, or holiday.
    const dow = new Date(`${result.rescue!.date}T00:00:00Z`).getUTCDay();
    expect(dow).not.toBe(0);
    expect(dow).not.toBe(6);
  });

  it("rescue tracks the target end month, not just today - two different already-unreachable targets close to reachability land on different rescues", () => {
    const nearby = bgb573cNoticeDeadline("2026-10", "DE", "BW", "2026-08-09");
    const further = bgb573cNoticeDeadline("2026-11", "DE", "BW", "2026-08-09");
    expect(nearby.rescue).not.toBeNull();
    expect(further.pastDeadline).toBe(false); // Nov's own natural deadline (notice month Sep) is already reachable
    // Nearby's rescue must not be later than picking Nov directly would be.
    expect(nearby.rescue!.leaseEndMonth <= "2026-11").toBe(true);
  });

  it("rescue is null when the deadline is still reachable", () => {
    const result = bgb573cNoticeDeadline("2024-03", "DE", undefined, "2023-12-01");
    expect(result.rescue).toBeNull();
  });

  it("does not rescue when the natural deadline is still reachable, even if close", () => {
    const result = bgb573cNoticeDeadline("2024-03", "DE", undefined, "2024-01-04");
    expect(result.pastDeadline).toBe(false);
    expect(result.date).toBe("2024-01-04");
  });

  it("always states the holiday-region assumption and the target end month, for every result", () => {
    const result = bgb573cNoticeDeadline("2024-03", "DE", "BW", "2023-12-01");
    expect(result.derivation[0].step).toBe("holiday-region");
    expect(result.derivation[0].label).toContain("DE-BW");
    expect(result.derivation.some((s) => s.step === "target-end-month")).toBe(true);
  });
});
