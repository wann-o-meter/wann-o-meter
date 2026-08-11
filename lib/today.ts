export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function isPast(date: string): boolean {
  return date < isoToday();
}
