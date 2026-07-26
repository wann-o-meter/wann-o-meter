// Year-scoped variants of any dated page: /urlaubsfenster/nw/2027/ next to the
// evergreen /urlaubsfenster/nw/, /astronomie/sonnenfinsternis/2027/ next to
// /astronomie/sonnenfinsternis/. Long-tail search is year-shaped ("Brückentage
// NRW 2027", "Sonnenfinsternis 2027", "Feiertage Spanien 2027") and an
// evergreen page can only rank for one thing at a time, so each year gets its
// own URL, title and H1.
//
// The rule is STRUCTURAL, not a per-category allowlist: any page whose data
// spans more than one year gets year pages, whatever the category or window
// type. Nothing here branches on "is this a holiday / an eclipse / a
// vegetable" - the only category-aware part is the state ABBREVIATION in the
// title, which exists because "NRW" is what people type, not because
// Urlaubsfenster is special.
//
// Everything is pure so it can be unit-tested (lib/year-pages.test.ts) -
// src/pages/[...path].astro only maps it onto markup. That matters most for
// eventsInYear()/eventYears(), whose overlap handling is the one thing a
// passing `astro build` cannot tell you is wrong.

import { getAllPages, getPageEvents } from "./pages";
import { STATE_ABBREVIATIONS, STATES } from "./states";
import type { Page, PageEvent } from "./pages";

// The three categories that are per-state as well as per-year. Only used to
// resolve a state ABBREVIATION and to cross-link the same state across topics -
// year pages themselves are not limited to these.
export const YEAR_TOPICS = ["urlaubsfenster", "schulferien", "feiertage"] as const;
export type YearTopic = (typeof YEAR_TOPICS)[number];

// Feiertage namespaces its German pages as "de-{code}" because a bare code
// collides with a country: /feiertage/bw/ is BOTSWANA and /feiertage/by/ is
// Belarus, both real pages. Getting this backwards would point every sibling
// link at the wrong country's holidays, so it is the inverse of lib/pages.ts's
// stateTag() and must stay that way.
export function stateSlug(topic: YearTopic, code: string): string {
  const lower = code.toLowerCase();
  return topic === "feiertage" ? `de-${lower}` : lower;
}

// The German state a page is about, or undefined for everything else (a
// Feiertage COUNTRY page, an eclipse page, a scraped page). Those still get
// year pages - they just get their plain title instead of an abbreviation.
export function yearSubjectCode(category: string, slug: string): string | undefined {
  if (!YEAR_TOPICS.includes(category as YearTopic)) return undefined;
  const code = category === "feiertage" ? (slug.startsWith("de-") ? slug.slice(3) : undefined) : slug;
  return code && STATES[code.toUpperCase()] ? code.toUpperCase() : undefined;
}

// What a year page calls itself. `label` is what leads the H1 - the state
// abbreviation where one exists ("Brückentage NRW"), otherwise the page's own
// title ("Sonnenfinsternis", "Feiertage Spanien", "Spargel"). `fullName` is
// only set when it differs from the label, so callers can append it without
// producing "Bayern ... Bayern".
export interface YearSubject {
  label: string;
  fullName?: string;
  tail?: string; // descriptive clause for the <title>, state topics only
}

const STATE_TAILS: Record<YearTopic, { heading: string; tail: string }> = {
  urlaubsfenster: { heading: "Brückentage", tail: "optimale Urlaubsfenster" },
  schulferien: { heading: "Schulferien", tail: "Ferientermine" },
  feiertage: { heading: "Feiertage", tail: "gesetzliche Feiertage" },
};

export function yearSubject(page: Page): YearSubject {
  const code = yearSubjectCode(page.category, page.slug);
  if (!code) return { label: page.meta.title };
  const { heading, tail } = STATE_TAILS[page.category as YearTopic];
  const name = STATES[code];
  const abbr = STATE_ABBREVIATIONS[code];
  return { label: `${heading} ${abbr ?? name}`, fullName: abbr ? name : undefined, tail };
}

export function yearHref(category: string, slug: string, year: number): string {
  return `/${category}/${slug}/${year}/`;
}

export function yearLabel(page: Page, year: number): string {
  return `${yearSubject(page).label} ${year}`;
}

// Every calendar year an event TOUCHES, not just the one it starts in. School
// holidays make this load-bearing: NW's Weihnachtsferien run 2026-12-23 to
// 2027-01-06, so they belong on both the 2026 and the 2027 page. Filtering on
// the start year (or on RawWindow.year, which says 2026 for exactly this
// window) would silently drop January's holidays from "Schulferien NRW 2027".
export function eventYears(events: PageEvent[]): number[] {
  const years = new Set<number>();
  for (const e of events) {
    const first = Number(e.date.slice(0, 4));
    const last = Number((e.to ?? e.date).slice(0, 4));
    for (let y = first; y <= last; y++) years.add(y);
  }
  return [...years].sort((a, b) => a - b);
}

// Overlap, for the same reason as eventYears(): an event is in `year` if any
// part of it falls inside that year.
export function eventsInYear(events: PageEvent[], year: number): PageEvent[] {
  return events.filter((e) => e.date <= `${year}-12-31` && (e.to ?? e.date) >= `${year}-01-01`);
}

// EVERY year a page has data for gets a page - deliberately uncapped. A cap
// would mean some year pills navigate to a real page and others only filter
// the list in place, i.e. one control with two behaviours; whether a year is
// prerendered or not must not be something a visitor can feel. The wide rows
// that come with that (data/astronomie/sonnenfinsternis spans 1901-2100) are a
// DISPLAY problem, solved by the pager in DateListControls.astro, not by
// generating fewer pages.
//
// The one exception is structural, not a cap: a page whose data covers a
// single year gets NO year page, because it would be a byte-for-byte retelling
// of the evergreen page - duplicate content competing with itself. (That is
// what keeps single-date scraped event pages out, without the rule needing to
// know what a scraped event is.)
export function yearsForPage(page: Page): number[] {
  const years = eventYears(getPageEvents(page));
  return years.length > 1 ? years : [];
}

