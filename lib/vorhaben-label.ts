// "Dein Umzug", where a Vorhaben is something a person has. Not every one is:
// a Todesfall belongs to nobody, so its yaml leaves possessive out and every
// surface keeps the plain label. Pure, so the islands can import it.
export function possessiveLabel(v: {
  label: string;
  possessive?: string;
}): string {
  return v.possessive ? `${v.possessive} ${v.label}` : v.label;
}
