import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core.extraction import (  # noqa: E402
    CHUNK_OVERLAP,
    MAX_TEXT_LENGTH,
    ExtractionError,
    _split_into_chunks,
    extract_dated_events,
    extract_season_windows,
    extract_subjects,
    suggest_tags,
    suggest_title,
    type_slug_from_label,
)
from core.llm import LlmError  # noqa: E402


def test_empty_text_returns_empty_without_calling_llm():
    with patch("core.extraction.call_llm") as mock_call:
        result = extract_dated_events("   ")
    assert result == []
    mock_call.assert_not_called()


def test_text_at_the_limit_is_still_a_single_call():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = "[]"
        result = extract_dated_events("x" * MAX_TEXT_LENGTH)
    assert result == []
    mock_call.assert_called_once()


def test_oversized_text_is_chunked_into_multiple_llm_calls():
    # A festival/event listing page (hundreds of entries) risks the model's
    # own response getting cut off mid-JSON by its output-length limit if
    # sent in one shot - split into chunks instead of refusing outright (see
    # the eclipse.gsfc.nasa.gov solar-eclipse-catalog case this targets).
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = [
            '[{"date": "2026-01-01", "label": "Erstes"}]',
            '[{"date": "2026-06-01", "label": "Zweites"}]',
        ]
        result = extract_dated_events("x" * (MAX_TEXT_LENGTH + 1))

    assert mock_call.call_count == 2
    assert result == [
        {"date": "2026-01-01", "label": "Erstes"},
        {"date": "2026-06-01", "label": "Zweites"},
    ]


def test_on_progress_reports_each_chunk_before_calling_the_llm():
    messages = []
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = ["[]", "[]"]
        extract_dated_events("x" * (MAX_TEXT_LENGTH + 1), on_progress=messages.append)

    assert len(messages) == 2
    assert "chunk 1/2" in messages[0]
    assert "chunk 2/2" in messages[1]
    assert str(MAX_TEXT_LENGTH) in messages[0]  # first chunk is exactly at the limit


def test_on_progress_omits_the_chunk_suffix_for_a_single_chunk():
    messages = []
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = "[]"
        extract_dated_events("short text", on_progress=messages.append)

    assert len(messages) == 1
    assert "chunk" not in messages[0]


def test_duplicate_entries_from_the_overlapping_region_are_deduped():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = [
            '[{"date": "2026-01-01", "label": "Erstes"}]',
            '[{"date": "2026-01-01", "label": "Erstes"}, {"date": "2026-06-01", "label": "Zweites"}]',
        ]
        result = extract_dated_events("x" * (MAX_TEXT_LENGTH + 1))

    assert result == [
        {"date": "2026-01-01", "label": "Erstes"},
        {"date": "2026-06-01", "label": "Zweites"},
    ]


def test_a_single_failing_chunk_raises_and_stops_the_whole_page():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = ["[]", ValueError("boom")]
        with pytest.raises(ExtractionError):
            extract_dated_events("x" * (MAX_TEXT_LENGTH + 1))


class TestSplitIntoChunks:
    def test_text_under_the_limit_is_a_single_chunk(self):
        assert _split_into_chunks("short text", max_length=100) == ["short text"]

    def test_splits_a_long_text_into_multiple_chunks_under_the_limit(self):
        text = "x" * 250
        chunks = _split_into_chunks(text, max_length=100, overlap=20)
        assert len(chunks) > 1
        assert all(len(c) <= 100 for c in chunks)
        assert "".join(chunks).replace("x", "") == ""  # sanity: still all "x"

    def test_consecutive_chunks_overlap_so_a_boundary_word_survives_intact(self):
        # No newlines at all - forces the hard-cut path (no nicer boundary
        # to break on). "BOUNDARY" straddles index 100 (the first chunk's
        # hard cutoff, chars 96-99 fall inside chunk 1, 100-103 outside it)
        # - the next chunk's overlap must still contain it whole.
        text = "a" * 96 + "BOUNDARY" + "b" * 90
        chunks = _split_into_chunks(text, max_length=100, overlap=30)
        assert any("BOUNDARY" in c for c in chunks)

    def test_prefers_a_paragraph_break_over_a_hard_cut(self):
        text = "a" * 90 + "\n\n" + "b" * 90
        chunks = _split_into_chunks(text, max_length=100, overlap=10)
        assert chunks[0] == "a" * 90

    def test_default_overlap_is_generous_enough_for_a_table_row(self):
        assert CHUNK_OVERLAP >= 500


