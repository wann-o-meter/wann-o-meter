import { describe, expect, it } from "vitest";
import { handleIcsRequest } from "./index";
import type { PlanPayload } from "./index";

const plan: PlanPayload = {
  slug: "umzug",
  vorhaben: "Umzug innerhalb Deutschlands",
  anchorLabel: "Umzugstag",
  variant: {
    slug: "rottenburg",
    label: "Rottenburg am Neckar",
    regionCode: "BW",
    deadlines: [
      { id: "ummeldung", label: "Ummeldung", offset_days: 14, source_url: null },
      { id: "unbekannt", label: "Noch offen", offset_days: null, source_url: null },
      {
        id: "kfz",
        label: "Kfz ummelden",
        offset_days: 7,
        source_url: null,
        applies_if: ["auto"],
      },
    ],
  },
};

const loadPlan = async (vorhaben: string, variant: string) =>
  vorhaben === "umzug" && variant === "rottenburg" ? plan : null;

function req(path: string) {
  return handleIcsRequest(new URL(`https://wannometer.de${path}`), loadPlan);
}

describe("handleIcsRequest", () => {
  it("renders the plan as a calendar", async () => {
    const res = await req("/ics/umzug?date=2026-12-26&variant=rottenburg");
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/calendar; charset=utf-8");
    const body = await res.text();
    expect(body).toContain("X-WR-CALNAME:Umzug innerhalb Deutschlands - Rottenburg am Neckar");
    expect(body).toContain("SUMMARY:Umzugstag");
    expect(body).toContain("DTSTART;VALUE=DATE:20261226"); // anchor, offset 0
    expect(body).toContain("DTSTART;VALUE=DATE:20270109"); // Ummeldung, +14
    expect(body).toContain("UID:ummeldung-2026-12-26@wannometer.de");
  });

  it("omits deadlines with no researched offset", async () => {
    const body = await (await req("/ics/umzug?date=2026-12-26&variant=rottenburg")).text();
    expect(body).not.toContain("Noch offen");
  });

  it("includes a facet deadline only when the facet is active", async () => {
    const without = await (await req("/ics/umzug?date=2026-12-26&variant=rottenburg")).text();
    expect(without).not.toContain("Kfz ummelden");
    const with_ = await (
      await req("/ics/umzug?date=2026-12-26&variant=rottenburg&facets=auto")
    ).text();
    expect(with_).toContain("Kfz ummelden");
  });

  it("accepts a trailing .ics for clients that want a file-looking URL", async () => {
    expect((await req("/ics/umzug.ics?date=2026-12-26&variant=rottenburg")).status).toBe(200);
  });

  it("rejects a missing or malformed date", async () => {
    expect((await req("/ics/umzug?variant=rottenburg")).status).toBe(400);
    expect((await req("/ics/umzug?date=26.12.2026&variant=rottenburg")).status).toBe(400);
    expect((await req("/ics/umzug?date=2026-02-30&variant=rottenburg")).status).toBe(400);
    expect((await req("/ics/umzug?date=9999-01-01&variant=rottenburg")).status).toBe(400);
  });

  it("rejects path traversal in the slug segments", async () => {
    expect((await req("/ics/..%2F..%2Fetc?date=2026-12-26&variant=rottenburg")).status).toBe(400);
    expect((await req("/ics/umzug?date=2026-12-26&variant=..%2Fsecret")).status).toBe(400);
  });

  it("404s an unknown plan", async () => {
    expect((await req("/ics/umzug?date=2026-12-26&variant=gibtsnicht")).status).toBe(404);
  });
});
