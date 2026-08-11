import type { Holiday } from "./holidays";

interface OptimalWindow {
  from: string;
  to: string;
  requiredVacationDays: number;
  totalDaysOff: number;
  efficiency: number;
}

function isOff(dateIso: string, holidaySet: Set<string>): boolean {
  const dow = new Date(`${dateIso}T00:00:00Z`).getUTCDay();
  if (dow === 0 || dow === 6) return true;
  return holidaySet.has(dateIso);
}

function addDays(dateIso: string, n: number): string {
  const d = new Date(`${dateIso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function daysBetween(fromIso: string, toIso: string): number {
  return (Date.parse(toIso) - Date.parse(fromIso)) / 86_400_000 + 1;
}

export function calculateOptimalWindows(
  year: number,
  holidays: Holiday[],
  maxVacationDays = 4,
): OptimalWindow[] {
  const holidaySet = new Set(holidays.map((f) => f.date));
  const yearStart = `${year}-01-01`;
  const yearEnd = `${year}-12-31`;
  const results: OptimalWindow[] = [];

  let cursor = yearStart;
  while (cursor <= yearEnd) {
    if (isOff(cursor, holidaySet)) {
      cursor = addDays(cursor, 1);
      continue;
    }

    let blockEnd = cursor;
    while (addDays(blockEnd, 1) <= yearEnd && !isOff(addDays(blockEnd, 1), holidaySet)) {
      blockEnd = addDays(blockEnd, 1);
    }
    const requiredVacationDays = daysBetween(cursor, blockEnd);

    if (requiredVacationDays <= maxVacationDays) {
      let from = cursor;
      while (from > yearStart && isOff(addDays(from, -1), holidaySet)) {
        from = addDays(from, -1);
      }
      let to = blockEnd;
      while (to < yearEnd && isOff(addDays(to, 1), holidaySet)) {
        to = addDays(to, 1);
      }

      if (from < cursor && to > blockEnd) {
        const totalDaysOff = daysBetween(from, to);
        results.push({
          from,
          to,
          requiredVacationDays,
          totalDaysOff,
          efficiency: Math.round((totalDaysOff / requiredVacationDays) * 100) / 100,
        });
      }
    }
    cursor = addDays(blockEnd, 1);
  }

  return results.sort((a, b) => b.efficiency - a.efficiency);
}

