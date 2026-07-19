// One page model for every category the site has - scraped content (see
// pipeline/main.py POST /create-page) and curated/computed calendar data
// alike. A page folder is either a walked data.yaml/page.yaml pair (facts on
// disk: scraped pages, and calendar categories with authored windows like
// Saisonkalender) or produced by a category-level generator.ts registered in
// GENERATORS below (calendar categories with nothing to author - Feiertage's
// 200+ subjects are pure code, Urlaubsfenster mixes authored school-holiday
// facts with a computed bridge-day step). Either way a page ends up with the
// same PageData shape (pages-schema.ts): `windows` for calendar-style date
// facts, `raw_data` for arbitrary scraped content - a page populates one or
// the other, not both.
//
// Routing: data/{seg1}/{seg2}/.../{slug}/ maps directly to
// /{seg1}/{seg2}/.../{slug}/ (see src/pages/[...path].astro) - no generic
// "/seiten/" wrapper, so a page's URL reflects its actual topic. A category
// can nest up to MAX_CATEGORY_DEPTH segments deep (data/sport/fussball/
// bundesliga/{slug}/) - a directory is either a page (contains page.yaml +
// data.yaml) or a further category node; which one it is is determined
// structurally, not declared anywhere. RESERVED_CATEGORIES keeps a
// top-level category folder from colliding with the site's existing
// hardcoded routes (kalender, presets, ...) or a generator-backed one
// (feiertage, urlaubsfenster - excluded from the walk so GENERATORS' output
// isn't double-counted); pipeline/main.py mirrors this list on write.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { generate as generateFeiertage } from "../data/feiertage/generator";
import { generate as generateUrlaubsfenster } from "../data/urlaubsfenster/generator";
import { materializeRawWindow, rollingYears } from "./materialization";
import { MAX_CATEGORY_DEPTH, parseCategoryMeta, parsePageData, parsePageMeta } from "./pages-schema";
import type { CategoryMeta, PageData, PageMeta } from "./pages-schema";

const DATA_ROOT = join(process.cwd(), "data");

export const RESERVED_CATEGORIES = [
  "kalender",
  "urlaubsfenster",
  "feiertage",
  "presets",
  "seiten",
  "themen",
  "api",
  "feeds",
  "impressum",
  "datenschutz",
  "schema",
];

// Categories with no facts to walk on disk (or only partial facts, read by
// the generator itself) - produce their full Page[] list in code instead. A
// static registry (not auto-discovered generator.ts files) so this stays
// synchronous: no I/O to await here, and going async would ripple into every
// getStaticPaths() that transitively calls getAllPages(). Registered
// categories MUST also be in RESERVED_CATEGORIES, or the normal directory
// walk and the generator would double-produce their pages.
const GENERATORS: Record<string, () => Page[]> = {
  feiertage: generateFeiertage,
  urlaubsfenster: generateUrlaubsfenster,
};

// "tag" is reserved at ANY depth (not just segment 1) since it's used as a
// route suffix (see src/pages/themen/[tag].astro, the global cross-cutting
// tag page a per-category-node tag route was folded into) - a category
// segment named "tag" is silently excluded from the walk, same treatment as
// a top-level RESERVED_CATEGORIES collision.
const RESERVED_AT_ANY_DEPTH = ["tag"];

export interface Page {
  category: string;
  slug: string;
  meta: PageMeta;
  data: PageData;
}

// One node per category directory, both intermediate ("sport", with no
// pages of its own, only child categories) and leaf ("sport/fussball/
// bundesliga", which directly holds pages) - src/pages/[...path].astro's
// getStaticPaths() needs both to render a category-overview page at every
// level, not just the ones that directly contain pages.
export interface CategoryNode {
  path: string; // "/"-joined, e.g. "sport/fussball/bundesliga"
  segments: string[];
  childPaths: string[]; // direct child category paths, "/"-joined
  pages: Page[]; // pages directly in this node (page.category === path), not descendants'
}

export interface LoadResult {
  pages: Page[];
  nodes: Map<string, CategoryNode>;
}

let cache: LoadResult | undefined;

