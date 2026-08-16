// The Frist in § 573c BGB, which no sequence of add_months and roll steps can
// express: the notice month is derived backwards from the month the tenancy
// should end in, and the cut-off inside that month is the third Werktag, where
// Saturday counts for the counting but not for the landing.
//
// Lives next to wohnung-kuendigen.yaml and is named after it, because that is
// where someone looking for this rule will look. computeSchedule finds it by
// the Frist's id.
import { loadHolidays, nthCountingDayOfMonth } from "../../lib/business-days";
import { endOfMonth, monthKey, shiftMonth } from "../../lib/date";
import { monthAndYear } from "../../lib/date-display";
import { formatDate, toDate, toIso } from "../../lib/format-date";
import type { DerivationStep, FristSolution } from "../../lib/derivation";

export const solve = (
  anchorDate: string,
  countryCode: string,
  regionCode: string | undefined,
  today: string,
  deferMonths: number,
): FristSolution => {
  const { year: ty, month0: tm } = shiftMonth(anchorDate.slice(0, 7), deferMonths);
  const targetEndMonth = monthKey(ty, tm);

  const derivation: DerivationStep[] = [];
  const region = regionCode ? `${countryCode}-${regionCode}` : countryCode;
  derivation.push({
    step: "holiday-region",
    label: `Feiertage nach Recht ${region} angenommen (§ 193 BGB stellt auf den Sitz des Vermieters ab, hier vereinfachend der Zielort des Umzugs)`,
  });
  derivation.push({
    step: "target-end-month",
    label: `Angenommenes Mietende: Ende ${monthAndYear(targetEndMonth)} (${deferMonths > 0
      ? `${deferMonths} Überlappungsmonat eingeplant`
      : "kein Überlappungsmonat eingeplant"
      })`,
    value: targetEndMonth,
  });

  function deadlineFor(endMonth: string) {
    const { year, month0 } = shiftMonth(endMonth, -2);
    const holidays = loadHolidays(year, countryCode, regionCode);
    return {
      noticeMonth: monthKey(year, month0),
      ...nthCountingDayOfMonth(year, month0, 3, holidays),
    };
  }

  const natural = deadlineFor(targetEndMonth);
  derivation.push({
    step: "notice-month",
    label: `Kündigung wirkt zum Ablauf des übernächsten Monats - maßgeblicher Monat: ${monthAndYear(natural.noticeMonth)}`,
    value: natural.noticeMonth,
  });
  derivation.push({
    step: "raw-third-werktag",
    label: `Dritter Werktag in ${monthAndYear(natural.noticeMonth)}: ${formatDate(toIso(natural.raw))}`,
    value: toIso(natural.raw),
  });
  if (natural.rolled) {
    derivation.push({
      step: "saturday-roll",
      label: `Fällt auf einen Samstag - verschoben auf ${formatDate(toIso(natural.date))} (§ 193 BGB)`,
      value: toIso(natural.date),
    });
  }

  const naturalIso = toIso(natural.date);
  let leaseEndMonth = targetEndMonth;
  let rescue: FristSolution["rescue"] = null;
  const pastDeadline = naturalIso < today;

  if (pastDeadline) {
    derivation.push({
      step: "past-deadline",
      label: `Frist für Ende ${monthAndYear(targetEndMonth)} bereits verstrichen (${formatDate(naturalIso)} liegt vor heute)`,
    });
    let candidate = deadlineFor(leaseEndMonth);
    while (toIso(candidate.date) < today) {
      const { year, month0 } = shiftMonth(leaseEndMonth, 1);
      leaseEndMonth = monthKey(year, month0);
      candidate = deadlineFor(leaseEndMonth);
    }
    derivation.push({
      step: "rescue",
      label: `Frühestmögliches Mietende: Ende ${monthAndYear(leaseEndMonth)} - Kündigung bis ${formatDate(toIso(candidate.date))}`,
      value: toIso(candidate.date),
    });
    rescue = {
      date: toIso(candidate.date),
      label: `Mietende dann Ende ${monthAndYear(leaseEndMonth)}`,
    };
  }

  const lastDay = endOfMonth(leaseEndMonth);
  return {
    date: naturalIso,
    derivation,
    pastDeadline,
    rescue,
    leaseEnd: {
      date: lastDay,
      overlapDays: Math.round(
        (toDate(lastDay).getTime() - toDate(anchorDate).getTime()) / 86400000,
      ),
    },
  };
};
