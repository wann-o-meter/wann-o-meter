import Holidays from "date-holidays";

// All countries supported by date-holidays (>200) - "every country" literally.
// Names come as delivered by the library (sometimes in the local language) -
// no translation table maintained for >200 entries, that would be its own
// content effort with no data value.
let cache: Record<string, string> | undefined;

export function allCountries(): Record<string, string> {
  if (!cache) cache = new Holidays().getCountries();
  return cache;
}
