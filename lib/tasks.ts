import { HOLIDAYS_DE } from "./holidays-de-data";
import { allFristen } from "./fristen-data";
import { loadAllVorhaben } from "./vorhaben-data";
import type { Deadline } from "./deadline-plan";
import type { VorhabenData } from "./vorhaben-data";

export interface FristTask {
  task: Deadline;
  // Every plan that points at this Frist. A Frist can belong to several, or to
  // none at all.
  vorhaben: VorhabenData[];
}

export function fristPath(id: string, year?: number): string {
  return year ? `frist/${id}/${year}` : `frist/${id}`;
}

// Every Frist that lives in data/fristen, with the plan that references it.
export function allFristTasks(): FristTask[] {
  const plans = loadAllVorhaben();
  return [...allFristen().values()].map((task) => ({
    task,
    vorhaben: plans.filter((v) =>
      v.variants.some((variant) =>
        variant.deadlines.some((d) => d.id === task.id),
      ),
    ),
  }));
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
