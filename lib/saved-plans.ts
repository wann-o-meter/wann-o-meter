import type { Deadline } from "./deadline-plan";

// Plans the visitor started, so the startpage can show them side by side.
// The per plan snapshot format is owned by useTaskEditor, here it is read only.

export interface SavedPlan {
  slug: string;
  variant: string;
  date: string;
  // The same facets the plan page filters by, so both count the same Fristen.
  facets: string[];
}

export interface PlanSnapshot {
  done: Record<string, boolean>;
  deleted: Record<string, boolean>;
  labels: Record<string, string>;
  offsets: Record<string, number>;
  custom: { id: string; label: string; offsetDays: number }[];
}

const INDEX_KEY = "wann:plans";

export function planStorageKey(vorhaben: string, variant: string): string {
  return `wann:plan:${vorhaben}:${variant}`;
}

function read(key: string): unknown {
  if (typeof localStorage === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem(key) ?? "null");
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
  }
}

export function loadSavedPlans(): SavedPlan[] {
  const raw = read(INDEX_KEY);
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((p) => p?.slug && p?.variant && p?.date)
    .map((p) => ({ ...p, facets: Array.isArray(p.facets) ? p.facets : [] }));
}

export function savePlan(plan: SavedPlan): void {
  const rest = loadSavedPlans().filter((p) => p.slug !== plan.slug);
  write(INDEX_KEY, [...rest, plan]);
}

export function forgetPlan(slug: string): SavedPlan[] {
  const rest = loadSavedPlans().filter((p) => p.slug !== slug);
  write(INDEX_KEY, rest);
  return rest;
}

export function readSnapshot(key: string): PlanSnapshot {
  const raw = read(key) as Partial<PlanSnapshot> | null;
  return {
    done: raw?.done ?? {},
    deleted: raw?.deleted ?? {},
    labels: raw?.labels ?? {},
    offsets: raw?.offsets ?? {},
    custom: Array.isArray(raw?.custom) ? raw.custom : [],
  };
}

export function snapshotDeadlines(
  base: Deadline[],
  snap: PlanSnapshot,
): Deadline[] {
  const custom: Deadline[] = snap.custom.map((t) => ({
    id: t.id,
    label: t.label,
    offset_days: t.offsetDays,
    source_url: null,
  }));
  return [...base, ...custom]
    .filter((d) => !snap.deleted[d.id])
    .map((d) => ({
      ...d,
      offset_days: d.id in snap.offsets ? snap.offsets[d.id] : d.offset_days,
      label: snap.labels[d.id] ?? d.label,
    }));
}