// "category/slug" -> its years. Built once and used for BOTH path generation
// and every internal link, which is the point: prev/next year and sibling links
// are rendered only if the target is in here, so a year page can never link to
// a year that was never generated. (A 404 from a link like that would not fail
// the build - it would just quietly exist.)
//
// Cached because Astro hoists getStaticPaths() out of the page's frontmatter
// scope (it cannot reference a module-level const there), so the route calls
// this again in every year-page render - each call otherwise re-materializes
// every window of every page on the site.
let cache: Map<string, number[]> | undefined;

export function yearIndex(): Map<string, number[]> {
  if (!cache) cache = buildYearIndex(getAllPages());
  return cache;
}

export function buildYearIndex(pages: Page[]): Map<string, number[]> {
  const index = new Map<string, number[]>();
  for (const page of pages) {
    const years = yearsForPage(page);
    if (years.length > 0) index.set(`${page.category}/${page.slug}`, years);
  }
  return index;
}

// Cross-links from a year page to the same year elsewhere. Two rules, neither
// of which inspects a window's type: the same STATE across the state topics
// (Brückentage NRW 2027 -> Schulferien NRW 2027), or failing that the page's
// SIBLINGS in the same category (Sonnenfinsternis 2027 -> Mondfinsternis 2027).
// Capped, because a category like Saisonkalender would otherwise link every
// page to every other one.
const MAX_SIBLINGS = 6;

export function siblingPages(page: Page, all: Page[]): Page[] {
  const code = yearSubjectCode(page.category, page.slug);
  if (code) {
    return YEAR_TOPICS.filter((t) => t !== page.category)
      .map((t) => all.find((p) => p.category === t && p.slug === stateSlug(t, code)))
      .filter((p): p is Page => p !== undefined);
  }
  return all
    .filter((p) => p.category === page.category && p.slug !== page.slug)
    .slice(0, MAX_SIBLINGS);
}

export interface YearCopy {
  h1: string;
  title: string;
  description: string;
  intro: string;
  faq: { question: string; answer: string }[];
}

function de(iso: string): string {
  return `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}`;
}

function dateRange(e: PageEvent): string {
  return e.to && e.to !== e.date ? `${de(e.date)} bis ${de(e.to)}` : de(e.date);
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

// Templated from the year's own events - no LLM at build time, but also not the
// same sentence on every page: the count, the dates and the longest/best entry
// all come from the data, so each page says something only true of itself.
// That is what keeps a year page from being a thin duplicate of the evergreen
// one. Deliberately generic: it reads the events, never the category.
export function yearCopy(page: Page, year: number, events: PageEvent[]): YearCopy {
  const subject = yearSubject(page);
  const { label, fullName, tail } = subject;
  const h1 = `${label} ${year}`;
  const title = tail ? `${h1} – ${tail}${fullName ? ` ${fullName}` : ""}` : `${h1} – alle Termine im Überblick`;
  const name = fullName ?? label;

  const count = events.length;
  const listed = events.map(dateRange);
  const dates = listed.length <= 3 ? listed.join(", ") : `${listed.slice(0, 3).join(", ")} und ${listed.length - 3} weitere`;
  const longest = [...events].sort((a, b) => span(b) - span(a))[0];
  // Urlaubsfenster is the one page kind whose rows carry a ratio (RawWindow
  // .value), so "the best one" is meaningful there and simply absent elsewhere -
  // read off the data, not off the category name.
  const best = events.some((e) => e.value !== undefined)
    ? [...events].sort((a, b) => (b.value ?? 0) - (a.value ?? 0))[0]
    : undefined;

  const intro = count > 1
    ? best
      ? `${year} gibt es ${plural(count, "Eintrag", "Einträge")} für ${name}. Der beste: ${best.label}`
      : `${year} gibt es ${plural(count, "Termin", "Termine")} für ${name}: ${dates}.`
    : ``;

  const faq: { question: string; answer: string }[] = [];
  if (count > 0) {
    faq.push({
      question: `Wann ist ${label} ${year}?`,
      answer: best
        ? `${year} gibt es ${plural(count, "Eintrag", "Einträge")} für ${name}. Der beste liegt vom ${dateRange(best)}: ${best.label}`
        : `${name} ${year}: ${events.map((e) => `${e.label} (${dateRange(e)})`).join(", ")}.`,
    });
    if (longest && longest.to && longest.to !== longest.date) {
      faq.push({
        question: `Wie lange dauert der längste Zeitraum ${year}?`,
        answer: `Der längste Zeitraum ${year} ist ${longest.label} vom ${dateRange(longest)}.`,
      });
    }
    faq.push({
      question: `Kann ich ${label} als Kalender abonnieren?`,
      answer: `Ja. Wann-O-Meter stellt ${name} als ICS-Feed bereit - im Kalender abonniert kommen neue Termine automatisch dazu, ohne dass du hier nachsehen musst.`,
    });
  }

  const description = fullName
    ? `${h1}: ${tail} für ${fullName} ${year} mit Datum und Wochentag. Als ICS-Kalender abonnierbar.`
    : `${h1}: alle Termine mit Datum und Wochentag. Als ICS-Kalender abonnierbar.`;

  return { h1, title, description, intro, faq };
}

function span(e: PageEvent): number {
  return Date.parse(`${e.to ?? e.date}T00:00:00Z`) - Date.parse(`${e.date}T00:00:00Z`);
}