function walkCategory(segments: string[], dir: string, nodes: Map<string, CategoryNode>): Page[] {
  const path = segments.join("/");
  const directPages: Page[] = [];
  const childPaths: string[] = [];
  const allPages: Page[] = [];

  const entries = readdirSync(dir, { withFileTypes: true }).filter((entry) => entry.isDirectory());
  for (const entry of entries) {
    if (RESERVED_AT_ANY_DEPTH.includes(entry.name)) continue;

    const sub = join(dir, entry.name);
    const metaPath = join(sub, "page.yaml");
    const dataPath = join(sub, "data.yaml");
    if (existsSync(metaPath) && existsSync(dataPath)) {
      const meta = parsePageMeta(load(readFileSync(metaPath, "utf-8")));
      const data = parsePageData(load(readFileSync(dataPath, "utf-8")));
      const page: Page = { category: path, slug: entry.name, meta, data };
      directPages.push(page);
      allPages.push(page);
      continue;
    }

    // Not a page folder, so it must be a further category segment - reject
    // (loudly, not silently) once that would exceed the max nesting depth
    // pages-schema.ts's category validation also enforces.
    if (segments.length >= MAX_CATEGORY_DEPTH) {
      throw new Error(
        `data/${[...segments, entry.name].join("/")}: category nesting exceeds max depth of ${MAX_CATEGORY_DEPTH} (and it isn't a page folder - missing page.yaml/data.yaml)`,
      );
    }
    const childSegments = [...segments, entry.name];
    childPaths.push(childSegments.join("/"));
    allPages.push(...walkCategory(childSegments, sub, nodes));
  }

  nodes.set(path, { path, segments, childPaths, pages: directPages });
  return allPages;
}

