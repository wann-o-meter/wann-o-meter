import type { Deadline } from "./deadline-plan";

// Optional circumstances of a Vorhaben ("ich habe ein Auto", "ich habe einen
// Hund"). A deadline tagged with applies_if only shows once one of its facets
// is active - untagged deadlines always show.
//
// This map is the whole catalog: the YAML schema validates applies_if against
// its keys, and the planner only offers a chip for a facet that some deadline
// in the selected variant actually uses, so tagging a new entry is a one-line
// data change with no UI work.
export const FACET_LABELS: Record<string, string> = {
  haustier_hund: "Hund",
  haustier_katze: "Katze",
  auto: "Auto",
  gewerbe: "Gewerbe",
  kinder: "Kinder",
  studium: "Studium",
  arbeitssuchend: "Arbeitssuchend",
  wohngeld: "Wohngeld",
  jagdschein: "Jagdschein",
};

export const FACET_IDS = Object.keys(FACET_LABELS) as [string, ...string[]];

export function facetLabel(id: string): string {
  return FACET_LABELS[id] ?? id;
}

export function appliesTo(deadline: Deadline, activeFacets: string[]): boolean {
  const required = deadline.applies_if;
  if (!required || required.length === 0) return true;
  return required.some((f) => activeFacets.includes(f));
}

// Facets worth offering as a chip: only those some deadline in this list uses.
export function facetsUsedBy(deadlines: Deadline[]): string[] {
  const used = new Set(deadlines.flatMap((d) => d.applies_if ?? []));
  return FACET_IDS.filter((id) => used.has(id));
}
