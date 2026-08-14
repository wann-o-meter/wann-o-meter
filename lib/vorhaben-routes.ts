import { BUNDESWEIT_SLUG, loadAllVorhaben } from "./vorhaben-data";
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

export function vorhabenRoutes(): VorhabenRoute[] {
  return loadAllVorhaben().flatMap((v) => {
    const base: VorhabenRoute = {
      path: v.slug,
      v,
      variant: defaultVariant(v),
      title: v.title,
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
        title: `${v.label} in ${variant.label}: wann muss ich anfangen?`,
        description: `${v.label} in ${variant.label}: alle Fristen rückwärts vom ${v.anchorLabel} geplant, mit Quelle - inklusive der örtlichen Schritte.`,
      })),
    ];
  });
}
