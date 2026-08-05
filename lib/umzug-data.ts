// Server-only: node:fs reads for data/umzug/. Kept out of lib/deadline-plan.ts
// because that module is imported by DeadlinePlanner.vue (client:load) - only
// Astro frontmatter may import this file.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { deadlineSchema } from "./deadline-plan";
import type { Deadline } from "./deadline-plan";

const DATA_ROOT = join(process.cwd(), "data", "umzug");
const BUNDESWEIT_FILE = "_bundesweit.yaml";

const deadlineListSchema = z.object({
  deadlines: z.array(deadlineSchema).default([]),
});

const kommuneFileSchema = deadlineListSchema.extend({
  name: z.string(),
  state: z.string(),
});

export interface UmzugKommune {
  slug: string;
  name: string;
  state: string;
}

export interface UmzugKommuneData extends UmzugKommune {
  deadlines: Deadline[];
}

function readYaml(path: string): unknown {
  return load(readFileSync(path, "utf-8"));
}

export function listUmzugKommunen(): UmzugKommune[] {
  return readdirSync(DATA_ROOT, { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".yaml") && e.name !== BUNDESWEIT_FILE)
    .map((e) => {
      const slug = e.name.replace(/\.yaml$/, "");
      const doc = kommuneFileSchema.parse(readYaml(join(DATA_ROOT, e.name)));
      return { slug, name: doc.name, state: doc.state };
    })
    .sort((a, b) => a.name.localeCompare(b.name, "de"));
}

// Bundesweit deadlines apply to every Kommune, local ones add to them - plain
// concat, no override-by-id merge.
// ponytail: concat only, override-by-id when a Kommune actually contradicts a
// federal step.
export function loadUmzugKommune(slug: string): UmzugKommuneData | null {
  let kommuneDoc: z.infer<typeof kommuneFileSchema>;
  try {
    kommuneDoc = kommuneFileSchema.parse(readYaml(join(DATA_ROOT, `${slug}.yaml`)));
  } catch {
    return null;
  }
  const bundesweit = deadlineListSchema.parse(readYaml(join(DATA_ROOT, BUNDESWEIT_FILE)));
  return {
    slug,
    name: kommuneDoc.name,
    state: kommuneDoc.state,
    deadlines: [...bundesweit.deadlines, ...kommuneDoc.deadlines],
  };
}

// The /umzug page picks a Kommune client-side rather than routing per
// Kommune, so it needs every Kommune's full deadline list up front.
export function loadAllUmzugKommunen(): UmzugKommuneData[] {
  return listUmzugKommunen()
    .map((k) => loadUmzugKommune(k.slug))
    .filter((k) => k !== null);
}
