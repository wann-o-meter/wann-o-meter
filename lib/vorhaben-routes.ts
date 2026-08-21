import { BUNDESWEIT_SLUG, loadAllVorhaben } from "./vorhaben-data";
import { appliesTo } from "./facets";
import { byOffset, durationLabel, offsetLabel } from "./offset-label";
import type { Deadline } from "./deadline-schema";
import type { VorhabenData, VorhabenVariant } from "./vorhaben-data";

interface VorhabenRoute {
  path: string;
  v: VorhabenData;
  variant: VorhabenVariant;
  title: string;
  // What the page says as its H1. The same as the title unless the Vorhaben
  // gives its place pages a heading of their own.
  heading: string;
  description: string;
  noindex: boolean;
}

// A place page earns its index entry with at least one fact that is true only
// there: an own source or the office that handles it. Without one it is the
// bundesweit plan with a place name swapped in, and that is what a crawler
// counts as a duplicate. It keeps its links: noindex, follow.
export function shouldIndex(variant: VorhabenVariant): boolean {
  return variant.localDeadlines.some((d) => d.source_url || d.authority);
}

// The same rule, as the paths the sitemap has to leave out.
export function noindexPaths(): string[] {
  return vorhabenRoutes()
    .filter((r) => r.noindex)
    .map((r) => `/${r.path}/`);
}

function defaultVariant(v: VorhabenData): VorhabenVariant {
  return v.variants.find((x) => x.slug === v.defaultVariant) ?? v.variants[0];
}

// The same entries in the same order the page shows them.
function shown(variant: VorhabenVariant): Deadline[] {
  return variant.deadlines.filter((d) => appliesTo(d, [])).sort(byOffset);
}

// Every Frist that names its Paragraf. What the title is allowed to promise:
// a soft step has no statute behind it and must not be counted as one.
function fristen(entries: Deadline[]) {
  return entries.filter((d) => d.kind !== "soft" && d.source_label);
}

// The Fristen a description leads with: the earliest one before the anchor and
// the earliest one after it, so a plan that runs both ways shows both.
function highlights(entries: Deadline[], count: number): Deadline[] {
  const stat = fristen(entries);
  const picked = [
    stat.find((d) => d.direction === "before"),
    stat.find((d) => d.direction === "after"),
  ].filter((d) => d !== undefined);
  return [...new Set([...picked, ...stat])].slice(0, count);
}

// The title says what the page answers, not how long its list is. A count in
// the title counts every soft step as a Frist, which is what the page is not
// allowed to promise. Without a single Paragraf the page says so.
function planTitle(
  v: VorhabenData,
  variant: VorhabenVariant,
  subject: string,
): string {
  return fristen(shown(variant)).length > 0
    ? `${subject}: alle Fristen mit Paragraf`
    : (v.titleFallback ?? `${subject}: Vorlaufzeiten für ${v.teaser}`);
}

// How much time the plan asks for up front. A Frist that carries its own label
// has no fixed offset, so the lead time keeps the hedge that label exists for.
function leadTime(first: Deadline | undefined, anchorLabel: string): string {
  if (!first) return "";
  const say =
    first.offset_label && first.offset_days !== null
      ? `etwa ${durationLabel(Math.abs(first.offset_days))} ${first.offset_days < 0 ? "vorher" : "danach"}`
      : offsetLabel(first, anchorLabel);
  return ` Früheste Aufgabe: ${say}.`;
}

// What the page delivers, named from the plan itself. A description that reads
// its own Fristen cannot promise a Paragraf the page does not have.
function planDescription(v: VorhabenData, variant: VorhabenVariant): string {
  const entries = shown(variant);
  const lead = leadTime(entries[0], v.anchorLabel);
  // A place page names what only it has. That is what it is indexed for.
  const local = variant.localDeadlines.map((d) => d.label.split(" ")[0]);
  const open = `${v.anchorLabel} eingeben, jede Aufgabe als konkretes Datum bekommen`;
  // What a result page shows is about 160 characters, so the Paragrafen give up
  // their task names before they give up their place. A label is never cut in
  // half to make one more fit, and the sentence about Feiertage only fills the
  // space no Paragraf took.
  const options: [number, boolean][] = [[2, true], [1, true], [2, false], [0, false]];
  for (const [count, withLabel] of options) {
    const cited = highlights(entries, count)
      .map((d) => (withLabel ? `${d.label} (${d.source_label})` : d.source_label))
      .join(", ");
    const tail = local.length > 0
      ? ` In ${variant.label} dazu: ${local.join(", ")}.`
      : cited
        ? ""
        : " Mit Feiertagen deines Bundeslands.";
    const text = `${open}${cited ? `: ${cited}` : ""}.${lead}${tail}`;
    if (text.length <= 160 || count === 0) return text;
  }
  return "";
}

// "Umzug planen", but "Nach der Geburt" where planning is not the point.
function subject(v: VorhabenData): string {
  return v.titleSubject ?? `${v.label} planen`;
}

export function vorhabenRoutes(): VorhabenRoute[] {
  return loadAllVorhaben().flatMap((v) => {
    const base: VorhabenRoute = {
      path: v.slug,
      v,
      variant: defaultVariant(v),
      title: planTitle(v, defaultVariant(v), subject(v)),
      heading: planTitle(v, defaultVariant(v), subject(v)),
      description: planDescription(v, defaultVariant(v)),
      noindex: false,
    };
    const local = v.variants.filter((x) => x.slug !== BUNDESWEIT_SLUG);
    if (local.length === 0) return [base];
    return [
      base,
      ...local.map((variant) => ({
        path: `${v.slug}/${variant.slug}`,
        v,
        variant,
        title:
          v.placeTitle?.replace("{ort}", variant.label) ??
          planTitle(v, variant, `${v.label} in ${variant.label}`),
        heading:
          v.placeHeading?.replace("{ort}", variant.label) ??
          planTitle(v, variant, `${v.label} in ${variant.label}`),
        description: planDescription(v, variant),
        noindex: !shouldIndex(variant),
      })),
    ];
  });
}
