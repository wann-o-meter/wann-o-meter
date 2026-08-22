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

// What a place may add to a task the whole country shares: who does it here,
// what to bring here, where that is written here. Never a Frist and never a
// Paragraf, and .strict() is what enforces that. A place cannot rewrite the
// law, only say where in town it happens.
const patchSchema = z
  .object({
    id: z.string(),
    authority: z.string().optional(),
    documents: z.array(z.string()).optional(),
    source_url: z.url().nullable().optional(),
    source_label: z.string().optional(),
    lead_time_days: z.number().int().positive().optional(),
    lead_time_source: z.string().optional(),
    no_source_needed: z.boolean().optional(),
    checked_on: z.iso.date().optional(),
    note: z.string().optional(),
  })
  .strict();

type Patch = z.infer<typeof patchSchema>;

// A plan either spells a task out, points at a Frist that lives on its own, or
// patches one it already has. Order matters: a full task carries keys the patch
// refuses, and a patch is missing keys a full task needs, so each falls through
// to the one it belongs to.
const entrySchema = z.union([
  z.object({ ref: z.string() }).strict(),
  patchSchema,
  deadlineSchema,
]);

function isPatch(e: z.infer<typeof entrySchema>): e is Patch {
  return !("ref" in e) && !("kind" in e);
}

export interface Patched {
  all: Deadline[];
  // The ones this place actually said something about.
  local: Deadline[];
}

// Fill the shared tasks in with what a place says about them. Patched in place,
// so the plan keeps the order the bundesweit file sets, and a task nobody
// patched comes back untouched.
export function applyPatches(shared: Deadline[], patches: Patch[], where: string): Patched {
  const byId = new Map(patches.map((x) => [x.id, x]));
  // A patch naming a task the plan does not have is a typo, and a silent one
  // would look exactly like a Gemeinde nobody has researched yet.
  for (const id of byId.keys()) {
    if (!shared.some((d) => d.id === id)) throw new Error(`${where}: patches unknown task ${id}`);
  }
  const all = shared.map((d) => (byId.has(d.id) ? { ...d, ...byId.get(d.id) } : d));
  return { all, local: all.filter((d) => byId.has(d.id)) };
}

const deadlineListSchema = z.object({
  deadlines: z.array(entrySchema).default([]),
});

function resolve(entries: z.infer<typeof entrySchema>[]): Deadline[] {
  return entries
    .filter((e) => !isPatch(e))
    .map((e) => ("ref" in e ? fristById(e.ref) : (e as Deadline)));
}

const variantFileSchema = deadlineListSchema.extend({
  name: z.string(),
  state: z.string(),
});

const vorhabenSchema = z.object({
  slug: z.string(),
  label: z.string(),
  teaser: z.string(),
  // The subject a title starts with, where "<Label> planen" would read wrong
  // ("Nach der Geburt" instead of "Geburt planen").
  titleSubject: z.string().optional(),
  // The title for a Vorhaben whose plan rests on no statute at all, where the
  // generated one would promise a Paragraf the page cannot show.
  titleFallback: z.string().optional(),
  // What a place page is called, where the query people actually type is not
  // the one the generated title answers. {ort} is the Gemeinde. Without these
  // a place page keeps the generated title every other page gets.
  placeTitle: z.string().optional(),
  placeHeading: z.string().optional(),
  vorhaben: z.string(),
  anchorLabel: z.string(),
  anchorName: z.string(),
  // How the site says this Vorhaben belongs to the visitor: "Dein" Umzug,
  // "Deine" Geburt. Left out where nobody owns the event, and then no surface
  // puts a pronoun in front of it.
  possessive: z.string().optional(),
  // The anchor as the plan headline says it to the visitor: "Dein Umzugstag".
  // One phrase and not a pronoun, because the article follows the anchor's own
  // gender and case, which no rule derives from the label. Left out where the
  // date belongs to nobody, and then the headline names it plainly.
  anchorPersonal: z.string().optional(),
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
      const merged = applyPatches(
        own(bundesweit.deadlines),
        doc.deadlines.filter(isPatch),
        `${slug}/${e.name}`,
      );
      const added = own(doc.deadlines);
      return {
        slug: e.name.replace(/\.yaml$/, ""),
        label: doc.name,
        regionCode: doc.state,
        deadlines: [...merged.all, ...added],
        // A patched task is a local fact: it is what this page has that the
        // bundesweit plan does not, so indexing is decided on it too.
        localDeadlines: [...merged.local, ...added],
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
