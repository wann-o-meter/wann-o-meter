// One list of routes for both the HTML page and the .md endpoint, so the two
// can never enumerate different pages. Server-only (loads vorhaben-data).
import { loadAllVorhaben } from "./vorhaben-data";
import type { VorhabenData, VorhabenVariant } from "./vorhaben-data";

export interface VorhabenRoute {
  path: string; // "umzug" or "umzug/rottenburg"
  v: VorhabenData;
  variant: VorhabenVariant;
  title: string;
  description: string;
}

function defaultVariant(v: VorhabenData): VorhabenVariant {
  return v.variants.find((x) => x.slug === v.defaultVariant) ?? v.variants[0];
}

export function vorhabenRoutes(): VorhabenRoute[] {
  return loadAllVorhaben().flatMap((v) => {
    const base: VorhabenRoute = {
      path: v.slug,
      v,
      variant: defaultVariant(v),
      title: v.title,
      description: v.description,
    };
    // A single synthetic bundesweit variant is not a place - no /geburt/bundesweit/.
    if (v.variants.length < 2) return [base];
    return [
      base,
      ...v.variants.map((variant) => ({
        path: `${v.slug}/${variant.slug}`,
        v,
        variant,
        title: `${v.label} in ${variant.label}: wann muss ich anfangen?`,
        description: `${v.label} in ${variant.label}: alle Fristen rückwärts vom ${v.anchorLabel} geplant, mit Quelle - inklusive der örtlichen Schritte.`,
      })),
    ];
  });
}
