// Regenerates lib/statute-quotes.ts, the statute wording the Frist pages print.
//
// A Frist page has to say what the Frist is. The shortest true way to say it is
// the statute itself, so the yaml names the Absätze and this script fetches the
// wording. Nobody writes a paraphrase, so nobody has to review one.
//
// Source is the official XML of gesetze-im-internet.de, not the HTML: it is a
// stable format with one <norm> per Paragraf and one <P> per Absatz. Gesetze
// carry no copyright (§ 5 Abs. 1 UrhG), so the wording can be reproduced.
//
// Deliberately NOT part of `bun run build`. A build must not depend on a
// government website being up, and a statute that changed should show up as a
// diff somebody looks at, not as a silent edit on a deploy.
//
//   bun run gesetze
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { load } from "js-yaml";

const FRISTEN_DIR = "data/fristen";
const OUT = "lib/statute-quotes.ts";
const GII = "https://www.gesetze-im-internet.de";

// https://www.gesetze-im-internet.de/bgb/__573c.html -> { law: "bgb", enbez: "§ 573c" }
function locate(sourceUrl) {
  const m = new URL(sourceUrl).pathname.match(/^\/([^/]+)\/__([^.]+)\.html$/);
  return m ? { law: m[1], enbez: `§ ${m[2]}` } : null;
}

const lawCache = new Map();
function lawXml(law) {
  if (!lawCache.has(law)) {
    const dir = mkdtempSync(join(tmpdir(), "gii-"));
    const zip = join(dir, "law.zip");
    execFileSync("curl", ["-sSf", "--max-time", "120", `${GII}/${law}/xml.zip`, "-o", zip]);
    execFileSync("unzip", ["-oq", zip, "-d", dir]);
    const xml = readdirSync(dir).find((f) => f.endsWith(".xml"));
    lawCache.set(law, readFileSync(join(dir, xml), "utf-8"));
  }
  return lawCache.get(law);
}

const unescape = (s) =>
  s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(Number(d)))
    .replace(/&amp;/g, "&");

// One entry per Absatz, in the order the statute has them. A <DL> list belongs
// to the Absatz above it, and a <P> without an "(n)" marker continues the last
// one, which is how the XML writes Sätze that carry their own number.
function absaetze(normXml) {
  const body = normXml.match(/<text[^>]*>\s*<Content>([\s\S]*?)<\/Content>/);
  if (!body) return [];
  const flat = unescape(
    body[1]
      // Satz numbering, which the site prints as a superscript. Not part of the
      // wording, so it becomes an invisible boundary rather than text.
      .replace(/<SUP class="Rec">\d+<\/SUP>/g, SATZ_MARK)
      .replace(/<\/(P|DD)>/g, "\n")
      .replace(/<\/DT>/g, " ")
      .replace(/<[^>]+>/g, ""),
  );
  const out = [];
  for (const raw of flat.split("\n")) {
    const line = raw.replace(/\s+/g, " ").trim();
    if (!line) continue;
    const start = line.match(/^\((\d+[a-z]?)\)\s*/);
    if (start)
      // The first Satz marker sits right behind the "(1) " prefix and would
      // otherwise split that prefix off as a Satz of its own.
      out.push({ n: start[1], text: line.replace(/^(\(\d+[a-z]?\)\s*)\u0001/, "$1") });
    else if (out.length) out[out.length - 1].text += ` ${line}`;
  }
  return out;
}

