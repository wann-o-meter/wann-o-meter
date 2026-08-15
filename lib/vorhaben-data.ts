import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { deadlineSchema } from "./deadline-plan";
import type { Deadline } from "./deadline-plan";

const DATA_ROOT = join(process.cwd(), "data");
const BUNDESWEIT_FILE = "_bundesweit.yaml";
const VORHABEN_FILE = "vorhaben.yaml";
// Kept in sync by hand with the literal in the Vue islands, importing this
// module would pull node:fs into the browser bundle.
export const BUNDESWEIT_SLUG = "bundesweit";

const deadlineListSchema = z.object({
  deadlines: z.array(deadlineSchema).default([]),
});

const variantFileSchema = deadlineListSchema.extend({
  name: z.string(),
  state: z.string(),
});

const vorhabenSchema = z.object({
  slug: z.string(),
  label: z.string(),
  teaser: z.string(),
  title: z.string(),
  description: z.string(),
  vorhaben: z.string(),
  anchorLabel: z.string(),
  anchorName: z.string(),
  possessive: z.string().default("Dein"),
  variantLabel: z.string(),
  variantPreposition: z.string().default("in"),
  defaultVariant: z.string().optional(),
  // What a Vorhaben has in common with others. Carried through but not shown
  // anywhere yet.
  tags: z.array(z.string()).default([]),
});

type Vorhaben = z.infer<typeof vorhabenSchema>;

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

const VORHABEN: Vorhaben[] = z
  .array(vorhabenSchema)
  .parse(readYaml(join(DATA_ROOT, VORHABEN_FILE)));

function loadVorhaben(slug: string): VorhabenData | null {
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

  // Bundesweit is always a variant: a place without its own file still needs a
  // plan, and the Feiertage of its Bundesland come from the region parameter.
  const variants = [
    { slug: BUNDESWEIT_SLUG, label: "Bundesweit", deadlines: bundesweit.deadlines },
    ...local,
  ];
  return { ...meta, variants };
}

export function loadAllVorhaben(): VorhabenData[] {
  return VORHABEN.map((v) => loadVorhaben(v.slug)).filter((v) => v !== null);
}
