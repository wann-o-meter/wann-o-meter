import { formatDate } from "./format-date";
import { MONTH_NAMES } from "./date-display";
import { loadHolidays, nthCountingDayOfMonth } from "./business-days";

export interface DerivationStep {
  step: string;
  label: string;
  value?: string;
}

interface NoticeDeadlineResult {
  date: string;
  leaseEndMonth: string;
  derivation: DerivationStep[];
  pastDeadline: boolean;
  rescue: { date: string; leaseEndMonth: string; label: string } | null;
}

function iso(d: Date): string {
  return d.toISOString().slice(0, 10);
}
function monthLabel(yyyyMm: string): string {
  const [y, m] = yyyyMm.split("-").map(Number);
  return `${MONTH_NAMES[m - 1]} ${y}`;
}
function addMonths(
  yyyyMm: string,
  n: number,
): { year: number; month0: number } {
  const [y, m] = yyyyMm.split("-").map(Number);
  const total = m - 1 + n;
  const year = y + Math.floor(total / 12);
  const month0 = ((total % 12) + 12) % 12;
  return { year, month0 };
}
function monthKey(year: number, month0: number): string {
  return `${year}-${String(month0 + 1).padStart(2, "0")}`;
}

export function bgb573cNoticeDeadline(
  targetEndMonth: string,
  countryCode: string,
  regionCode: string | undefined,
  today: string,
  deferMonths = 0,
): NoticeDeadlineResult {
  const derivation: DerivationStep[] = [];
  const region = regionCode ? `${countryCode}-${regionCode}` : countryCode;
  derivation.push({
    step: "holiday-region",
    label: `Feiertage nach Recht ${region} angenommen (§ 193 BGB stellt auf den Sitz des Vermieters ab, hier vereinfachend der Zielort des Umzugs)`,
  });
  derivation.push({
    step: "target-end-month",
    label: `Angenommenes Mietende: Ende ${monthLabel(targetEndMonth)} (${deferMonths > 0
        ? `${deferMonths} Überlappungsmonat eingeplant`
        : "kein Überlappungsmonat eingeplant"
      })`,
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
    return {
      date: naturalIso,
      leaseEndMonth: targetEndMonth,
      derivation,
      pastDeadline: false,
      rescue: null,
    };
  }

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
    rescue: {
      date: iso(rescue.date),
      leaseEndMonth: candidateEndMonth,
      label: `Mietende dann Ende ${monthLabel(candidateEndMonth)}`,
    },
  };
}
