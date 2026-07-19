import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";
import { parsePreset } from "./schema";
import type { Preset } from "./schema";

const DATA_DIR = join(process.cwd(), "data/presets");

let cache: Preset[] | undefined;

export function allPresets(): Preset[] {
  if (!cache) {
    cache = readdirSync(DATA_DIR)
      .filter((f) => f.endsWith(".yaml"))
      .map((f) => parsePreset(load(readFileSync(join(DATA_DIR, f), "utf-8"))));
  }
  return cache;
}

export function presetBySlug(slug: string): Preset | undefined {
  return allPresets().find((p) => p.slug === slug);
}

export function calendarUrl(preset: Preset): string {
  const params = new URLSearchParams({ region: preset.region, layers: preset.layers.join(",") });
  return `/kalender?${params}`;
}