def test_parses_valid_json_array():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"date": "2026-09-06", "label": "Landtagswahl Sachsen-Anhalt"}, '
            '{"date": "2027-01-30", "label": "Bundesversammlung"}]'
        )
        result = extract_dated_events("some bundestag.de wahltermine text")

    assert result == [
        {"date": "2026-09-06", "label": "Landtagswahl Sachsen-Anhalt"},
        {"date": "2027-01-30", "label": "Bundesversammlung"},
    ]


def test_unwraps_markdown_code_fence():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '```json\n[{"date": "2026-01-01", "label": "Neujahr"}]\n```'
        result = extract_dated_events("text")
    assert result == [{"date": "2026-01-01", "label": "Neujahr"}]


def test_invalid_json_raises_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = "not json at all"
        with pytest.raises(ExtractionError, match="not valid JSON"):
            extract_dated_events("text")


def test_non_array_json_raises_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '{"date": "2026-01-01"}'
        with pytest.raises(ExtractionError, match="Expected a JSON array"):
            extract_dated_events("text")


def test_filters_out_malformed_items_without_erroring():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"date": "2026-09-06", "label": "gut"}, '
            '{"date": "irgendwann", "label": "kein echtes Datum"}, '
            '{"date": "2026-01-01"}, '
            '"not even an object"]'
        )
        result = extract_dated_events("text")
    assert result == [{"date": "2026-09-06", "label": "gut"}]


def test_drops_january_first_paired_with_a_season_word_as_a_fabricated_date():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"date": "2026-09-06", "label": "echtes Datum"}, '
            '{"date": "2028-01-01", "label": "Herbst Landtagswahl Niedersachsen"}]'
        )
        result = extract_dated_events("text")
    assert result == [{"date": "2026-09-06", "label": "echtes Datum"}]


def test_keeps_a_genuine_january_first_holiday():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '[{"date": "2026-01-01", "label": "Neujahr"}]'
        result = extract_dated_events("text")
    assert result == [{"date": "2026-01-01", "label": "Neujahr"}]


def test_deduplicates_and_sorts_by_date():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"date": "2027-01-30", "label": "B"}, '
            '{"date": "2026-09-06", "label": "A"}, '
            '{"date": "2027-01-30", "label": "B"}]'
        )
        result = extract_dated_events("text")
    assert result == [
        {"date": "2026-09-06", "label": "A"},
        {"date": "2027-01-30", "label": "B"},
    ]


def test_llm_failure_propagates_as_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = LlmError("ANTHROPIC_API_KEY is not set")
        with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
            extract_dated_events("text")


def test_subjects_empty_text_returns_empty_without_calling_llm():
    with patch("core.extraction.call_llm") as mock_call:
        result = extract_subjects("   ", "hint")
    assert result == []
    mock_call.assert_not_called()


def test_subjects_has_no_length_guard_since_callers_may_send_raw_html():
    # Unlike extract_dated_events, extract_subjects' callers (e.g.
    # core/generic_source.py) may feed raw, undecoded HTML rather than
    # cleaned text, so it's expected to see much larger real inputs for the
    # same content - this asserts oversized text is still attempted.
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = "[]"
        result = extract_subjects("x" * (MAX_TEXT_LENGTH + 1), "hint")
    assert result == []
    mock_call.assert_called_once()


def test_subjects_parses_a_single_subject():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "bw", "name": "Schulferien Baden-Württemberg"}, '
            '"ranges": [{"start": "2028-03-27", "end": "2028-04-08", "label": "Osterferien"}, '
            '{"start": "2028-07-27", "end": "2028-09-09", "label": "Sommerferien"}]}]'
        )
        result = extract_subjects("some schulferien text", "school holidays for BW, year 2028")

    assert result == [
        {
            "subject": {"slug": "bw", "name": "Schulferien Baden-Württemberg"},
            "ranges": [
                {"start": "2028-03-27", "end": "2028-04-08", "label": "Osterferien"},
                {"start": "2028-07-27", "end": "2028-09-09", "label": "Sommerferien"},
            ],
        }
    ]


def test_subjects_splits_a_page_into_multiple_subjects():
    # The actual point of extract_subjects: one page (e.g. all 16
    # Bundeslaender on one KMK page) becomes multiple subjects in one call,
    # instead of a caller having to already know the enumeration in advance
    # and invoke extraction once per value.
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "bw", "name": "Schulferien Baden-Württemberg"}, '
            '"ranges": [{"start": "2028-03-27", "end": "2028-04-08", "label": "Osterferien"}]}, '
            '{"subject": {"slug": "by", "name": "Schulferien Bayern"}, '
            '"ranges": [{"start": "2028-04-03", "end": "2028-04-15", "label": "Osterferien"}]}]'
        )
        result = extract_subjects("bw and by holiday tables", "hint")

    assert [s["subject"]["slug"] for s in result] == ["bw", "by"]


