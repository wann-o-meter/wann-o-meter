import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { z } from "zod";
import { deadlineSchema } from "./deadline-plan";
import { HOLIDAYS_DE } from "./holidays-de-data";
import { BUNDESWEIT_SLUG, loadAllVorhaben } from "./vorhaben-data";
import type { Deadline } from "./deadline-plan";
import type { VorhabenData } from "./vorhaben-data";

const FRISTEN_DIR = join(process.cwd(), "data", "fristen");

const fileSchema = z.object({ deadlines: z.array(deadlineSchema).default([]) });

export interface FristTask {
  task: Deadline;
  // The plan this task is part of, if any. A task under data/fristen stands on
  // its own until a Vorhaben bundles it.
  vorhaben?: VorhabenData;
}

export function fristPath(id: string, year?: number): string {
  return year ? `frist/${id}/${year}` : `frist/${id}`;
}

// Only the tasks that carry a statutory basis get a page of their own. A soft
// task has no defensible date, so a page about it would say nothing.
export function allFristTasks(): FristTask[] {
  const out: FristTask[] = [];

  for (const v of loadAllVorhaben()) {
    // The bundesweit variant holds every task of the Vorhaben. The Gemeinde
    // variants repeat those and add local ones, which are all soft.
    const base = v.variants.find((x) => x.slug === BUNDESWEIT_SLUG);
    for (const task of base?.deadlines ?? [])
      if (task.kind !== "soft") out.push({ task, vorhaben: v });
  }

  for (const file of readdirSync(FRISTEN_DIR).filter((f) =>
    f.endsWith(".yaml"),
  )) {
    const doc = fileSchema.parse(
      load(readFileSync(join(FRISTEN_DIR, file), "utf-8")),
    );
    for (const task of doc.deadlines)
      if (task.kind !== "soft") out.push({ task });
  }

  // The id is the URL, so a collision would quietly drop a page.
  const seen = new Set<string>();
  for (const { task } of out) {
    if (seen.has(task.id)) throw new Error(`duplicate task id: ${task.id}`);
    seen.add(task.id);
  }
  return out;
}

// A rule needs the holidays of the year its deadline lands in, so the table
// decides how far the year pages reach. Regenerating it extends them.
export function yearsFor(task: Deadline): number[] {
  if (!task.year_pages || !task.rule) return [];
  // A deadline for year Y lands in Y+1, so the table's first year already
  // answers the year before it.
  const covered = Object.keys(HOLIDAYS_DE.DE).map(Number);
  const first = Math.max(
    task.rule.first_year ?? -Infinity,
    Math.min(...covered) - 1,
  );
  const last = Math.max(...covered) - 1;
  const years: number[] = [];
  for (let y = first; y <= last; y++) years.push(y);
  return years;
}
