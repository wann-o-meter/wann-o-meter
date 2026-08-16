import { z } from "zod";
import { evaluateRule } from "./calendar-rule";
import { STATUTE_QUOTES } from "./statute-quotes";
import { allFristTasks, fristPath, yearsFor } from "./tasks";
import { TASK_KINDS } from "./deadline-schema";
import type { FristTask } from "./tasks";

// The shape this API answers in, written as a schema rather than assembled ad
// hoc in the route. Two reasons: the route serialises through it, so a field
// cannot quietly change shape, and /openapi.json derives its documentation from
// the same object instead of describing it a second time by hand.
//
// Server only: reads the yaml at build time. Never import from an island.

export const fristSummarySchema = z.object({
  id: z.string().meta({ description: "Stable identifier, also the page slug" }),
  label: z.string(),
  kind: z.enum(TASK_KINDS).meta({
    description:
      "statutory-absolute: the statute names the day. statutory-relative: it names an offset from a date you supply.",
  }),
  direction: z.enum(["before", "after"]).nullable().meta({
    description: "before: the deadline precedes the anchor. after: the clock starts at it.",
  }),
  tags: z.array(z.string()),
  source: z
    .object({
      label: z.string().nullable().meta({ description: 'Citation, e.g. "§ 573c BGB"' }),
      url: z.url().nullable(),
    })
    .meta({ description: "The statute this Frist comes from. Cite this, not this API." }),
  plans: z.array(z.string()).meta({ description: "Vorhaben this Frist appears in" }),
  url: z.string().meta({ description: "Human-readable page" }),
  dataUrl: z.string().meta({ description: "This Frist's full JSON" }),
});

const statuteSchema = z.object({
  enbez: z.string().meta({ description: 'Paragraf, e.g. "§ 573c"' }),
  titel: z.string(),
  url: z.url(),
  stand: z.string().nullable().meta({ description: "Date of the wording, from the official XML" }),
  excerpt: z.boolean().meta({ description: "true when only some Absätze are reproduced" }),
  absaetze: z.array(z.string()).meta({
    description:
      "Verbatim from gesetze-im-internet.de. Gesetze carry no copyright (§ 5 Abs. 1 UrhG).",
  }),
});

export const fristDetailSchema = fristSummarySchema.extend({
  offset: z.object({
    days: z.number().int().nullable().meta({
      description: "Days from the anchor date. Negative is before it. null when not researched.",
    }),
    label: z.string().nullable().meta({ description: "Set where a plain day count would mislead" }),
    earliestDays: z.number().int().nullable(),
    needsOffice: z.boolean(),
  }),
  note: z.string().nullable(),
  statute: statuteSchema.nullable(),
  occurrences: z
    .array(
      z.object({
        year: z.number().int().meta({ description: "The year the Frist is about" }),
        date: z.iso.date().meta({ description: "The day it falls on, weekends and Feiertage rolled" }),
        icsUrl: z.string(),
      }),
    )
    .meta({ description: "Only for statutory-absolute, where no input from you is needed" }),
});

export type FristSummary = z.infer<typeof fristSummarySchema>;
export type FristDetail = z.infer<typeof fristDetailSchema>;

function summary({ task, vorhaben }: FristTask): FristSummary {
  return {
    id: task.id,
    label: task.label,
    kind: task.kind,
    direction: task.direction ?? null,
    tags: task.tags,
    source: { label: task.source_label ?? null, url: task.source_url ?? null },
    plans: vorhaben.map((v) => v.slug),
    url: `/${fristPath(task.id)}/`,
    dataUrl: `/api/v1/fristen/${task.id}.json`,
  };
}

function detail(entry: FristTask): FristDetail {
  const { task } = entry;
  const quote = STATUTE_QUOTES[task.id];
  return {
    ...summary(entry),
    offset: {
      days: task.offset_days,
      label: task.offset_label ?? null,
      earliestDays: task.earliest_offset_days ?? null,
      needsOffice: task.needs_office ?? false,
    },
    note: task.note ?? null,
    statute: quote
      ? {
        enbez: quote.enbez,
        titel: quote.titel,
        url: quote.url,
        stand: quote.stand,
        excerpt: !quote.complete,
        // The page marks and links pieces of the wording. An API consumer wants
        // the sentence, so the pieces are joined back up.
        absaetze: quote.absaetze.map((segments) => segments.map((s) => s.text).join("")),
      }
      : null,
    occurrences: task.rule
      ? yearsFor(task).flatMap((year) => {
        const hit = evaluateRule(task.rule!, year, "DE");
        return hit
          ? [{ year, date: hit.date, icsUrl: `/${fristPath(task.id, year)}.ics` }]
          : [];
      })
      : [],
  };
}

export function allFristSummaries(): FristSummary[] {
  return allFristTasks()
    .map(summary)
    .sort((a, b) => a.id.localeCompare(b.id));
}

export function fristDetails(): FristDetail[] {
  return allFristTasks()
    .map(detail)
    .sort((a, b) => a.id.localeCompare(b.id));
}