def test_subjects_filters_out_items_missing_subject_slug_or_name():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "bw", "name": "Schulferien Baden-Württemberg"}, "ranges": []}, '
            '{"subject": {"slug": "", "name": "Missing slug"}, "ranges": []}, '
            '{"subject": {"name": "No slug key"}, "ranges": []}, '
            '{"ranges": []}, '
            '"not even an object"]'
        )
        result = extract_subjects("text", "hint")
    assert [s["subject"]["slug"] for s in result] == ["bw"]


def test_subjects_validates_ranges_per_subject():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "bw", "name": "BW"}, "ranges": ['
            '{"start": "2028-03-27", "end": "2028-04-08", "label": "gut"}, '
            '{"start": "2028-04-08", "end": "2028-03-27", "label": "Ende vor Anfang"}, '
            '{"start": "irgendwann", "end": "2028-04-08", "label": "kein echtes Datum"}]}]'
        )
        result = extract_subjects("text", "hint")
    assert result == [
        {
            "subject": {"slug": "bw", "name": "BW"},
            "ranges": [{"start": "2028-03-27", "end": "2028-04-08", "label": "gut"}],
        }
    ]


def test_subjects_llm_failure_propagates_as_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = LlmError("ANTHROPIC_API_KEY is not set")
        with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
            extract_subjects("text", "hint")


def test_season_windows_empty_text_returns_empty_without_calling_llm():
    with patch("core.extraction.call_llm") as mock_call:
        result = extract_season_windows("   ", "hint")
    assert result == []
    mock_call.assert_not_called()


def test_season_windows_parses_month_only_ranges_per_subject():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "apfel", "name": "Apfel"}, "windows": ['
            '{"type": "main_season", "name": "Hauptsaison", "from": "--05", "to": "--08"}, '
            '{"type": "peak_season", "name": "Spitzensaison", "from": "--06", "to": "--07"}]}, '
            '{"subject": {"slug": "aprikosen", "name": "Aprikosen"}, "windows": ['
            '{"type": "peak_season", "name": "Spitzensaison", "from": "--06", "to": "--08"}]}]'
        )
        result = extract_season_windows(
            "Aepfel: 5-8 orange, Rest gruen. Aprikosen: nur 6-8 orange hervorgehoben, Rest grau.",
            "hint",
        )

    assert result == [
        {
            "subject": {"slug": "apfel", "name": "Apfel"},
            "windows": [
                {"type": "main_season", "name": "Hauptsaison", "from": "--05", "to": "--08"},
                {"type": "peak_season", "name": "Spitzensaison", "from": "--06", "to": "--07"},
            ],
        },
        {
            "subject": {"slug": "aprikosen", "name": "Aprikosen"},
            "windows": [{"type": "peak_season", "name": "Spitzensaison", "from": "--06", "to": "--08"}],
        },
    ]


def test_season_windows_allows_a_window_spanning_the_year_boundary():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "gruenkohl", "name": "Gruenkohl"}, "windows": ['
            '{"type": "main_season", "name": "Hauptsaison", "from": "--11", "to": "--02"}]}]'
        )
        result = extract_season_windows("Gruenkohl: 11-12 und 1-2 gruen hervorgehoben", "hint")

    assert result[0]["windows"] == [{"type": "main_season", "name": "Hauptsaison", "from": "--11", "to": "--02"}]


def test_season_windows_rejects_dated_or_malformed_ranges():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "apfel", "name": "Apfel"}, "windows": ['
            '{"type": "main_season", "name": "gut", "from": "--05", "to": "--08"}, '
            '{"type": "hat_jahr", "name": "hat ein Jahr, ungueltig", "from": "2028-05-01", "to": "--08"}, '
            '{"type": "ungueltiger_monat", "name": "Monat 13 ungueltig", "from": "--13", "to": "--08"}, '
            '{"type": "", "name": "kein type", "from": "--05", "to": "--08"}]}]'
        )
        result = extract_season_windows("text", "hint")

    assert result[0]["windows"] == [{"type": "main_season", "name": "gut", "from": "--05", "to": "--08"}]


def test_season_windows_filters_out_items_missing_subject_slug_or_name():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"subject": {"slug": "apfel", "name": "Apfel"}, "windows": []}, '
            '{"subject": {"slug": "", "name": "Missing slug"}, "windows": []}, '
            '{"windows": []}, '
            '"not even an object"]'
        )
        result = extract_season_windows("text", "hint")
    assert [s["subject"]["slug"] for s in result] == ["apfel"]


def test_season_windows_llm_failure_propagates_as_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = LlmError("ANTHROPIC_API_KEY is not set")
        with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
            extract_season_windows("text", "hint")


