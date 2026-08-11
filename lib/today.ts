/** Today as an ISO day, in the same shape every date in a plan uses. */
export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

/** ISO day strings compare correctly as strings, so no Date is needed. */
export function isPast(date: string): boolean {
  return date < isoToday();
}
