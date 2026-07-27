"""ICS -> event/window mapping (Ziel 5 of the pipeline overhaul): a
deterministic extraction path, no LLM call at all. Maps each VEVENT in a
VCALENDAR onto one RawWindow-shaped dict (core/staging.py's candidate
event: shape) - SUMMARY -> name, DTSTART/DTEND -> from/to, LOCATION/
DESCRIPTION/URL -> notes, RRULE -> rrule (stored verbatim, not expanded -
see lib/schema.ts's rrule field docstring, a future generator.ts's job).

Two correctness details that are easy to get wrong and MUST be handled here:

  - DTEND is EXCLUSIVE for an all-day (DATE, not DATE-TIME) VEVENT per
    RFC 5545 - it's the day AFTER the last day. This project's own window
    convention is inclusive `to` (see data/schulferien/bw/data.yaml's
    single-day windows, from == to) - so an all-day DTEND is converted by
    subtracting one day before being written, or every multi-day ICS event
    would land one day too long.
  - A tz-aware DTSTART/DTEND carries no timezone in this project's
    datePartSchema ("YYYY-MM-DDTHH:MM" has no offset) - normalized to
    Europe/Berlin wall-clock time before formatting, not left as UTC or
    whatever the source feed's tzid happened to be.

`year` is always a concrete int (never null): unlike the "--MM" recurring
month-window shape (which year: null is specifically for, see
materializeRawWindow), an ICS VEVENT's from/to are always full dates, and
year: null + a full date is NOT a supported combination in
materializeRawWindow (it would repeat the same fixed date under every
rolling year instead of expanding a rule) - year: null is reserved for the
month-only case. An RRULE captured here doesn't change that; it's just
carried along as inert metadata until a future generator.ts expands it."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from icalendar import Calendar

BERLIN_TZ = ZoneInfo("Europe/Berlin")


def _wall_clock_string(value) -> tuple:
    """Returns (iso_string, is_all_day). A `date` (no time component) is an
    all-day VEVENT; a `datetime` is normalized to Europe/Berlin wall-clock
    before formatting if it carries a timezone."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(BERLIN_TZ).replace(tzinfo=None)
        return value.strftime("%Y-%m-%dT%H:%M"), False
    return value.isoformat(), True


def map_vevent(vevent, type_hint: str = "event") -> dict[str, Any] | None:
    """Maps one icalendar VEVENT component to a RawWindow-shaped dict.
    Returns None if the VEVENT has no DTSTART (malformed, nothing to map)."""
    dtstart_prop = vevent.get("dtstart")
    if dtstart_prop is None:
        return None
    dtstart = dtstart_prop.dt
    from_str, all_day = _wall_clock_string(dtstart)

    dtend_prop = vevent.get("dtend")
    if dtend_prop is not None:
        dtend = dtend_prop.dt
        if all_day:
            dtend = dtend - timedelta(days=1)  # DTEND is exclusive for all-day events
        to_str, _ = _wall_clock_string(dtend)
    else:
        to_str = from_str

    name = str(vevent.get("summary", "")).strip()

    rrule_prop = vevent.get("rrule")
    rrule_str = rrule_prop.to_ical().decode("ascii") if rrule_prop else None

    notes_parts: list[str] = []
    if vevent.get("location"):
        notes_parts.append(f"Ort: {vevent.get('location')}")
    if vevent.get("description"):
        notes_parts.append(str(vevent.get("description")).strip())
    if vevent.get("url"):
        notes_parts.append(str(vevent.get("url")))

    window: dict[str, Any] = {
        "type": type_hint,
        "year": dtstart.year,
        "from": from_str,
        "to": to_str,
        "precision": "exact",
        "ics": True,
        "name": name,
    }
    if rrule_str:
        window["rrule"] = rrule_str
    if notes_parts:
        window["notes"] = "\n".join(notes_parts)
    return window


def map_calendar(raw: bytes, type_hint: str = "event") -> list[dict[str, Any]]:
    """Parses a VCALENDAR's bytes and maps every VEVENT it contains.
    Malformed VEVENTs (no DTSTART) are skipped, not fatal - one bad entry
    in a feed shouldn't drop every other real event."""
    calendar = Calendar.from_ical(raw)
    windows = []
    for component in calendar.walk("VEVENT"):
        window = map_vevent(component, type_hint)
        if window is not None:
            windows.append(window)
    return windows
