// Regenerates public/gemeinden.json from Wikidata. Run by hand when the list
// should be refreshed: `bun scripts/gemeinden.mjs`.
//
// Selected by Gemeindeschlüssel (P439) rather than by class and P131 chain:
// the chain version times the endpoint out, and the first two digits of the
// key already name the Bundesland. Every field comes from the query result.
import { writeFileSync } from "node:fs";

const ENDPOINT = "https://query.wikidata.org/sparql";
const UA = "wannometer-gemeinden/1.0 (https://wannometer.de)";

const QUERY = `
SELECT ?gemLabel ?ags (GROUP_CONCAT(DISTINCT ?plz; separator="|") AS ?plzList) WHERE {
  ?gem wdt:P439 ?ags .
  ?gem rdfs:label ?gemLabel .
  FILTER(LANG(?gemLabel) = "de")
  OPTIONAL { ?gem wdt:P281 ?plz . }
}
GROUP BY ?gem ?gemLabel ?ags`;

// First two digits of the Gemeindeschlüssel, the official numbering.
const STATE_OF_AGS = {
  "01": "SH",
  "02": "HH",
  "03": "NI",
  "04": "HB",
  "05": "NW",
  "06": "HE",
  "07": "RP",
  "08": "BW",
  "09": "BY",
  10: "SL",
  11: "BE",
  12: "BB",
  13: "MV",
  14: "SN",
  15: "ST",
  16: "TH",
};

// P281 comes as single codes and as ranges like "71634-71642". The lowest code
// is the one a Gemeinde is listed under.
function firstPlz(raw) {
  const codes = (raw ?? "").match(/\d{5}/g);
  return codes ? codes.sort()[0] : null;
}

// The public endpoint answers this in about 45 seconds and hands out a 504
// whenever it is busy, so a few attempts are normal.
async function ask(attempt = 1) {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: {
      "User-Agent": UA,
      Accept: "application/sparql-results+json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ query: QUERY }),
  });
  if (res.ok) return (await res.json()).results.bindings;
  if (attempt >= 5) throw new Error(`HTTP ${res.status} after ${attempt} tries`);
  console.error(`HTTP ${res.status}, retrying (${attempt})`);
  await new Promise((r) => setTimeout(r, attempt * 10000));
  return ask(attempt + 1);
}

const rows = await ask();

const seen = new Set();
const out = [];
for (const row of rows) {
  const name = row.gemLabel?.value;
  const state = STATE_OF_AGS[row.ags?.value?.slice(0, 2)];
  const plz = firstPlz(row.plzList?.value);
  // An entity without a German label, without a usable key or without a PLZ is
  // not something anyone can search for.
  if (!name || /^Q\d+$/.test(name) || !state || !plz) continue;
  const key = `${name}|${plz}`;
  if (seen.has(key)) continue;
  seen.add(key);
  out.push({ name, plz, state });
}

out.sort(
  (a, b) => a.name.localeCompare(b.name, "de") || a.plz.localeCompare(b.plz),
);
writeFileSync("public/gemeinden.json", JSON.stringify(out));
console.error(`${rows.length} rows, wrote ${out.length} Gemeinden`);
