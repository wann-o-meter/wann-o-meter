import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { deadlineSchema } from "./deadline-schema";
import type { Deadline } from "./deadline-schema";

// One file per Frist, named like its page. A Vorhaben points at it by id, so
// the rule and its paragraph live in exactly one place no matter how many plans
// end up using them.
const FRISTEN_DIR = join(process.cwd(), "data", "fristen");

const fileSchema = z.object({ deadlines: z.array(deadlineSchema).default([]) });

let cache: Map<string, Deadline> | undefined;

export function allFristen(): Map<string, Deadline> {
  if (cache) return cache;
  cache = new Map();
  for (const file of readdirSync(FRISTEN_DIR).filter((f) =>
    f.endsWith(".yaml"),
  )) {
    const doc = fileSchema.parse(
      load(readFileSync(join(FRISTEN_DIR, file), "utf-8")),
    );
    for (const task of doc.deadlines) {
      if (cache.has(task.id))
        throw new Error(`duplicate Frist id: ${task.id} in ${file}`);
      cache.set(task.id, task);
    }
  }
  return cache;
}

export function fristById(id: string): Deadline {
  const found = allFristen().get(id);
  if (!found) throw new Error(`unknown Frist ref: ${id}`);
  return found;
}