// Satz boundaries. Where the XML numbers Sätze the official markers decide it.
// Only the EStG does that among the Gesetze in use here, so everywhere else a
// Satz ends at a period after a lowercase letter followed by a capital, a § or
// a quote. A digit never starts a Satz, which keeps "Abs. 2", "Nr. 2" and
// "am 15. eines Monats" in one piece.
const SATZ_MARK = "\u0001";
const SATZ_GRENZE = /(?<=[a-zäöüß]\.)\s+(?=[A-ZÄÖÜ§„"])/;

function saetze(text) {
  const parts = text.includes(SATZ_MARK)
    ? text.split(SATZ_MARK)
    : text.split(SATZ_GRENZE);
  return parts.map((x) => x.trim()).filter(Boolean);
}

// Every Paragraf the law actually contains. A cross-reference is only turned
// into a link when it resolves against this, so the page cannot invent a URL.
const enbezCache = new Map();
function enbezOf(law) {
  if (!enbezCache.has(law)) {
    enbezCache.set(
      law,
      new Set([...lawXml(law).matchAll(/<enbez>(§ [^<]+)<\/enbez>/g)].map((m) => m[1])),
    );
  }
  return enbezCache.get(law);
}

// A bare "§ 12" inside a law means that law. "§ 15 des Aktiengesetzes" does
// not, and neither does "§§ 3 und 4 ...", so both are left as plain text: a
// link to the wrong Gesetz is worse than no link.
const PARAGRAF = /(?<!§)§\s*(\d+[a-z]?)(?!\d)/g;
const ZAEHLER = "(?:\\s*(?:Abs(?:atz|\\.)|S(?:atz|\\.)|Nr\\.?|Nummer)\\s*\\d+[a-z]?)*";
function namesAnotherLaw(tail, jurabk) {
  if (new RegExp(`^${ZAEHLER}\\s+(?:des|der)\\s`, "i").test(tail)) return true;
  // The lookahead matters: without it "§ 19 Satz 1" reads "Satz" as the name of
  // another Gesetz, because a counter word is capitalised too.
  const abbr = tail.match(
    new RegExp(`^${ZAEHLER}\\s+(?!Abs|Satz|Nr|Nummer)([A-ZÄÖÜ][A-ZÄÖÜa-z]*)`),
  );
  return !!abbr && abbr[1] !== jurabk;
}

// Splits one Satz around the cross-references it contains. Emphasis is decided
// by the caller and applies to a whole Satz, so a Frist is never a bare number
// lifted out of the sentence that qualifies it.
function linkify(text, law, jurabk) {
  const hits = [];
  for (const m of text.matchAll(PARAGRAF)) {
    const tail = text.slice(m.index + m[0].length);
    if (namesAnotherLaw(tail, jurabk)) continue;
    if (!enbezOf(law).has(`§ ${m[1]}`)) continue;
    hits.push({ at: m.index, len: m[0].length, href: `${GII}/${law}/__${m[1]}.html` });
  }
  const out = [];
  let at = 0;
  for (const hit of hits) {
    if (hit.at < at) continue;
    if (hit.at > at) out.push({ text: text.slice(at, hit.at) });
    out.push({ text: text.slice(hit.at, hit.at + hit.len), href: hit.href });
    at = hit.at + hit.len;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}

function norm(law, enbez) {
  for (const block of lawXml(law).split("<norm ")) {
    if (block.includes(`<enbez>${enbez}</enbez>`)) {
      return {
        block,
        titel: (block.match(/<titel[^>]*>([\s\S]*?)<\/titel>/)?.[1] ?? "").trim(),
        jurabk: block.match(/<jurabk>([^<]+)<\/jurabk>/)?.[1] ?? "",
        builddate: block.match(/^builddate="(\d{8})/)?.[1] ?? "",
      };
    }
  }
  return null;
}

const quotes = {};
const skipped = [];
for (const file of readdirSync(FRISTEN_DIR).filter((f) => f.endsWith(".yaml"))) {
  for (const task of load(readFileSync(join(FRISTEN_DIR, file), "utf-8")).deadlines ?? []) {
    if (!task.quote?.length) continue;
    const where = task.source_url && locate(task.source_url);
    if (!where) {
      skipped.push(`${task.id}: source_url is not a gesetze-im-internet Paragraf`);
      continue;
    }
    const found = norm(where.law, where.enbez);
    if (!found) {
      skipped.push(`${task.id}: ${where.enbez} not found in ${where.law}`);
      continue;
    }
    const all = absaetze(found.block);
    const picked = task.quote.map((n) => all.find((a) => a.n === String(n)));
    const missing = task.quote.filter((n, i) => !picked[i]);
    if (missing.length) {
      skipped.push(`${task.id}: ${where.enbez} has no Absatz ${missing.join(", ")}`);
      continue;
    }
    // Emphasis is a citation, not a judgement about which words matter: the
    // yaml names Absatz and Satz the way a lawyer would, and a Satz that does
    // not exist stops the build instead of silently emphasising nothing.
    const wanted = task.emphasize ?? {};
    const bad = [];
    const absaetzeOut = picked.map((a) => {
      // The "(1) " an Absatz opens with is a label, not part of any Satz, so it
      // stays outside the emphasis and outside the Satz count.
      const prefix = a.text.match(/^\(\d+[a-z]?\)\s*/)?.[0] ?? "";
      const parts = saetze(a.text.slice(prefix.length));
      const want = (wanted[String(a.n)] ?? []).map(Number);
      for (const i of want) if (i < 1 || i > parts.length) bad.push(`Abs. ${a.n} Satz ${i}`);

      const out = prefix ? [{ text: prefix }] : [];
      parts.forEach((satz, i) => {
        const pieces = linkify(satz, where.law, found.jurabk);
        out.push(...(want.includes(i + 1) ? pieces.map((p) => ({ ...p, mark: true })) : pieces));
        // The gap between two Sätze belongs to neither of them.
        if (i < parts.length - 1) out.push({ text: " " });
      });
      return out;
    });
    for (const key of Object.keys(wanted))
      if (!task.quote.map(String).includes(key)) bad.push(`Abs. ${key} is not quoted`);
    if (bad.length) {
      skipped.push(`${task.id}: ${where.enbez} has no ${bad.join(", ")}`);
      continue;
    }

    const d = found.builddate;
    quotes[task.id] = {
      enbez: where.enbez,
      titel: found.titel,
      url: task.source_url,
      // Stand of the wording, from the XML itself rather than from today.
      stand: d ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : null,
      complete: picked.length === all.length,
      absaetze: absaetzeOut,
    };
  }
}

const body = `// Generated by scripts/gesetze.mjs, do not edit. Run \`bun run gesetze\`.
// Wording taken verbatim from the official XML of gesetze-im-internet.de.
// Gesetze genießen keinen urheberrechtlichen Schutz (§ 5 Abs. 1 UrhG).
export interface StatuteSegment {
  text: string;
  // Part of the Satz this page is about, emphasised whole. A Frist is never a
  // bare number lifted out of the sentence that qualifies it.
  mark?: boolean;
  // A cross-reference to another Paragraf of the same Gesetz, checked to exist
  // before it was written here.
  href?: string;
}

export interface StatuteQuote {
  enbez: string;
  titel: string;
  url: string;
  stand: string | null;
  // false when only some Absätze of the Paragraf are printed, so the page can
  // say it is an excerpt instead of implying it shows the whole thing.
  complete: boolean;
  absaetze: StatuteSegment[][];
}

export const STATUTE_QUOTES: Record<string, StatuteQuote> = ${JSON.stringify(quotes, null, 2)};
`;
writeFileSync(OUT, body);
for (const s of skipped) console.error(`skipped ${s}`);
console.error(
  `${Object.keys(quotes).length} quotes, ${(body.length / 1024).toFixed(1)} KiB`,
);
