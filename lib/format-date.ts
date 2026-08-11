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
  return iso.length > 10 ? `${day}, ${iso.slice(11, 16)} UTC` : day;
}
