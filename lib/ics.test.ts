import { describe, expect, it } from "vitest";
import { generateIcs } from "./ics";

describe("generateIcs", () => {
  it("produces a valid VCALENDAR with one VEVENT", () => {
    const out = generateIcs(
      [{ uid: "abc-1", from: "2027-05-07", to: "2027-05-09", title: "Pfingstbruecke" }],
      "Testkalender",
    );
    expect(out.startsWith("BEGIN:VCALENDAR\r\n")).toBe(true);
    expect(out.endsWith("END:VCALENDAR\r\n")).toBe(true);
    expect(out).toContain("DTSTART;VALUE=DATE:20270507");
    // DTEND is exclusive -> one day after the last full day
    expect(out).toContain("DTEND;VALUE=DATE:20270510");
    expect(out).toContain("SUMMARY:Pfingstbruecke");
    expect(out).toContain("X-WR-CALNAME:Testkalender");
  });

  it("escapes commas, semicolons and backslashes in text", () => {
    const out = generateIcs(
      [{ uid: "x", from: "2027-01-01", to: "2027-01-01", title: "A; B, C\\D" }],
      "K",
    );
    expect(out).toContain("SUMMARY:A\\; B\\, C\\\\D");
  });

  it("folds lines over 74 characters with CRLF + space continuation", () => {
    const longText = "x".repeat(120);
    const out = generateIcs(
      [{ uid: "y", from: "2027-01-01", to: "2027-01-01", title: "kurz", description: longText }],
      "K",
    );
    expect(out).toContain("\r\n ");
    const descriptionLine = out.split("\r\n").find((l) => l.startsWith("DESCRIPTION:"));
    expect(descriptionLine!.length).toBeLessThanOrEqual(74);
  });

  it("produces no VEVENT for an empty list", () => {
    const out = generateIcs([], "Leer");
    expect(out).not.toContain("BEGIN:VEVENT");
  });
});
