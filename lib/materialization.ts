import { resolution, resolveMonthWindow } from "./date";
import type { MaterializedWindow, RawWindow, Source } from "./schema";

const DATA_AS_OF = "2026-07-11";

export function holidaySource(): Source {
  return {
    url: "https://www.npmjs.com/package/date-holidays",
    retrieved_at: DATA_AS_OF,
    license: "own_derivation",
    license_note:
      "Eigene Ableitung aus den gesetzlichen Feiertagen der Bundesländer (Bibliothek date-holidays, basierend auf den jeweiligen Feiertagsgesetzen).",
    extraction: "parser",
  };
}

export function rollingYears(
  startYear: number = new Date().getFullYear(),
  additionalCount = 2,
): number[] {
  return Array.from({ length: additionalCount + 1 }, (_, i) => startYear + i);
}

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
