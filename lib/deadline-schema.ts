import { z } from "zod";
import { FACET_IDS } from "./facets";

// What a task looks like, and nothing about how a date is worked out from it.
// The split is the point: parsing yaml happens once at build time, computing a
// schedule happens in the browser on every keystroke. Keeping the schemas here
// keeps Zod out of the island bundles, which import only the types.

// What a task is, before anything computes a date for it.
//   statutory-absolute  the statute names the day, no user input
//   statutory-relative  the statute names an offset from a date the user gives
//   soft                no legal anchor, so no defensible date either
export const TASK_KINDS = [
  "statutory-absolute",
  "statutory-relative",
  "soft",
] as const;

// A deadline the statute fixes by itself, written down in the task's yaml
// rather than in code. Nothing here knows any law: it reads the steps the yaml
// names and walks them. A new deadline is a yaml entry, not a new function.
export const calendarRuleSchema = z.object({
  // Where the count starts. The year it applies to comes from the caller.
  from: z.enum(["end-of-year"]),
  add_months: z.number().int().optional(),
  add_days: z.number().int().optional(),
  // Pull the result to the last day of the month it landed in.
  snap: z.enum(["end-of-month"]).optional(),
  // Saturday, Sunday and public holidays push the result to the next
  // working day.
  roll: z.enum(["next-working-day"]).optional(),
  // Earliest year this wording is the one that applies. Older years usually
  // had a transitional rule and are better answered not at all.
  first_year: z.number().int().optional(),
});

export type CalendarRule = z.infer<typeof calendarRuleSchema>;

export const deadlineSchema = z
  .object({
    id: z.string(),
    kind: z.enum(TASK_KINDS),
    // before: the deadline precedes the anchor. after: the clock starts at it.
    direction: z.enum(["before", "after"]).optional(),
    // The Vorhaben this task appears in. Filled in by the loader from the
    // directory, one entry until a second Vorhaben genuinely reuses a task.
    belongsTo: z.array(z.string()).default([]),
    label: z.string(),
    offset_days: z.number().int().nullable(),
    // How to say the Frist when a plain offset would misdescribe it. Set on the
    // Fristen that carry their own solver in data/fristen/<id>.ts.
    offset_label: z.string().optional(),
    // A Frist the statute fixes by itself, spelled out in yaml. Present exactly
    // on the tasks whose kind is statutory-absolute.
    rule: calendarRuleSchema.optional(),
    // Give this task one page per year. Only makes sense where the answer
    // actually moves from year to year, so only for a rule-fixed date.
    year_pages: z.boolean().optional(),
    // What this Frist is about, for grouping it with others. A Frist inside a
    // plan is grouped by that plan and needs none.
    tags: z.array(z.string()).default([]),
    // Which Absätze of source_url the page prints, in the statute's own words.
    // The wording itself is not stored here: scripts/gesetze.mjs pulls it from
    // the official XML into lib/statute-quotes.ts, so nobody hand-copies a law
    // and nobody has to review a paraphrase of one.
    quote: z.array(z.number().int().positive()).optional(),
    // Which Satz of which quoted Absatz this page is actually about, keyed by
    // Absatz. A pointer in the form a lawyer would cite, not a phrase someone
    // wrote: scripts/gesetze.mjs refuses to generate if the Satz is not there.
    emphasize: z.record(z.string(), z.array(z.number().int().positive())).optional(),
    needs_office: z.boolean().optional(),
    earliest_offset_days: z.number().int().optional(),
    lead_time_days: z.number().int().positive().optional(),
    lead_time_source: z.string().optional(),
    source_url: z.url().nullable(),
    source_label: z.string().optional(),
    no_source_needed: z.boolean().optional(),
    applies_if: z.array(z.enum(FACET_IDS)).optional(),
    note: z.string().optional(),
  })
  .refine((d) => (d.kind === "soft") === (d.direction === undefined), {
    message: "statutory tasks need a direction, soft tasks must not have one",
    path: ["direction"],
  })
  .refine((d) => (d.kind === "statutory-absolute") === (d.rule !== undefined), {
    message: "an absolute task is exactly one that carries a rule",
    path: ["rule"],
  })
  .refine((d) => !d.year_pages || d.rule !== undefined, {
    message: "year pages need a rule, otherwise every year says the same thing",
    path: ["year_pages"],
  })
  // Catches both halves of the same mistake: emphasis on a Frist that quotes
  // nothing, and emphasis on an Absatz the page does not print. Either way the
  // mark would silently not appear.
  .refine(
    (d) =>
      Object.keys(d.emphasize ?? {}).every((n) => d.quote?.includes(Number(n))),
    {
      message: "every emphasized Absatz has to be one the page quotes",
      path: ["emphasize"],
    },
  );

export type Deadline = z.infer<typeof deadlineSchema>;