def test_type_slug_from_label_maps_known_german_holiday_keywords():
    assert type_slug_from_label("Weihnachtsferien") == "school_holidays-christmas"
    assert type_slug_from_label("Osterferien") == "school_holidays-easter"
    assert type_slug_from_label("Pfingstferien") == "school_holidays-whitsun"
    assert type_slug_from_label("Sommerferien") == "school_holidays-summer"
    assert type_slug_from_label("Herbstferien") == "school_holidays-autumn"
    assert type_slug_from_label("Winterferien") == "school_holidays-winter"


def test_type_slug_from_label_falls_back_to_a_generic_slug():
    assert type_slug_from_label("Beweglicher Ferientag") == "beweglicher-ferientag"


def test_tags_empty_text_returns_empty_without_calling_llm():
    with patch("core.extraction.call_llm") as mock_call:
        result = suggest_tags("   ", "title", ["religion"])
    assert result == []
    mock_call.assert_not_called()


def test_tags_parses_valid_json_array():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '["religion", "islam"]'
        result = suggest_tags("some islamic calendar text", "Islamische Feiertage", ["religion"])
    assert result == ["religion", "islam"]


def test_tags_lowercases_and_deduplicates():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '["Religion", "religion", "Islam"]'
        result = suggest_tags("text", "title", [])
    assert result == ["religion", "islam"]


def test_tags_caps_at_max_tags():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '["a", "b", "c", "d", "e", "f"]'
        result = suggest_tags("text", "title", [], max_tags=3)
    assert result == ["a", "b", "c"]


def test_tags_unwraps_markdown_code_fence():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '```json\n["astronomie"]\n```'
        result = suggest_tags("text", "title", [])
    assert result == ["astronomie"]


def test_tags_invalid_json_raises_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = "not json at all"
        with pytest.raises(ExtractionError, match="not valid JSON"):
            suggest_tags("text", "title", [])


def test_tags_llm_failure_propagates_as_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = LlmError("ANTHROPIC_API_KEY is not set")
        with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
            suggest_tags("text", "title", [])


def test_title_empty_raw_title_returns_empty_without_calling_llm():
    with patch("core.extraction.call_llm") as mock_call:
        result = suggest_title("some text", "   ")
    assert result == ""
    mock_call.assert_not_called()


def test_title_strips_years_and_duplicated_site_name():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = "Islamische Feiertage"
        result = suggest_title(
            "text",
            "Islamische Feiertage 2026 - 2029 - Islamisches Zentrum MünchenIslamisches Zentrum München",
        )
    assert result == "Islamische Feiertage"


def test_title_strips_surrounding_quotes():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '"Islamische Feiertage"'
        result = suggest_title("text", "raw title")
    assert result == "Islamische Feiertage"


def test_title_llm_failure_propagates_as_extraction_error():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = LlmError("ANTHROPIC_API_KEY is not set")
        with pytest.raises(ExtractionError, match="ANTHROPIC_API_KEY"):
            suggest_title("text", "raw title")


def test_multi_day_span_is_one_event_with_an_inclusive_end():
    # "19. September bis 4. Oktober 2026" (Oktoberfest, wiesnkini.de) is one
    # window, not two point dates - `to` is the last day, inclusive.
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = '[{"date": "2026-09-19", "end": "2026-10-04", "label": "Oktoberfest"}]'
        result = extract_dated_events("19. September bis 4. Oktober 2026")

    assert result == [{"date": "2026-09-19", "end": "2026-10-04", "label": "Oktoberfest"}]


def test_inverted_or_malformed_end_drops_the_span_but_keeps_the_date():
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.return_value = (
            '[{"date": "2026-09-19", "end": "2026-09-01", "label": "Rueckwaerts"},'
            ' {"date": "2026-10-01", "end": "irgendwann", "label": "Unfug"}]'
        )
        result = extract_dated_events("...")

    assert result == [
        {"date": "2026-09-19", "label": "Rueckwaerts"},
        {"date": "2026-10-01", "label": "Unfug"},
    ]


def test_span_seen_start_only_by_the_overlapping_chunk_does_not_duplicate():
    # CHUNK_OVERLAP is 1000 chars, so a span wider than the overlap can be
    # whole in one chunk and start-only in the next. Without the longest-span
    # dedup that left both the range and a spurious single-day window.
    with patch("core.extraction.call_llm") as mock_call:
        mock_call.side_effect = [
            '[{"date": "2026-09-19", "end": "2026-10-04", "label": "Oktoberfest"}]',
            '[{"date": "2026-09-19", "label": "Oktoberfest"}]',
        ]
        result = extract_dated_events("x" * (MAX_TEXT_LENGTH + 1))

    assert result == [{"date": "2026-09-19", "end": "2026-10-04", "label": "Oktoberfest"}]
