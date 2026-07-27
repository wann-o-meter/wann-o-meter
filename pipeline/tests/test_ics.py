import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core.ics import map_calendar, map_vevent  # noqa: E402
from core.sniff import extract_any  # noqa: E402


def _calendar(*vevents: str) -> bytes:
    body = "\n".join(vevents)
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
        f"{body}\r\nEND:VCALENDAR\r\n"
    ).encode("utf-8")


def _vevent(**fields) -> str:
    lines = ["BEGIN:VEVENT", "UID:test-1@example.org"]
    for key, value in fields.items():
        lines.append(f"{key}:{value}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def test_maps_a_simple_timed_event():
    raw = _calendar(_vevent(SUMMARY="Stadtfest", DTSTART="20260815T180000", DTEND="20260815T220000"))
    windows = map_calendar(raw)

    assert len(windows) == 1
    w = windows[0]
    assert w["name"] == "Stadtfest"
    assert w["year"] == 2026
    assert w["from"] == "2026-08-15T18:00"
    assert w["to"] == "2026-08-15T22:00"
    assert w["precision"] == "exact"
    assert w["ics"] is True


def test_all_day_event_dtend_is_exclusive_converted_to_inclusive_to():
    # A 3-day all-day event (15th-17th inclusive) has DTEND=18th per RFC
    # 5545 (exclusive) - the mapped `to` must be the 17th, not the 18th.
    raw = _calendar(_vevent(SUMMARY="Stadtfest", DTSTART="20260815", DTEND="20260818"))
    windows = map_calendar(raw)

    assert windows[0]["from"] == "2026-08-15"
    assert windows[0]["to"] == "2026-08-17"


def test_single_day_all_day_event_has_matching_from_and_to():
    raw = _calendar(_vevent(SUMMARY="Feiertag", DTSTART="20260815", DTEND="20260816"))
    windows = map_calendar(raw)

    assert windows[0]["from"] == windows[0]["to"] == "2026-08-15"


def test_missing_dtend_falls_back_to_dtstart():
    raw = _calendar(_vevent(SUMMARY="Punkttermin", DTSTART="20260815T090000"))
    windows = map_calendar(raw)

    assert windows[0]["from"] == windows[0]["to"] == "2026-08-15T09:00"


def test_utc_datetime_is_normalized_to_europe_berlin_wall_clock():
    # 2026-08-15 18:00 UTC is 20:00 in Berlin (CEST, UTC+2 in August).
    raw = _calendar(_vevent(SUMMARY="Webinar", DTSTART="20260815T180000Z"))
    windows = map_calendar(raw)

    assert windows[0]["from"] == "2026-08-15T20:00"
    assert "Z" not in windows[0]["from"]
    assert "+" not in windows[0]["from"]


def test_rrule_is_preserved_verbatim():
    raw = _calendar(
        _vevent(SUMMARY="Wochenmarkt", DTSTART="20260801", DTEND="20260802", RRULE="FREQ=WEEKLY;BYDAY=SA")
    )
    windows = map_calendar(raw)

    assert windows[0]["rrule"] == "FREQ=WEEKLY;BYDAY=SA"


def test_event_without_rrule_has_no_rrule_key():
    raw = _calendar(_vevent(SUMMARY="Einmalig", DTSTART="20260801", DTEND="20260802"))
    windows = map_calendar(raw)

    assert "rrule" not in windows[0]


def test_location_and_description_and_url_combine_into_notes():
    raw = _calendar(
        _vevent(
            SUMMARY="Stadtfest",
            DTSTART="20260815",
            DTEND="20260816",
            LOCATION="Marktplatz Hechingen",
            DESCRIPTION="Musik und Essen",
            URL="https://example.org/stadtfest",
        )
    )
    windows = map_calendar(raw)

    notes = windows[0]["notes"]
    assert "Marktplatz Hechingen" in notes
    assert "Musik und Essen" in notes
    assert "https://example.org/stadtfest" in notes


def test_multiple_vevents_all_get_mapped():
    raw = _calendar(
        _vevent(SUMMARY="Erstes", DTSTART="20260815", DTEND="20260816"),
        _vevent(SUMMARY="Zweites", DTSTART="20260901", DTEND="20260902"),
    )
    windows = map_calendar(raw)

    assert [w["name"] for w in windows] == ["Erstes", "Zweites"]


def test_vevent_without_dtstart_is_skipped_not_fatal():
    calendar_text = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:broken@example.org\r\nSUMMARY:Kaputt\r\nEND:VEVENT\r\n"
        f"{_vevent(SUMMARY='Gut', DTSTART='20260815', DTEND='20260816')}\r\n"
        "END:VCALENDAR\r\n"
    ).encode("utf-8")

    windows = map_calendar(calendar_text)

    assert [w["name"] for w in windows] == ["Gut"]


def test_type_hint_is_used_as_the_window_type():
    raw = _calendar(_vevent(SUMMARY="Markt", DTSTART="20260815", DTEND="20260816"))
    windows = map_calendar(raw, type_hint="market")

    assert windows[0]["type"] == "market"


class TestExtractAnyDispatch:
    def test_routes_text_calendar_content_type_to_ics(self):
        raw = _calendar(_vevent(SUMMARY="Stadtfest", DTSTART="20260815", DTEND="20260816"))
        result = extract_any("feed", raw, "text/calendar")

        assert result["kind"] == "ics_feed"
        assert result["event_count"] == 1
        assert result["windows"][0]["name"] == "Stadtfest"

    def test_routes_ics_file_extension_to_ics_even_without_content_type(self):
        raw = _calendar(_vevent(SUMMARY="Stadtfest", DTSTART="20260815", DTEND="20260816"))
        result = extract_any("events.ics", raw, "")

        assert result["kind"] == "ics_feed"

    def test_routes_by_vcalendar_magic_bytes_alone(self):
        raw = _calendar(_vevent(SUMMARY="Stadtfest", DTSTART="20260815", DTEND="20260816"))
        result = extract_any("unnamed", raw, "")

        assert result["kind"] == "ics_feed"

    def test_malformed_ics_returns_unsupported_binary_not_a_crash(self):
        result = extract_any("events.ics", b"BEGIN:VCALENDAR\r\nnot actually valid\r\n", "")

        assert result["kind"] == "unsupported_binary"
        assert "ICS parsing failed" in result["reason"]
