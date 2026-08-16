import type { Deadline } from "./deadline-plan";

function amount(days: number): string {
  if (days >= 60) return `${Math.round(days / 30)} Monate`;
  if (days >= 14) return `${Math.round(days / 7)} Wochen`;
  return days === 1 ? "1 Tag" : `${days} Tage`;
}

export function offsetLabel(d: Deadline, anchorLabel: string): string {
  // A Frist whose shape no offset describes says so in its yaml.
  if (d.offset_label) return d.offset_label;
  if (d.offset_days === null) return "Frist noch nicht recherchiert";
  if (d.offset_days === 0) return anchorLabel;
  return d.offset_days < 0
    ? `${amount(-d.offset_days)} vorher`
    : `${amount(d.offset_days)} danach`;
}

export function sourceLabel(d: Deadline): string {
  if (d.source_url) return d.source_label ?? "Quelle";
  if (d.no_source_needed) return "Keine gesetzliche Frist";
  return "Erfahrungswert";
}

export function byOffset(a: Deadline, b: Deadline): number {
  if (a.offset_days === null) return b.offset_days === null ? 0 : 1;
  if (b.offset_days === null) return -1;
  return a.offset_days - b.offset_days;
}
