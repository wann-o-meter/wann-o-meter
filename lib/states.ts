// The abbreviation people actually type into a search box ("Brückentage NRW"),
// which is what has to appear in a year page's <title>/H1 (see
// lib/year-pages.ts). Only the five states with a genuinely common short form
// are listed: nobody searches for "Feiertage BAY" or "Schulferien SAC", so the
// rest deliberately have no entry and fall back to their full name below.
//
// ponytail: a sibling map keyed the same way as STATES, not an object-per-state
// remodelling of STATES itself - that would touch every consumer
// (data/*/generator.ts, lib/pages.ts, lib/countries.ts) to add one optional
// string. Still a single source of truth, which is all the spec asks for.
export const STATE_ABBREVIATIONS: Record<string, string> = {
  BW: "BW",
  MV: "MV",
  NW: "NRW",
  RP: "RLP",
  SH: "SH",
};

export const STATES: Record<string, string> = {
  BW: "Baden-Württemberg",
  BY: "Bayern",
  BE: "Berlin",
  BB: "Brandenburg",
  HB: "Bremen",
  HH: "Hamburg",
  HE: "Hessen",
  MV: "Mecklenburg-Vorpommern",
  NI: "Niedersachsen",
  NW: "Nordrhein-Westfalen",
  RP: "Rheinland-Pfalz",
  SL: "Saarland",
  SN: "Sachsen",
  ST: "Sachsen-Anhalt",
  SH: "Schleswig-Holstein",
  TH: "Thüringen",
};
