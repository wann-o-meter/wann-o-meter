import sys
from pathlib import Path
from unittest.mock import patch

import fitz

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from scraper import MAX_PDF_PAGES, extract_any, extract_dates, sniff_image_mime  # noqa: E402


def _pdf_bytes(page_count: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(page_count):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def test_html_page_keeps_full_text_alongside_truncated_preview():
    long_paragraph = "Ein Satz mit Inhalt. " * 200  # well over 1500 chars
    html = f"<html><body><p>{long_paragraph}</p></body></html>".encode("utf-8")

    result = extract_any("page.html", html, "text/html")

    assert result["kind"] == "html_page"
    assert len(result["clean_markdown_full"]) > 1500
    assert result["clean_markdown_preview"].endswith("...")
    assert len(result["clean_markdown_preview"]) <= 1503  # 1500 chars + "..."
    # the preview must be a genuine prefix of the full text, not something else
    assert result["clean_markdown_full"].startswith(result["clean_markdown_preview"][:1500])


def test_html_page_short_content_preview_matches_full_text():
    html = b"<html><body><p>Kurzer Text.</p></body></html>"

    result = extract_any("page.html", html, "text/html")

    assert not result["clean_markdown_preview"].endswith("...")
    assert result["clean_markdown_preview"] == result["clean_markdown_full"]


def test_extract_dates_finds_both_supported_formats():
    text = "Termine: 6.9.2026, 20.09.2026 und im ISO-Format 2027-01-30."
    assert extract_dates(text) == ["20.09.2026", "2027-01-30", "6.9.2026"]


def test_extract_dates_returns_empty_list_when_no_dates_present():
    text = "Diese Seite enthaelt gar keine Datumsangaben, nur Fliesstext."
    assert extract_dates(text) == []


def test_sniff_image_mime_recognizes_gif_png_jpeg():
    assert sniff_image_mime(b"GIF89a\x01\x00\x01\x00") == "image/gif"
    assert sniff_image_mime(b"\x89PNG\r\n\x1a\n\x00\x00") == "image/png"
    assert sniff_image_mime(b"\xff\xd8\xff\xe0\x00\x10") == "image/jpeg"
    assert sniff_image_mime(b"<html></html>") is None


def test_extract_any_routes_gif_to_vision_extraction_not_plain_text():
    gif_bytes = b"GIF89a" + b"\x00" * 20  # not valid UTF-8/Latin-1-meaningful text
    with patch("scraper.call_llm_vision") as mock_vision:
        mock_vision.return_value = "Sonnenfinsternis 2026-08-12, Totalitaet 14:00-14:03 UTC"
        result = extract_any("SE2001-25T-2.GIF", gif_bytes, "image/gif")

    mock_vision.assert_called_once()
    args, _ = mock_vision.call_args
    assert args[0] == gif_bytes
    assert args[1] == "image/gif"
    assert result["kind"] == "image_page"
    assert result["dates"] == ["2026-08-12"]
    assert "Sonnenfinsternis" in result["clean_markdown_full"]


def test_extract_any_gif_falls_back_to_unsupported_binary_on_llm_error():
    from core.llm import LlmError

    gif_bytes = b"GIF89a" + b"\x00" * 20
    with patch("scraper.call_llm_vision", side_effect=LlmError("no API key")):
        result = extract_any("broken.gif", gif_bytes, "image/gif")

    assert result["kind"] == "unsupported_binary"
    assert "vision extraction failed" in result["reason"]


def test_extract_any_rejects_oversized_image_without_calling_vision():
    from scraper import MAX_IMAGE_BYTES

    oversized_gif = b"GIF89a" + b"\x00" * (MAX_IMAGE_BYTES + 1)
    with patch("scraper.call_llm_vision") as mock_vision:
        result = extract_any("huge.gif", oversized_gif, "image/gif")

    mock_vision.assert_not_called()
    assert result["kind"] == "unsupported_binary"
    assert "too large" in result["reason"]


def test_extract_dates_handles_german_month_names_alongside_numeric_dates():
    # Regression test: the month-name pattern used to have capturing groups,
    # so re.findall returned tuples for these matches while the numeric
    # patterns returned plain strings - mixing the two crashed sorted(set(...))
    # with "'<' not supported between instances of 'str' and 'tuple'".
    text = "Feiertage: 6.9.2026, 20. August 2026 und 25 Dezember."
    result = extract_dates(text)
    assert "6.9.2026" in result
    assert any("August" in d for d in result)
    assert any("Dezember" in d for d in result)


def test_extract_any_routes_pdf_page_through_vision_extraction():
    pdf_bytes = _pdf_bytes(page_count=1)
    with patch("scraper.call_llm_vision") as mock_vision:
        mock_vision.return_value = "Sitzungstermin 06.09.2026"
        result = extract_any("termine.pdf", pdf_bytes, "application/pdf")

    mock_vision.assert_called_once()
    assert result["kind"] == "pdf_document"
    assert result["page_count"] == 1
    assert result["dates"] == ["06.09.2026"]
    assert "Sitzungstermin" in result["clean_markdown_full"]


def test_extract_pdf_caps_vision_calls_at_max_pages_and_notes_truncation():
    pdf_bytes = _pdf_bytes(page_count=MAX_PDF_PAGES + 3)
    with patch("scraper.call_llm_vision") as mock_vision:
        mock_vision.return_value = "Seite ohne Datum"
        result = extract_any("huge.pdf", pdf_bytes, "application/pdf")

    assert mock_vision.call_count == MAX_PDF_PAGES
    assert result["page_count"] == MAX_PDF_PAGES + 3
    assert f"ersten {MAX_PDF_PAGES} von {MAX_PDF_PAGES + 3} Seiten" in result["clean_markdown_preview"]


def test_extract_pdf_propagates_oversized_rendered_page_as_unsupported():
    pdf_bytes = _pdf_bytes(page_count=1)
    with patch("scraper.MAX_IMAGE_BYTES", 0), patch("scraper.call_llm_vision") as mock_vision:
        result = extract_any("page.pdf", pdf_bytes, "application/pdf")

    mock_vision.assert_not_called()
    assert result["kind"] == "unsupported_binary"
    assert "too large" in result["reason"]


def test_extract_pdf_broken_file_returns_unsupported_binary_without_crashing():
    result = extract_any("broken.pdf", b"%PDF-1.4\nnot actually a pdf", "application/pdf")

    assert result["kind"] == "unsupported_binary"
    assert "could not be opened" in result["reason"]
