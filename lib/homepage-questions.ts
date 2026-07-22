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

// A rotator entry - `layerIds` are lib/calendar-sources.ts CalendarEntry ids
// for the exact subject the sentence names, so the homepage calendar preview
// (src/components/HeroCalendarPreview.vue) can highlight the same thing the
// H1 just claimed instead of the two drifting apart.
export interface HomeQuestion {
  text: string;
  layerIds: string[];
}

/**
 * Fills each category's YAML-authored template (data/homepage-questions.yaml)
 * with a real subject from the site's own data, for the homepage H1 rotator
 * (src/pages/index.astro). Bounded to categories with both a template and a
 * clean, bounded subject set - German-state Feiertage only, never the 200+
 * country entries (same cut lib/calendar-sources.ts's getTodayFeedEntries
 * makes for the "Heute ist..." teaser).
 */
export function homepageQuestions(): HomeQuestion[] {
  const t = templates();
  const questions: HomeQuestion[] = [];

  for (const p of getAllPages()) {
    if (p.category === "saisonkalender" && t.saisonkalender) {
      questions.push({
        text: t.saisonkalender.replace("{subject}", seasonNoun(p.meta.title)),
        layerIds: [`saisonkalender--${p.slug}`],
      });
      continue;
    }
    if (p.category === "schulferien" && t.schulferien) {
      const name = stateName(p.slug);
      if (name) {
        questions.push({
          text: t.schulferien.replace("{subject}", name),
          layerIds: [`schulferien--${p.slug}`],
        });
      }
      continue;
    }
    if (p.category === "urlaubsfenster" && t.urlaubsfenster) {
      const name = stateName(p.slug);
      if (name) {
        questions.push({
          text: t.urlaubsfenster.replace("{subject}", name),
          layerIds: [`urlaubsfenster--${p.slug}`],
        });
      }
      continue;
    }
    if (p.category === "feiertage" && t.feiertage && p.slug.startsWith("de-")) {
      const name = stateName(p.slug);
      if (name) {
        questions.push({
          text: t.feiertage.replace("{subject}", name),
          layerIds: [`feiertage--${p.slug}`],
        });
      }
    }
  }

  // Combined Schulferien+Feiertage question per Bundesland - both categories
  // are generated 1:1 from lib/states.ts's STATES (see data/schulferien and
  // data/feiertage/generator.ts), so every state has both ids without needing
  // to look them up in getAllPages() first.
  if (t.schulferien_feiertage) {
    for (const [code, name] of Object.entries(STATES)) {
      const slug = code.toLowerCase();
      questions.push({
        text: t.schulferien_feiertage.replace("{subject}", name),
        layerIds: [`feiertage--de-${slug}`, `schulferien--${slug}`],
      });
    }
  }

  return questions;
}
