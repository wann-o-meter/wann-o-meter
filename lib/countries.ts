import Holidays from "date-holidays";

let cache: Record<string, string> | undefined;

export function allCountries(): Record<string, string> {
  if (!cache) cache = new Holidays().getCountries();
  return cache;
}
