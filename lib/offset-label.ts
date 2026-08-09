// Wording for a deadline that has no concrete date yet: what the statically
// rendered page (and any crawler) sees before the planner island hydrates a
// real calendar date over it. Browser-safe, no node imports.
import type { Deadline } from "./deadline-plan";

// A rule computes its date from the anchor month, so the entry's offset_days
// is only a sorting approximation - saying "3 Monate vorher" would present
// that guess as the deadline. Name the rule instead.
const RULE_LABELS: Record<string, string> = {
  "bgb-573c-notice": "Frist nach § 573c BGB, abhängig vom Umzugsmonat",
};

function amount(days: number): string {
  if (days >= 60) return `${Math.round(days / 30)} Monate`;
  if (days >= 14) return `${Math.round(days / 7)} Wochen`;
  return days === 1 ? "1 Tag" : `${days} Tage`;
}

export function offsetLabel(d: Deadline, anchorLabel: string): string {
  if (d.offset_rule) return RULE_LABELS[d.offset_rule] ?? "Frist nach Regel berechnet";
  if (d.offset_days === null) return "Frist noch nicht recherchiert";
  if (d.offset_days === 0) return `am ${anchorLabel}`;
  return d.offset_days < 0
    ? `${amount(-d.offset_days)} vorher`
    : `${amount(d.offset_days)} danach`;
}

export function sourceLabel(d: Deadline): string {
  if (d.source_url) return d.source_label ?? "Quelle";
  if (d.no_source_needed) return "Keine gesetzliche Frist";
  return "Quelle fehlt";
}

// Unknown offsets sort last: they are the ones nobody has researched yet, not
// the ones that happen last.
export function byOffset(a: Deadline, b: Deadline): number {
  if (a.offset_days === null) return b.offset_days === null ? 0 : 1;
  if (b.offset_days === null) return -1;
  return a.offset_days - b.offset_days;
}
