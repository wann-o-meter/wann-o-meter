import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { deadlineSchema } from "./deadline-schema";
import { fristById } from "./fristen-data";
import type { Deadline } from "./deadline-schema";

const DATA_ROOT = join(process.cwd(), "data");
const BUNDESWEIT_FILE = "_bundesweit.yaml";
const VORHABEN_FILE = "vorhaben.yaml";
// Kept in sync by hand with the literal in the Vue islands, importing this
// module would pull node:fs into the browser bundle.
export const BUNDESWEIT_SLUG = "bundesweit";

// A plan either spells a task out or points at a Frist that lives on its own.
const entrySchema = z.union([
  z.object({ ref: z.string() }).strict(),
  deadlineSchema,
]);

const deadlineListSchema = z.object({
  deadlines: z.array(entrySchema).default([]),
});

function resolve(entries: z.infer<typeof entrySchema>[]): Deadline[] {
  return entries.map((e) => ("ref" in e ? fristById(e.ref) : e));
}

const variantFileSchema = deadlineListSchema.extend({
  name: z.string(),
  state: z.string(),
});

const vorhabenSchema = z.object({
  slug: z.string(),
  label: z.string(),
  teaser: z.string(),
  // Which way the plan runs. The page titles are built from it, so a Vorhaben
  // cannot be described backwards while its Fristen all come after the anchor.
  direction: z.enum(["backwards", "forwards"]),
  // The subject a title starts with, where the bare label would read wrong
  // ("Nach der Geburt" instead of "Geburt").
  titleSubject: z.string().optional(),
  // The anchor as a title says it after "vom", where the label does not fit.
  anchorDative: z.string().optional(),
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
  // The ones this place adds to the bundesweit plan. What makes the page worth
  // its own url, so indexing is decided on it.
  localDeadlines: Deadline[];
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
  // Membership is the directory today. The field exists so a task can later
  // belong to more than one Vorhaben without every consumer changing.
  const own = (list: z.infer<typeof entrySchema>[]) =>
    resolve(list).map((d) => ({ ...d, belongsTo: [slug] }));
  const bundesweit = deadlineListSchema.parse(readYaml(join(dir, BUNDESWEIT_FILE)));

  const local = readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".yaml") && e.name !== BUNDESWEIT_FILE)
    .map((e) => {
      const doc = variantFileSchema.parse(readYaml(join(dir, e.name)));
      return {
        slug: e.name.replace(/\.yaml$/, ""),
        label: doc.name,
        regionCode: doc.state,
        deadlines: own([...bundesweit.deadlines, ...doc.deadlines]),
        localDeadlines: own(doc.deadlines),
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label, "de"));

  // Bundesweit is always a variant: a place without its own file still needs a
  // plan, and the Feiertage of its Bundesland come from the region parameter.
  const variants = [
    {
      slug: BUNDESWEIT_SLUG,
      label: "Bundesweit",
      deadlines: own(bundesweit.deadlines),
      localDeadlines: [],
    },
    ...local,
  ];
  return { ...meta, variants };
}

export function loadAllVorhaben(): VorhabenData[] {
  return VORHABEN.map((v) => loadVorhaben(v.slug)).filter((v) => v !== null);
}
