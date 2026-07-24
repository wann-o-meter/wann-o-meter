// The string length IS the resolution (see lib/date.ts): a 10-char day gets
// midnight, a 16-char "YYYY-MM-DDTHH:MM" already carries its own clock time.
// Without this split the minute form parses to Invalid Date, and every
// consumer of it silently degrades - getFullYear() returns NaN, so the
// window lands in a NaN year group on its page.
//
// ponytail: a time without an offset is read as UTC, which is what the
// UTC-pinned formatters below already assume, so a window renders exactly
// the clock time its data.yaml says. Sources reporting local wall-clock
// times need a real timezone decision first, not a second guess here.
export function toDate(iso: string): Date {
  return new Date(iso.length > 10 ? `${iso}Z` : `${iso}T00:00:00Z`);
}

export function formatDate(iso: string): string {
  return toDate(iso).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function formatDateWithWeekday(iso: string): string {
  const day = toDate(iso).toLocaleDateString("de-DE", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  });
  // Only the minute form has a clock time to show. Sliced off the source
  // string rather than re-formatted, so what a page shows is literally what
  // its data.yaml says - "UTC" is spelled out because that's the one thing a
  // bare "06:30" wouldn't tell a reader (see toDate).
  return iso.length > 10 ? `${day}, ${iso.slice(11, 16)} UTC` : day;
}
