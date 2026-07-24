// ICS generator (RFC 5545), platform-neutral. Uses only all-day events
// (VALUE=DATE), because time windows are always full days.

export interface IcsEvent {
  uid: string;
  from: string; // ISO date YYYY-MM-DD, inclusive
  to: string; // ISO date YYYY-MM-DD, inclusive (last full day)
  title: string;
  description?: string;
  url?: string;
}

// ponytail: a minute-resolution window ("YYYY-MM-DDTHH:MM", see lib/date.ts)
// is truncated to its day here - VALUE=DATE all-day events, as the header
// says. Passing the clock time through would emit "VALUE=DATE:20260501T0630",
// which is malformed RFC 5545. Emit a timed VEVENT instead once a source
// actually needs the time in the feed.
function toIcsDate(iso: string): string {
  return iso.slice(0, 10).replaceAll("-", "");
}

function addDay(iso: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function escapeText(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
}

// ponytail: folds by character count instead of exact UTF-8 octet count
// (RFC 5545) - fine for the short German texts here, a very long
// description with many umlauts could push a line past 75 octets.
function foldLine(line: string): string {
  const limit = 74;
  if (line.length <= limit) return line;
  let result = line.slice(0, limit);
  let rest = line.slice(limit);
  while (rest.length > 0) {
    result += `\r\n ${rest.slice(0, limit - 1)}`;
    rest = rest.slice(limit - 1);
  }
  return result;
}

export function generateIcs(events: IcsEvent[], calendarName: string): string {
  const dtstamp = `${new Date().toISOString().replace(/[-:]/g, "").slice(0, 15)}Z`;
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//wann//urlaubsfenster//DE",
    "CALSCALE:GREGORIAN",
    `X-WR-CALNAME:${escapeText(calendarName)}`,
  ];
  for (const e of events) {
    lines.push(
      "BEGIN:VEVENT",
      `UID:${e.uid}`,
      `DTSTAMP:${dtstamp}`,
      `DTSTART;VALUE=DATE:${toIcsDate(e.from)}`,
      `DTEND;VALUE=DATE:${toIcsDate(addDay(e.to))}`,
      `SUMMARY:${escapeText(e.title)}`,
    );
    if (e.description) lines.push(`DESCRIPTION:${escapeText(e.description)}`);
    if (e.url) lines.push(`URL:${e.url}`);
    lines.push("END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return `${lines.map(foldLine).join("\r\n")}\r\n`;
}
