import { BUNDESWEIT_SLUG, loadAllVorhaben } from "./vorhaben-data";
import { appliesTo } from "./facets";
import type { VorhabenData, VorhabenVariant } from "./vorhaben-data";

interface VorhabenRoute {
  path: string;
  v: VorhabenData;
  variant: VorhabenVariant;
  title: string;
  description: string;
}

function defaultVariant(v: VorhabenData): VorhabenVariant {
  return v.variants.find((x) => x.slug === v.defaultVariant) ?? v.variants[0];
}

// The same Fristen the page counts in its overview paragraph.
function shown(variant: VorhabenVariant) {
  return variant.deadlines.filter((d) => appliesTo(d, []));
}

function days(n: number): string {
  return n === 1 ? "1 Tag" : `${n} Tagen`;
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
    return `${subject}: ${count}, die erste nach ${days(Math.min(...after))}`;
  }
  return `${subject}: ${count} rückwärts vom ${v.anchorDative ?? v.anchorLabel}`;
}

export function vorhabenRoutes(): VorhabenRoute[] {
  return loadAllVorhaben().flatMap((v) => {
    const base: VorhabenRoute = {
      path: v.slug,
      v,
      variant: defaultVariant(v),
      title: planTitle(v, defaultVariant(v), v.titleSubject ?? v.label),
      description: v.description,
    };
    const local = v.variants.filter((x) => x.slug !== BUNDESWEIT_SLUG);
    if (local.length === 0) return [base];
    return [
      base,
      ...local.map((variant) => ({
        path: `${v.slug}/${variant.slug}`,
        v,
        variant,
        title: planTitle(v, variant, `${v.label} in ${variant.label}`),
        description: `${v.label} in ${variant.label}: alle Fristen rückwärts vom ${v.anchorLabel} geplant, mit Quelle - inklusive der örtlichen Schritte.`,
      })),
    ];
  });
}
