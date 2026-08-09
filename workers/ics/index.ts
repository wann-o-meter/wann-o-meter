// webcal://wannometer.de/ics/umzug?date=2026-12-26&variant=rottenburg
//
// A plan is a pure function of the four values above, so nothing is stored
// and no personal data reaches the edge. DeadlinePlanner.vue builds the same
// ICS client-side, but a Blob has no URL to subscribe to. See README.md.
import { appliesTo, FACET_LABELS } from "../../lib/facets";
import { computeSchedule } from "../../lib/deadline-plan";
import type { Deadline } from "../../lib/deadline-plan";
import { generateIcs } from "../../lib/ics";
import type { IcsEvent } from "../../lib/ics";

const COUNTRY_CODE = "DE"; // hardcoded as in usePlannerSchedule.ts, a German-market product end to end
const ANCHOR_ID = "__anchor";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const SLUG = /^[a-z0-9-]{1,64}$/; // both segments go into an origin fetch path, so this is a trust boundary

export interface PlanPayload {
  slug: string;
  vorhaben: string;
  anchorLabel: string;
  variant: { slug: string; label: string; regionCode?: string; deadlines: Deadline[] };
}

export type LoadPlan = (vorhaben: string, variant: string) => Promise<PlanPayload | null>;

function badRequest(message: string): Response {
  return new Response(`${message}\n`, {
    status: 400,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

// The year bound is a cost guard: date-holidays computes a whole year per call.
function isSaneDate(iso: string): boolean {
  if (!ISO_DAY.test(iso)) return false;
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== iso) return false;
  const year = Number(iso.slice(0, 4));
  return year >= 1900 && year <= 2200;
}

export async function handleIcsRequest(url: URL, loadPlan: LoadPlan): Promise<Response> {
  // Trailing .ics optional: some clients only subscribe to a file-looking URL.
  const vorhaben = url.pathname.replace(/^\/ics\//, "").replace(/\.ics$/, "");
  const variant = url.searchParams.get("variant") ?? "";
  const date = url.searchParams.get("date") ?? "";

  if (!SLUG.test(vorhaben)) return badRequest("Unbekanntes Vorhaben.");
  if (!SLUG.test(variant)) return badRequest("Parameter variant fehlt oder ist ungültig.");
  if (!isSaneDate(date)) return badRequest("Parameter date fehlt oder ist kein Datum (YYYY-MM-DD).");

  const plan = await loadPlan(vorhaben, variant);
  if (!plan) return new Response("Plan nicht gefunden.\n", { status: 404 });

  const facets = (url.searchParams.get("facets") ?? "")
    .split(",")
    .filter((f) => f in FACET_LABELS);

  // Anchor day plus the deadlines that apply, the same list the planner builds.
  const deadlines: Deadline[] = [
    { id: ANCHOR_ID, label: plan.anchorLabel, offset_days: 0, source_url: null },
    ...plan.variant.deadlines.filter((d) => appliesTo(d, facets)),
  ];
  const schedule = computeSchedule(date, deadlines, COUNTRY_CODE, plan.variant.regionCode);

  const events: IcsEvent[] = schedule
    .filter((e) => e.date !== null)
    .map((e) => ({
      // Same UID scheme as the client-side export, so a corrected deadline
      // moves the subscriber's existing event instead of adding a second one.
      uid: `${e.id}-${date}@wannometer.de`,
      from: e.date!,
      to: e.date!,
      title: e.label,
      description: e.note,
      url: e.source_url ?? undefined,
    }));

  const ics = generateIcs(events, `${plan.vorhaben} - ${plan.variant.label}`);
  return new Response(ics, {
    headers: {
      "Content-Type": "text/calendar; charset=utf-8",
      // Spares the origin only. Clients refetch on their own schedule anyway,
      // Google often just every 8 to 24 hours.
      "Cache-Control": "public, max-age=3600",
    },
  });
}

// Spelled out rather than read off the request, because a same-origin
// subrequest loops back into the worker under `wrangler dev`.
const DEFAULT_PLAN_ORIGIN = "https://wannometer.de";

export default {
  async fetch(request: Request, env: { PLAN_ORIGIN?: string }): Promise<Response> {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed\n", { status: 405, headers: { Allow: "GET, HEAD" } });
    }
    const origin = env?.PLAN_ORIGIN ?? DEFAULT_PLAN_ORIGIN;
    return handleIcsRequest(new URL(request.url), async (vorhaben, variant) => {
      const res = await fetch(`${origin}/api/v1/vorhaben/${vorhaben}/${variant}.json`);
      return res.ok ? ((await res.json()) as PlanPayload) : null;
    });
  },
};
