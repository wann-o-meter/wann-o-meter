import { BUNDESWEIT_SLUG, loadAllVorhaben } from "./vorhaben-data";
import { appliesTo } from "./facets";
import { durationLabel } from "./offset-label";
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

// The same Fristen the page counts in its overview paragraph.
function shown(variant: VorhabenVariant) {
  return variant.deadlines.filter((d) => appliesTo(d, []));
}

// "3 Monate" reads as "nach 3 Monaten" once a preposition takes the dative.
function dative(amount: string): string {
  return amount.endsWith("e") ? `${amount}n` : amount;
}

// The title says what the page answers: how many Fristen, and which way they
// run from the date the visitor gives.
function planTitle(
  v: VorhabenData,
  variant: VorhabenVariant,
  subject: string,
): string {
  const entries = shown(variant);
  const count = `${entries.length} ${entries.length === 1 ? "Frist" : "Fristen"}`;
  if (v.direction === "forwards") {
    const after = entries
      .map((d) => d.offset_days)
      .filter((o): o is number => o !== null && o > 0);
    if (after.length === 0) return `${subject}: ${count}`;
    return `${subject}: ${count}, die erste nach ${dative(durationLabel(Math.min(...after)))}`;
  }
  return `${subject}: ${count} rückwärts vom ${v.anchorDative ?? v.anchorLabel}`;
}

// What the page delivers, in numbers taken from the plan itself. A description
// that counts its own Fristen cannot promise a step the page does not have.
function planDescription(v: VorhabenData, variant: VorhabenVariant): string {
  const entries = shown(variant);
  const count = `${entries.length} ${entries.length === 1 ? "Frist" : "Fristen"}`;
  const offsets = entries
    .map((d) => d.offset_days)
    .filter((o): o is number => o !== null && o !== 0);
  const local = variant.localDeadlines.map((d) => d.label.split(" ")[0]);
  const where = local.length > 0 ? ` In ${variant.label} dazu: ${local.join(", ")}.` : "";

  if (v.direction === "forwards") {
    const after = offsets.filter((o) => o > 0);
    const first =
      after.length > 0 ? `, die erste nach ${dative(durationLabel(Math.min(...after)))}` : "";
    // Only the first letter drops its capital, the noun after it keeps its own.
    const subject = v.titleSubject
      ? v.titleSubject[0].toLowerCase() + v.titleSubject.slice(1)
      : `nach ${v.anchorName}`;
    return `${count} ${subject}${first}. Termin eingeben und jede Frist mit Datum, Quelle und Kalender-Export bekommen.${where}`;
  }
  const before = offsets.filter((o) => o < 0).map((o) => -o);
  const start =
    before.length > 0 ? `, die früheste ${durationLabel(Math.max(...before))} vorher` : "";
  return `${count} rückwärts vom ${v.anchorDative ?? v.anchorLabel}${start}. Mit Quelle, Feiertagen deines Bundeslands und Kalender-Export.${where}`;
}

export function vorhabenRoutes(): VorhabenRoute[] {
  return loadAllVorhaben().flatMap((v) => {
    const base: VorhabenRoute = {
      path: v.slug,
      v,
      variant: defaultVariant(v),
      title: planTitle(v, defaultVariant(v), v.titleSubject ?? v.label),
      heading: planTitle(v, defaultVariant(v), v.titleSubject ?? v.label),
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
