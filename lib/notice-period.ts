// § 573c Abs. 1 BGB: "Die Kündigung ist spätestens am dritten Werktag eines
// Kalendermonats zum Ablauf des übernächsten Monats zulässig." A fixed day
// count (e.g. "-90 Tage") is only an approximation - the real deadline
// depends on which weekdays/holidays fall in the notice month, and moves by
// a few days from year to year and by region. This computes the exact day,
// on top of the counting/landing primitives in lib/business-days.ts.
import { formatDate } from "./format-date";
import { MONTH_NAMES } from "./date-display";
import { loadHolidays, nthCountingDayOfMonth } from "./business-days";

export interface DerivationStep {
  step: string; // stable identifier - tests assert on this, not on prose
  label: string; // human-readable, shown in the UI as-is
  value?: string; // the concrete date/month this step establishes, if any
}

export interface NoticeDeadlineResult {
  date: string; // ALWAYS derived from targetEndMonth - never swapped for the rescue date, or editing the anchor day would stop visibly doing anything once past-deadline
  leaseEndMonth: string; // YYYY-MM the tenancy would end - always targetEndMonth
  derivation: DerivationStep[];
  pastDeadline: boolean; // true when `date` has already passed `today`
  rescue: { date: string; leaseEndMonth: string } | null; // earliest still-reachable alternative, informational only, set only when pastDeadline
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function monthLabel(yyyyMm: string): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}
function addMonths(yyyyMm: string, n: number): { year: number; month0: number } {
  const [y, m] = yyyyMm.split("-").map(Number);
  const total = m - 1 + n;
  const year = y + Math.floor(total / 12);
  const month0 = ((total % 12) + 12) % 12;
  return { year, month0 };
}
function monthKey(year: number, month0: number): string {
  return `${year}-${String(month0 + 1).padStart(2, "0")}`;
}

/**
 * Latest day notice can be given (§ 573c Abs. 1 BGB) for the tenancy to end
 * by `targetEndMonth` (YYYY-MM) - notice by the third Werktag of month M
 * takes effect at the end of month M+2, so the notice month is
 * `targetEndMonth` minus two.
 *
 * `targetEndMonth` is an explicit parameter, not derived internally from a
 * move date - "no overlap month" is a real assumption (many people want one
 * on purpose), and it stays visible/overridable at the call site instead of
 * buried in this function. There's no UI control to change it yet (see
 * lib/deadline-plan.ts's call site) - that's a known follow-up, not
 * something this function should paper over.
 *
 * `regionCode` is nominally the *recipient's* (the landlord's) Bundesland
 * per § 193 BGB's Erklärungsort - real calculators ask for this directly.
 * This product only knows the destination Kommune's Bundesland, and uses
 * that as a stand-in; the assumption is named in the derivation so it's
 * checkable, not hidden in a Set.
 *
 * If the deadline for `targetEndMonth` has already passed `today`, `date`
 * still comes back as that (past) deadline - it's derived from the anchor
 * day the user actually chose, and must keep tracking it 1:1, including
 * showing up as an overdue task like any other. `rescue` additionally
 * reports the earliest month that's *still* reachable, as information, not
 * as a silent substitute - that's the common case for anyone using the tool
 * after already knowing they need to move soon.
 */
export function bgb573cNoticeDeadline(
  targetEndMonth: string,
  countryCode: string,
  regionCode: string | undefined,
  today: string,
): NoticeDeadlineResult {
  const derivation: DerivationStep[] = [];
  const region = regionCode ? `${countryCode}-${regionCode}` : countryCode;
  derivation.push({
    step: "holiday-region",
    label: `Feiertage nach Recht ${region} angenommen (§ 193 BGB stellt auf den Sitz des Vermieters ab, hier vereinfachend der Zielort des Umzugs)`,
  });
  derivation.push({
    step: "target-end-month",
    label: `Angenommenes Mietende: Ende ${monthLabel(targetEndMonth)} (kein Überlappungsmonat eingeplant)`,
    value: targetEndMonth,
  });

  function deadlineFor(endMonth: string) {
    const { year, month0 } = addMonths(endMonth, -2);
    const noticeMonth = monthKey(year, month0);
    const holidays = loadHolidays(year, countryCode, regionCode);
    const result = nthCountingDayOfMonth(year, month0, 3, holidays);
    return { noticeMonth, ...result };
  }

  const natural = deadlineFor(targetEndMonth);
  derivation.push({
    step: "notice-month",
    label: `Kündigung wirkt zum Ablauf des übernächsten Monats - maßgeblicher Monat: ${monthLabel(natural.noticeMonth)}`,
    value: natural.noticeMonth,
  });
  derivation.push({
    step: "raw-third-werktag",
    label: `Dritter Werktag in ${monthLabel(natural.noticeMonth)}: ${formatDate(iso(natural.raw))}`,
    value: iso(natural.raw),
  });
  if (natural.rolled) {
    derivation.push({
      step: "saturday-roll",
      label: `Fällt auf einen Samstag - verschoben auf ${formatDate(iso(natural.date))} (§ 193 BGB)`,
      value: iso(natural.date),
    });
  }

  const naturalIso = iso(natural.date);
  if (naturalIso >= today) {
    return { date: naturalIso, leaseEndMonth: targetEndMonth, derivation, pastDeadline: false, rescue: null };
  }

  // The notice window for the targeted end month is already gone - `date`
  // stays the (past) natural one, still 1:1 with targetEndMonth. Separately,
  // walk forward to find the earliest end month that's still reachable, as
  // an informational suggestion only.
  derivation.push({
    step: "past-deadline",
    label: `Frist für Ende ${monthLabel(targetEndMonth)} bereits verstrichen (${formatDate(naturalIso)} liegt vor heute)`,
  });
  let candidateEndMonth = targetEndMonth;
  let rescue = natural;
  while (iso(rescue.date) < today) {
    const { year, month0 } = addMonths(candidateEndMonth, 1);
    candidateEndMonth = monthKey(year, month0);
    rescue = deadlineFor(candidateEndMonth);
  }
  derivation.push({
    step: "rescue",
    label: `Frühestmögliches Mietende: Ende ${monthLabel(candidateEndMonth)} - Kündigung bis ${formatDate(iso(rescue.date))}`,
    value: iso(rescue.date),
  });

  return {
    date: naturalIso,
    leaseEndMonth: targetEndMonth,
    derivation,
    pastDeadline: true,
    rescue: { date: iso(rescue.date), leaseEndMonth: candidateEndMonth },
  };
}
