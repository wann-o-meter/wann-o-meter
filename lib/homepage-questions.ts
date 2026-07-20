import { readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { getAllPages } from "./pages";
import { parseHomepageQuestionTemplates } from "./schema";
import { seasonNoun } from "./today-teaser";
import { STATES } from "./states";

const FILE = join(process.cwd(), "data/homepage-questions.yaml");

let cache: Record<string, string> | undefined;

function templates(): Record<string, string> {
  if (!cache) cache = parseHomepageQuestionTemplates(load(readFileSync(FILE, "utf-8")));
  return cache;
}

// Bundesland display name for a state-coded slug ("bw", "de-bw") - undefined
// for anything else (e.g. Feiertage's 200+ non-DE countries), which callers
// use to skip that page rather than render a broken sentence.
function stateName(slug: string): string | undefined {
  const code = slug.replace(/^de-/, "").toUpperCase();
  return STATES[code];
}

/**
 * Fills each category's YAML-authored template (data/homepage-questions.yaml)
 * with a real subject from the site's own data, for the homepage H1 rotator
 * (src/pages/index.astro). Bounded to categories with both a template and a
 * clean, bounded subject set - German-state Feiertage only, never the 200+
 * country entries (same cut lib/calendar-sources.ts's getTodayFeedEntries
 * makes for the "Heute ist..." teaser).
 */
export function homepageQuestions(): string[] {
  const t = templates();
  const questions: string[] = [];

  for (const p of getAllPages()) {
    if (p.category === "saisonkalender" && t.saisonkalender) {
      questions.push(t.saisonkalender.replace("{subject}", seasonNoun(p.meta.title)));
      continue;
    }
    if (p.category === "schulferien" && t.schulferien) {
      const name = stateName(p.slug);
      if (name) questions.push(t.schulferien.replace("{subject}", name));
      continue;
    }
    if (p.category === "urlaubsfenster" && t.urlaubsfenster) {
      const name = stateName(p.slug);
      if (name) questions.push(t.urlaubsfenster.replace("{subject}", name));
      continue;
    }
    if (p.category === "feiertage" && t.feiertage && p.slug.startsWith("de-")) {
      const name = stateName(p.slug);
      if (name) questions.push(t.feiertage.replace("{subject}", name));
    }
  }

  return questions;
}
