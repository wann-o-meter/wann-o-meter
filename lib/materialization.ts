// Materialization step (PLAN.md section 5.1 / 7): resolves a RawWindow
// (YAML facts, or a synthetic one built by a category's generator.ts - see
// lib/pages.ts) into concrete per-year MaterializedWindow entries, rolling
// over the current year + 2. Pages/JSON/ICS consume only this result.
import { resolution, resolveMonthWindow } from "./date";
import type { MaterializedWindow, RawWindow, Source } from "./schema";

const DATA_AS_OF = "2026-07-11";

export function holidaySource(): Source {
  return {
    url: "https://www.npmjs.com/package/date-holidays",
    retrieved_at: DATA_AS_OF,
    license: "own_derivation",
    license_note:
      "Own derivation from the statutory holidays of each German state (date-holidays library, based on each state's holiday laws).",
    extraction: "parser", // code computes this, no human types it
  };
}

export function rollingYears(
  startYear: number = new Date().getFullYear(),
  additionalCount = 2,
): number[] {
  return Array.from({ length: additionalCount + 1 }, (_, i) => startYear + i);
}

/**
 * Resolves a single raw window's source_urls against the file's full
 * sources[] list, keeping only the sources that actually reported that
 * window instead of blind-attaching every source the file has ever
 * recorded. Falls back to the full list when source_urls is absent (legacy
 * windows predating this field, see rawWindowSchema in lib/schema.ts) or
 * when none of it resolves (defensive - schema validation already rejects
 * unresolvable references, so this should not normally trigger).
 */
function resolveWindowSources(raw: RawWindow, sources: Source[]): Source[] {
  if (!raw.source_urls || raw.source_urls.length === 0) return sources;
  const matched = sources.filter((s) => raw.source_urls!.includes(s.url));
  return matched.length > 0 ? matched : sources;
}

export function materializeRawWindow(
  raw: RawWindow,
  subjectId: string,
  sources: Source[],
  years: number[],
): MaterializedWindow[] {
  const targetYears = raw.year === null ? years : [raw.year];
  const windowSources = resolveWindowSources(raw, sources);

  return targetYears
    .filter((year) => years.includes(year))
    .map((year) => {
      let { from, to } = raw;
      if (raw.year === null && resolution(raw.from) === "month") {
        ({ from, to } = resolveMonthWindow(raw.from, raw.to, year));
      }
      return {
        subject_id: subjectId,
        year,
        from,
        to,
        type: raw.type,
        precision: raw.precision,
        ics: raw.ics,
        description: raw.name ?? raw.type,
        source: windowSources,
        value: raw.value,
        unit: raw.unit,
      };
    });
}

