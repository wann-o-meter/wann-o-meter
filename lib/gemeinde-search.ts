// Client side only: the list is fetched, never imported, so the 11k entries
// stay out of the page bundle.
export interface Gemeinde {
  name: string;
  // Lowest PLZ of the Gemeinde. Over 450 names exist more than once, this is
  // what tells them apart.
  plz: string;
  state: string;
}

let cache: Gemeinde[] | null = null;

export async function loadGemeinden(): Promise<Gemeinde[]> {
  if (cache) return cache;
  try {
    cache = (await (await fetch("/gemeinden.json")).json()) as Gemeinde[];
  } catch {
    cache = [];
  }
  return cache;
}

// "Muenchen" and "munchen" should both find München.
export function fold(s: string): string {
  return s
    .toLowerCase()
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

// Tiers, best first: the whole name, the start of the name, the start of a word
// inside it, anywhere. Within a tier the shorter name wins, which is the same
// as "more of the name is the query".
function rank(name: string, q: string): number {
  const n = fold(name);
  if (n === q) return 0;
  if (n.startsWith(q)) return 1;
  const at = n.indexOf(q);
  if (at < 0) return 4;
  return /[\s(-]/.test(n[at - 1] ?? "") ? 2 : 3;
}

// ponytail: a linear scan over 11k names per keystroke, fast enough by far.
// Build an index only if the list ever grows past a country.
export function searchGemeinden(
  list: Gemeinde[],
  query: string,
  limit: number,
): Gemeinde[] {
  const q = fold(query.trim());
  if (q.length === 0) return [];
  const scored: { g: Gemeinde; tier: number }[] = [];
  for (const g of list) {
    const tier = g.plz.startsWith(q) ? 1 : rank(g.name, q);
    if (tier < 4) scored.push({ g, tier });
  }
  return scored
    .sort(
      (a, b) =>
        a.tier - b.tier ||
        a.g.name.length - b.g.name.length ||
        a.g.name.localeCompare(b.g.name, "de"),
    )
    .slice(0, limit)
    .map((s) => s.g);
}
