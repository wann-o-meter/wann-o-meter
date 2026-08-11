import type { Deadline } from "./deadline-plan";

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

export function facetsUsedBy(deadlines: Deadline[]): string[] {
  const used = new Set(deadlines.flatMap((d) => d.applies_if ?? []));
  return FACET_IDS.filter((id) => used.has(id));
}