// Shared by loadAll() (against the real DATA_ROOT) and
// loadCategoryTreeForTests() (against a fixture root outside data/, so
// nested-category test coverage never risks shipping a fixture page in the
// real site build/sitemap - see lib/pages.test.ts).
function walkRoot(root: string, topLevelFilter: (name: string) => boolean): LoadResult {
  const nodes = new Map<string, CategoryNode>();
  const pages = existsSync(root)
    ? readdirSync(root, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .filter((entry) => topLevelFilter(entry.name) && !RESERVED_AT_ANY_DEPTH.includes(entry.name))
        .flatMap((entry) => walkCategory([entry.name], join(root, entry.name), nodes))
    : [];
  return { pages, nodes };
}

function loadAll(): LoadResult {
  const { pages: walked, nodes } = walkRoot(DATA_ROOT, (name) => !RESERVED_CATEGORIES.includes(name));

  const generated = Object.entries(GENERATORS).flatMap(([category, generate]) => {
    const pages = generate();
    nodes.set(category, { path: category, segments: [category], childPaths: [], pages });
    return pages;
  });

  return { pages: [...walked, ...generated], nodes };
}

// Test-only entry point (lib/pages.test.ts): walks an arbitrary root the
// same way loadAll() walks DATA_ROOT, bypassing the module-level cache and
// RESERVED_CATEGORIES filtering (irrelevant outside the real data/ tree).
// Lets nested-category walkCategory() coverage live against a fixture
// directory instead of a checked-in placeholder under data/.
export function loadCategoryTreeForTests(root: string): LoadResult {
  return walkRoot(root, () => true);
}

// Named loadResult() (not load()) to avoid shadowing js-yaml's `load` import
// used throughout this file to parse YAML content.
function loadResult(): LoadResult {
  if (!cache) cache = loadAll();
  return cache;
}

export function getAllPages(): Page[] {
  return loadResult().pages;
}

// Every category node the routing layer must render a category-overview
// page for (src/pages/[...path].astro) - BOTH intermediate nodes (no pages
// of their own, only child categories) and leaf nodes (directly hold
// pages). Distinct from getAllCategories() below, which only reports
// leaf-with-pages categories.
export function getAllCategoryNodes(): CategoryNode[] {
  return [...loadResult().nodes.values()];
}

export function getCategoryNode(path: string): CategoryNode | undefined {
  return loadResult().nodes.get(path);
}

// Every distinct category path pages actually use directly (leaf categories
// that hold pages, not every intermediate node - see getAllCategoryNodes()
// for that) - what llms.txt.ts and lib/calendar-sources.ts need for a
// "topic X has N pages" listing/grouping, where a pages-less intermediate
// node like "sport" would just be noise.
export function getAllCategories(): string[] {
  return [...new Set(getAllPages().map((p) => p.category))].sort((a, b) => a.localeCompare(b, "de"));
}

// Category folder names are lowercase, URL-safe slugs (routing concern) and
// stay that way for hrefs/comparisons/lookups. Display identity (a real name
// like "Religiöse Feiertage" instead of a slugified "religioese-feiertage")
// comes from data/{seg1}/.../{segN}/_category.yaml, written once when an
// operator first creates a page under that node (see pipeline/main.py POST
// /create-page). Falls back to a capitalized slug for categories that predate
// this file or never got one.
const categoryMetaCache = new Map<string, CategoryMeta>();

// A category is looked up (and falls back) as ITS OWN node, not the whole
// breadcrumb chain - for a nested path like "sport/fussball", this is the
// display name of "fussball" alone (just the last segment), not "Sport
// Fussball". Breadcrumbs (src/pages/[...path].astro) build the full chain
// by calling this once per ancestor path instead.
export function capitalizeCategory(category: string): string {
  const last = category.split("/").pop() ?? category;
  return last.charAt(0).toUpperCase() + last.slice(1);
}

// `root` defaults to the real DATA_ROOT for every production caller; tests
// pass a fixture root explicitly (see loadCategoryTreeForTests()) instead of
// needing a checked-in placeholder under data/.
export function getCategoryMeta(category: string, root: string = DATA_ROOT): CategoryMeta {
  const cacheKey = `${root} ${category}`;
  const cached = categoryMetaCache.get(cacheKey);
  if (cached) return cached;

  const fallback: CategoryMeta = { name: capitalizeCategory(category), description: "" };
  const metaPath = join(root, ...category.split("/"), "_category.yaml");
  let meta = fallback;
  if (existsSync(metaPath)) {
    try {
      meta = parseCategoryMeta(load(readFileSync(metaPath, "utf-8")));
    } catch {
      meta = fallback;
    }
  }
  categoryMetaCache.set(cacheKey, meta);
  return meta;
}

export function getPagesInCategory(category: string): Page[] {
  return getAllPages().filter((p) => p.category === category);
}

export function getPageByCategoryAndSlug(category: string, slug: string): Page | undefined {
  return getAllPages().find((p) => p.category === category && p.slug === slug);
}

export function getAllTags(): string[] {
  return [...new Set(getAllPages().flatMap((p) => p.meta.tags))].sort((a, b) =>
    a.localeCompare(b, "de"),
  );
}

export function getPagesByTag(tag: string): Page[] {
  return getAllPages().filter((p) => p.meta.tags.includes(tag));
}

// Best-effort normalization of scraper.py's two found-date shapes
// ("DD.MM.YY(YY)" and "YYYY-MM-DD") into ISO dates. These are dates the
// scraper's regex noticed somewhere in the page text, not curated calendar
// events - callers (calendar layer, ICS feed) should treat them as "found in
// source", not as verified time windows. A 2-digit year is resolved with the
// common 50/50 heuristic (00-49 -> 20xx, 50-99 -> 19xx); ambiguous, but this
// is scraped-and-guessed data by nature.
function parseFoundDate(raw: string): string | null {
  const isoMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (isoMatch) return raw;

  const dotMatch = raw.match(/^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$/);
  if (!dotMatch) return null;
  const day = Number(dotMatch[1]);
  const month = Number(dotMatch[2]);
  let year = Number(dotMatch[3]);
  if (dotMatch[3].length === 2) year += year >= 50 ? 1900 : 2000;
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function getPageDates(page: Page): string[] {
  const rawDates = page.data.raw_data.dates;
  if (!Array.isArray(rawDates)) return [];
  const parsed = rawDates
    .filter((d): d is string => typeof d === "string")
    .map(parseFoundDate)
    .filter((d): d is string => d !== null);
  return [...new Set(parsed)].sort();
}

export interface PageEvent {
  date: string;
  to?: string; // present only when it differs from `date` (a multi-day window, not a single-day marker)
  label: string;
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

// Calendar-style pages (windows populated - Feiertage/Urlaubsfenster/
// Saisonkalender, curated or computed facts) resolve their rows via the same
// materializeRawWindow() used for any RawWindow, rolled out over the current
// build's rolling years. Scraped pages (raw_data populated, windows empty)
// fall back to LLM-extracted or regex-found dates instead - see below.
export function getPageEvents(page: Page): PageEvent[] {
  if (page.data.windows.length > 0) {
    return page.data.windows
      .flatMap((w) => materializeRawWindow(w, page.slug, page.data.source, rollingYears()))
      .map((w) => ({ date: w.from, to: w.to !== w.from ? w.to : undefined, label: w.description }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }

  // Prefers LLM-extracted events (pipeline/core/extraction.py, written into
  // raw_data.llm_events by POST /extract-llm) since they carry a real label -
  // falls back to the regex-found dates with a generic label when no LLM
  // extraction has been run for this page.
  const rawEvents = page.data.raw_data.llm_events;
  if (Array.isArray(rawEvents)) {
    const events = rawEvents
      .filter((e): e is Record<string, unknown> => typeof e === "object" && e !== null)
      .map((e) => ({ date: String(e.date ?? ""), label: String(e.label ?? "").trim() }))
      .filter((e) => ISO_DATE.test(e.date) && e.label !== "");
    if (events.length > 0) return events.sort((a, b) => a.date.localeCompare(b.date));
  }
  // No page title prefix here (unlike a curated label) - every consumer
  // (the page itself, the ICS feed's SUMMARY, the calendar layer's own
  // label) already shows the page title right next to this, so repeating
  // it in every single date's label just adds noise.
  return getPageDates(page).map((date) => ({
    date,
    label: "im Quelltext gefundenes Datum",
  }));
}
