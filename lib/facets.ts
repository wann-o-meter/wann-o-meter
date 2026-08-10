import type { Deadline } from "./deadline-plan";

// Optional circumstances of a Vorhaben ("ich habe ein Auto", "ich habe einen
// Hund"). A deadline tagged with applies_if only shows once one of its facets
// is active - untagged deadlines always show.
//
// This map is the whole catalog: the YAML schema validates applies_if against
// its keys, and the planner only offers a chip for a facet that some deadline
// in the selected variant actually uses, so tagging a new entry is a one-line
// data change with no UI work.
// Full sentences: a bare "Auto" next to a checkbox reads as a broken filter,
// not as something the reader is being asked about themselves.
export const FACET_LABELS: Record<string, string> = {
  haustier_hund: "Ich habe einen Hund",
  haustier_katze: "Ich habe eine Katze",
  auto: "Ich habe ein Auto, das ich ummelden muss",
  gewerbe: "Ich habe ein Gewerbe angemeldet",
  kinder: "Kinder ziehen mit um",
  studium: "Ich studiere",
  arbeitssuchend: "Ich bin arbeitssuchend gemeldet",
  wohngeld: "Ich beziehe Wohngeld",
  jagdschein: "Ich habe einen Jagdschein",
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
