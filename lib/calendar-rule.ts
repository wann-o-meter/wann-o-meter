import { z } from "zod";
import { loadHolidays, rollToLandingDay } from "./business-days";
import { formatDate } from "./format-date";
import type { DerivationStep } from "./notice-period";

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

export interface RuleResult {
  date: string;
  derivation: DerivationStep[];
}

const iso = (d: Date) => d.toISOString().slice(0, 10);
const MONTHS = (n: number) => (n === 1 ? "ein Monat" : `${n} Monate`);
const DAYS = (n: number) => (n === 1 ? "ein Tag" : `${n} Tage`);

export function evaluateRule(
  rule: CalendarRule,
  year: number,
  countryCode: string,
  regionCode?: string,
): RuleResult | null {
  if (rule.first_year !== undefined && year < rule.first_year) return null;

  const derivation: DerivationStep[] = [];
  // Only one start for now, and the enum keeps it that way until another is
  // written down here on purpose.
  let d = new Date(Date.UTC(year, 11, 31));
  derivation.push({
    step: "start",
    label: `Ablauf des Kalenderjahrs ${year}`,
    value: iso(d),
  });

  if (rule.add_months) {
    // Keep the day of the month, but never spill into the next one: the 31st
    // plus two months is the 30th, not the 1st.
    const day = d.getUTCDate();
    const month = d.getUTCMonth() + rule.add_months;
    const lastDay = new Date(
      Date.UTC(d.getUTCFullYear(), month + 1, 0),
    ).getUTCDate();
    d = new Date(Date.UTC(d.getUTCFullYear(), month, Math.min(day, lastDay)));
    derivation.push({
      step: "add-months",
      label: `${MONTHS(rule.add_months)} später, also der ${formatDate(iso(d))}`,
      value: iso(d),
    });
  }
  if (rule.add_days) {
    d = new Date(d.getTime() + rule.add_days * 86400000);
    derivation.push({
      step: "add-days",
      label: `${DAYS(rule.add_days)} später, also der ${formatDate(iso(d))}`,
      value: iso(d),
    });
  }
  if (rule.snap === "end-of-month") {
    d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
    derivation.push({
      step: "end-of-month",
      label: `Ende des Monats, also der ${formatDate(iso(d))}`,
      value: iso(d),
    });
  }
  if (rule.roll === "next-working-day") {
    const rolled = rollToLandingDay(
      d,
      loadHolidays(d.getUTCFullYear(), countryCode, regionCode),
    );
    if (iso(rolled) !== iso(d)) {
      derivation.push({
        step: "next-working-day",
        label: `Das ist ein Samstag, Sonntag oder Feiertag, deshalb der nächste Werktag: ${formatDate(iso(rolled))}`,
        value: iso(rolled),
      });
      d = rolled;
    }
  }
  return { date: iso(d), derivation };
}

// The next time this deadline comes round on or after `from`. The rolled day
// is the one that counts: a deadline whose raw day has passed but whose working
// day has not is still open.
export function nextOccurrence(
  rule: CalendarRule,
  from: string,
  countryCode: string,
  regionCode?: string,
): RuleResult | null {
  const start = Number(from.slice(0, 4));
  for (let year = start - 2; year <= start + 3; year++) {
    const hit = evaluateRule(rule, year, countryCode, regionCode);
    if (hit && hit.date >= from) return hit;
  }
  return null;
}
