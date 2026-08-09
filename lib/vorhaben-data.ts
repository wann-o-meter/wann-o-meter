// Server-only: node:fs reads for data/<vorhaben>/. Kept out of
// lib/deadline-plan.ts because that module is imported by DeadlinePlanner.vue
// (client:load) - only Astro frontmatter may import this file.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { deadlineSchema } from "./deadline-plan";
import type { Deadline } from "./deadline-plan";

const DATA_ROOT = join(process.cwd(), "data");
const BUNDESWEIT_FILE = "_bundesweit.yaml";
const VORHABEN_FILE = "vorhaben.yaml";

const deadlineListSchema = z.object({
  deadlines: z.array(deadlineSchema).default([]),
});

const variantFileSchema = deadlineListSchema.extend({
  name: z.string(),
  state: z.string(),
});

const vorhabenSchema = z.object({
  slug: z.string(), // data/<slug>/ and the URL segment
  label: z.string(), // chip and nav text
  title: z.string(), // h1 and <title>
  description: z.string(),
  vorhaben: z.string(), // planner's "Vorhaben" field text
  anchorLabel: z.string(), // date field label, also the offset-0 label
  anchorName: z.string(), // bold timeline pin label
  variantLabel: z.string(),
  defaultVariant: z.string().optional(),
});

export type Vorhaben = z.infer<typeof vorhabenSchema>;

// Matches PlanVariant in src/components/deadline-planner/types.ts, kept
// separate so lib/ never imports from src/.
export interface VorhabenVariant {
  slug: string;
  label: string;
  regionCode?: string;
  deadlines: Deadline[];
}

export interface VorhabenData extends Vorhaben {
  variants: VorhabenVariant[];
}

function readYaml(path: string): unknown {
  return load(readFileSync(path, "utf-8"));
}

// Every vertical the site plans, in display order. A new one is a data folder
// plus one entry in data/vorhaben.yaml.
export const VORHABEN: Vorhaben[] = z
  .array(vorhabenSchema)
  .parse(readYaml(join(DATA_ROOT, VORHABEN_FILE)));

// Bundesweit deadlines apply everywhere, local ones add to them - plain
// concat, no override-by-id merge.
// ponytail: concat only, override-by-id when a local file actually
// contradicts a federal step.
export function loadVorhaben(slug: string): VorhabenData | null {
  const meta = VORHABEN.find((v) => v.slug === slug);
  if (!meta) return null;
  const dir = join(DATA_ROOT, slug);
  const bundesweit = deadlineListSchema.parse(readYaml(join(dir, BUNDESWEIT_FILE)));

  const local = readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".yaml") && e.name !== BUNDESWEIT_FILE)
    .map((e) => {
      const doc = variantFileSchema.parse(readYaml(join(dir, e.name)));
      return {
        slug: e.name.replace(/\.yaml$/, ""),
        label: doc.name,
        regionCode: doc.state,
        deadlines: [...bundesweit.deadlines, ...doc.deadlines],
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label, "de"));

  // Verticals with no local files yet still need one variant to select.
  const variants =
    local.length > 0
      ? local
      : [{ slug: "bundesweit", label: "Bundesweit", deadlines: bundesweit.deadlines }];
  return { ...meta, variants };
}

export function loadAllVorhaben(): VorhabenData[] {
  return VORHABEN.map((v) => loadVorhaben(v.slug)).filter((v) => v !== null);
}
