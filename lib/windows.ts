import type { MaterializedWindow } from "./schema";

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function currentWindow(
  windows: MaterializedWindow[],
  date: Date = new Date(),
): MaterializedWindow | undefined {
  const iso = isoDate(date);
  return windows.find((f) => f.from <= iso && iso <= f.to);
}

export function nextWindow(
  windows: MaterializedWindow[],
  date: Date = new Date(),
): MaterializedWindow | undefined {
  const iso = isoDate(date);
  return [...windows].filter((f) => f.from > iso).sort((a, b) => a.from.localeCompare(b.from))[0];
}
