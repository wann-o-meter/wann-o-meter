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
// H1 just claimed instead of the two drifting apart. `before`/`emphasis`/
// `after` split the sentence around its **-marked topic clause (see
// data/homepage-questions.yaml) so the rotator can render that span in a
// distinct style - `text` is the flat, marker-stripped sentence for the
// static/no-JS H1 fallback and for callers that just want the words.
export interface HomeQuestion {
  text: string;
  before: string;
  emphasis: string;
  after: string;
  layerIds: string[];
}

// Fills {subject} into a template, then splits it on its one **emphasis**
// span. A template without markers (shouldn't happen given every entry in
// data/homepage-questions.yaml has one, but not schema-enforced) just comes
// back as all "before", no emphasis.
function render(template: string, subject: string): Pick<HomeQuestion, "text" | "before" | "emphasis" | "after"> {
  const filled = template.replace("{subject}", subject);
  const match = filled.match(/^(.*?)\*\*(.*?)\*\*(.*)$/s);
  const [, before, emphasis, after] = match ?? [, filled, "", ""];
  return { text: before + emphasis + after, before, emphasis, after };
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
        ...render(t.saisonkalender, seasonNoun(p.meta.title)),
        layerIds: [`saisonkalender--${p.slug}`],
      });
      continue;
    }
    if (p.category === "schulferien" && t.schulferien) {
      const name = stateName(p.slug);
      if (name) {
        questions.push({
          ...render(t.schulferien, name),
          layerIds: [`schulferien--${p.slug}`],
        });
      }
      continue;
    }
    if (p.category === "urlaubsfenster" && t.urlaubsfenster) {
      const name = stateName(p.slug);
      if (name) {
        questions.push({
          ...render(t.urlaubsfenster, name),
          layerIds: [`urlaubsfenster--${p.slug}`],
        });
      }
      continue;
    }
    if (p.category === "feiertage" && t.feiertage && p.slug.startsWith("de-")) {
      const name = stateName(p.slug);
      if (name) {
        questions.push({
          ...render(t.feiertage, name),
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
        ...render(t.schulferien_feiertage, name),
        layerIds: [`feiertage--de-${slug}`, `schulferien--${slug}`],
      });
    }
  }

  return questions;
}
