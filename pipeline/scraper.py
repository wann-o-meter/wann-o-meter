#!/usr/bin/env python3
"""
Simple web scraper for Wann-Plattform.

Handles more than HTML prose pages - open data portals (e.g. DWD's
opendata.dwd.de) serve directory listings, semicolon/comma-delimited text,
fixed-width legacy exports, and ZIP archives of all of the above. scrape()
fetches raw bytes and dispatches by sniffed content, not by assuming
everything is an article to markdown-ify.

Pipeline: fetch bytes -> sniff kind -> kind-specific extraction.
"""

import csv
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import yaml
from bs4 import BeautifulSoup

from core.fetch import Config, decode_text, fetch, fetch_bytes  # noqa: F401 (fetch/Config re-exported for callers)
from core.llm import LlmError, call_llm_vision


def html_to_markdown(html: str) -> str:
    """
    Convert HTML to clean Markdown.
    For production use: pip install trafilatura  (much better boilerplate removal)
    """
    if not html:
        return ""

    # Remove heavy non-content sections
    for tag in ["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]:
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.IGNORECASE)

    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

    # Headings
    for level in range(6, 0, -1):
        html = re.sub(rf"<h{level}[^>]*>(.*?)</h{level}>", rf"{'#' * level} \1\n\n", html, flags=re.DOTALL | re.IGNORECASE)

    # Links, bold, italic, lists, paragraphs
    html = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"</?(ul|ol)[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<br[^>]*>", "\n", html, flags=re.IGNORECASE)

    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def remove_filler_words(text: str) -> str:
    """Throw away most filler / boilerplate words."""
    if not text:
        return ""

    filler_patterns = [
        r"\b(mehr erfahren|weiterlesen|jetzt anmelden|kontaktieren sie uns)\b",
        r"\b(impressum|datenschutz|datenschutzerklärung|cookie-richtlinie|agb)\b",
        r"\b(menü|navigation|suche|filter|sortieren nach|seite \d+)\b",
        r"\b(vorherige|nächste|zurück zur startseite|home)\b",
        r"\b(folgen sie uns|social media|teilen|drucken|pdf herunterladen)\b",
        r"\b(alle rechte vorbehalten|copyright|\© \d{4})\b",
    ]
    for pattern in filler_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Drop very short / navigation-only lines
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if len(stripped) < 4:
            continue
        if re.match(r"^(home|menü|suche|login|logout|impressum|datenschutz|start)$", stripped, re.IGNORECASE):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r" +", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_dates(text: str) -> List[str]:
    patterns = [
        r"\b(?:0?[1-9]|[12][0-9]|3[01])\.(?:0?[1-9]|1[0-2])\.(?:\d{2})?\d{2}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        # Non-capturing groups throughout - re.findall returns tuples of each
        # capture group instead of the full match when a pattern has groups,
        # which would mix str and tuple entries in `dates` and crash sorted().
        r"\b(?:\d{1,2}\.\s*)?(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(?:\d{4})?\b"
    ]
    dates = []
    for p in patterns:
        dates.extend(re.findall(p, text, re.IGNORECASE))
    return sorted(set(dates))


def extract_time_windows(text: str) -> List[Dict[str, str]]:
    pattern = r"(?:vom\s+)?(\d{1,2}\.\d{1,2}\.\d{4})\s+(?:bis|–|-)\s+(\d{1,2}\.\d{1,2}\.\d{4})"
    return [{"from": m.group(1), "to": m.group(2)} for m in re.finditer(pattern, text, re.IGNORECASE)]


# ---------------------------------------------------------------------------
# Directory listings (Apache/nginx mod_autoindex, e.g. opendata.dwd.de/.../)
# ---------------------------------------------------------------------------

def is_directory_listing(html: str) -> bool:
    """mod_autoindex pages all share the "Index of /path" title convention."""
    title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return bool(title and title.group(1).strip().lower().startswith("index of"))


def parse_directory_listing(html: str) -> List[Dict[str, Any]]:
    """Each entry is one <a href> plus a trailing '<date>  <size>' text node -
    the standard mod_autoindex row shape. '-' size means it's a directory."""
    soup = BeautifulSoup(html, "html.parser")
    pre = soup.find("pre") or soup
    entries = []
    for a in pre.find_all("a", href=True):
        href = a["href"]
        if href in ("../", "/", "?C=N;O=D", "?C=M;O=A"):  # nav links some servers add
            continue
        trailing = str(a.next_sibling or "").strip()
        parts = trailing.rsplit(None, 1)
        modified = parts[0] if len(parts) == 2 else (trailing or None)
        size = parts[1] if len(parts) == 2 else None
        entries.append({
            "name": a.get_text(strip=True) or href,
            "href": href,
            "is_dir": href.endswith("/"),
            "modified": modified,
            "size": None if size in (None, "-") else size,
        })
    return entries


# ---------------------------------------------------------------------------
# Tabular text: delimited (csv/semicolon) and fixed-width legacy exports
# ---------------------------------------------------------------------------

def sniff_delimiter(text: str) -> Optional[str]:
    """Only trust a delimiter if the header row and a data row agree on the
    field count - otherwise a stray semicolon in prose would false-positive."""
    lines = [l for l in text.splitlines() if l.strip()][:5]
    if len(lines) < 2:
        return None
    for delimiter in (";", ",", "\t"):
        counts = {line.count(delimiter) for line in lines}
        if len(counts) == 1 and counts != {0}:
            return delimiter
    return None


def parse_delimited(text: str, delimiter: str, max_rows: int = 50) -> Dict[str, Any]:
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return {"columns": [], "row_count": 0, "rows_preview": []}
    columns = [c.strip() for c in rows[0]]
    data_rows = [dict(zip(columns, (c.strip() for c in r))) for r in rows[1:] if r]
    return {
        "columns": columns,
        "row_count": len(data_rows),
        "rows_preview": data_rows[:max_rows],
    }


def looks_fixed_width(text: str) -> bool:
    """A header line directly followed by a '---- --- ----' ruler line is the
    classic convention for these reports (e.g. DWD station lists)."""
    lines = text.splitlines()
    if len(lines) < 2:
        return False
    return bool(re.fullmatch(r"[-\s]+", lines[1]) and "-" in lines[1])


def parse_fixed_width(text: str, max_rows: int = 50) -> Dict[str, Any]:
    """Best-effort: column widths come from the ruler line under the header.
    Ground truth from opendata.dwd.de: the ruler often describes the HEADER's
    widths, not the actual data rows' widths (DWD's own export is inconsistent
    here), so this can misalign columns. We say so explicitly rather than
    presenting a confident-looking wrong table - callers get the parsed
    attempt AND a raw preview to check by eye."""
    lines = text.splitlines()
    header, ruler = lines[0], lines[1]
    spans = [m.span() for m in re.finditer(r"-+", ruler)]
    columns = [header[s:e].strip() or f"col_{i}" for i, (s, e) in enumerate(spans)]

    data_rows = []
    for line in lines[2:]:
        if not line.strip():
            continue
        values = [line[s:min(e, len(line))].strip() for s, e in spans]
        data_rows.append(dict(zip(columns, values)))

    return {
        "columns": columns,
        "row_count": len(data_rows),
        "rows_preview": data_rows[:max_rows],
        "low_confidence": True,
        "raw_lines_preview": lines[:10],
    }


# ---------------------------------------------------------------------------
# Images: no text to decode, so a vision-capable LLM reads them instead (e.g.
# NASA eclipse-path GIFs whose dates/labels are baked into the map itself).
# ---------------------------------------------------------------------------

_IMAGE_MAGIC = (
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

VISION_SYSTEM_PROMPT = (
    "Du transkribierst Bilder wortgetreu. Das Bild ist die EINZIGE Quelle. "
    "Erfinde, ergaenze oder vervollstaendige NIEMALS Text, Zahlen oder "
    "Datumsangaben aus Hintergrundwissen - auch nicht, wenn du das Motiv "
    "erkennst (z.B. eine bekannte Karte, Grafik oder Tabelle) und glaubst, "
    "den vollstaendigen Inhalt zu kennen. Gib nur wieder, was im Bild "
    "tatsaechlich lesbar abgebildet ist. Ist ein Datum, eine Zahl oder ein "
    "Textabschnitt nicht eindeutig lesbar, schreibe '[nicht lesbar]' an "
    "dieser Stelle statt zu raten oder aus Kontext zu schliessen. Farben und "
    "Hervorhebungen (siehe unten) sind Teil dessen, was tatsaechlich im Bild "
    "steht, und zu beschreiben ist kein Erfinden - beschreibe nur, was du "
    "siehst, nicht was du daraus ueber Bedeutung/Ursache vermutest."
)

VISION_PROMPT = (
    "Transkribiere den sichtbaren Inhalt dieses Bildes auf Deutsch. Gib "
    "insbesondere jeden sichtbaren Text, jede Beschriftung/Legende sowie "
    "alle erkennbaren Datums- und Zeitangaben vollstaendig wieder, statt sie "
    "zusammenzufassen - und nur das, was tatsaechlich im Bild steht. "
    "Enthaelt das Bild eine Tabelle, Leiste oder Aufzaehlung, bei der "
    "einzelne Eintraege (z.B. Monatszahlen 1-12) durch Hintergrundfarbe oder "
    "sonstige visuelle Hervorhebung markiert sind, beschreibe das explizit "
    "und pro Gruppe/Objekt getrennt - z.B. 'Aepfel: 1-4 gruen, 5-8 orange, "
    "9-12 gruen' oder 'Aprikosen: nur 6-8 orange hervorgehoben, Rest grau'. "
    "Diese Hervorhebung traegt oft die eigentliche Information (z.B. "
    "Erntesaison) und darf nicht ausgelassen werden, nur weil sie keine Zahl "
    "oder kein Text im engeren Sinn ist."
)

# Anthropic (the default provider) hard-rejects a base64 image over 5MB;
# OpenAI/Google/Mistral's own caps are all higher, so this one constant
# bounds worst-case request size/cost regardless of configured provider.
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def sniff_image_mime(content: bytes) -> Optional[str]:
    for magic, mime in _IMAGE_MAGIC:
        if content.startswith(magic):
            return mime
    return None


def extract_image(content: bytes, mime_type: str) -> Dict[str, Any]:
    """Same result shape as the html_page branch (dates/time_windows/
    clean_markdown_full) so downstream LLM date extraction, which reads
    clean_markdown_full, works unchanged regardless of whether the source
    was HTML or an image."""
    if len(content) > MAX_IMAGE_BYTES:
        return {
            "kind": "unsupported_binary",
            "reason": f"image too large for vision extraction ({len(content)} bytes > {MAX_IMAGE_BYTES} cap)",
            "size_bytes": len(content),
        }
    try:
        text = call_llm_vision(content, mime_type, VISION_PROMPT, system=VISION_SYSTEM_PROMPT)
    except LlmError as e:
        return {"kind": "unsupported_binary", "reason": f"vision extraction failed: {e}", "size_bytes": len(content)}
    return {
        "kind": "image_page",
        "dates": extract_dates(text),
        "time_windows": extract_time_windows(text),
        "clean_markdown_preview": text[:1500] + ("..." if len(text) > 1500 else ""),
        "clean_markdown_full": text,
    }


# PDFs get no dedicated text parser: scanned Behoerden-PDFs (no text layer at
# all) are common enough here that a text-extraction path would need a vision
# fallback anyway - so every PDF goes through the one vision pipeline above,
# rasterizing each page to JPEG first (not PNG - a single large-format page,
# e.g. an A3 poster/calendar, renders to a PNG well over MAX_IMAGE_BYTES;
# JPEG's lossy compression keeps the same page comfortably under it). One
# code path instead of two.
PDF_RENDER_DPI = 150

# Every page is one paid vision call - cap so a huge PDF doesn't silently
# fire off dozens of LLM calls.
MAX_PDF_PAGES = 10


def extract_pdf(content: bytes) -> Dict[str, Any]:
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as e:
        return {"kind": "unsupported_binary", "reason": f"PDF could not be opened: {e}", "size_bytes": len(content)}

    try:
        page_count = doc.page_count
        if page_count == 0:
            return {"kind": "unsupported_binary", "reason": "PDF has no pages", "size_bytes": len(content)}

        texts = []
        for page in doc[:MAX_PDF_PAGES]:
            jpg_bytes = page.get_pixmap(dpi=PDF_RENDER_DPI).tobytes("jpg")
            page_result = extract_image(jpg_bytes, "image/jpeg")
            if page_result["kind"] != "image_page":
                return page_result  # propagate vision failure/oversized-page as-is
            texts.append(page_result["clean_markdown_full"])
    finally:
        doc.close()

    text = "\n\n".join(texts).strip()
    truncated = page_count > MAX_PDF_PAGES
    preview = text[:1500] + ("..." if len(text) > 1500 else "")
    if truncated:
        preview += f" (gekuerzt auf die ersten {MAX_PDF_PAGES} von {page_count} Seiten)"

    return {
        "kind": "pdf_document",
        "page_count": page_count,
        "dates": extract_dates(text),
        "time_windows": extract_time_windows(text),
        "clean_markdown_preview": preview,
        "clean_markdown_full": text,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def extract_any(name: str, content: bytes, content_type: str = "") -> Dict[str, Any]:
    """Sniff what `content` actually is and extract accordingly. Used both at
    the top level and recursively for files inside a ZIP."""
    if content[:4] == b"PK\x03\x04" or name.lower().endswith(".zip"):
        return extract_zip(content)

    if content[:4] == b"%PDF":
        return extract_pdf(content)

    # Must run before decode_text: latin-1 decodes any byte sequence, so
    # image bytes would otherwise silently fall through to plain_text as
    # garbled text instead of being recognized as an image.
    image_mime = sniff_image_mime(content)
    if image_mime:
        return extract_image(content, image_mime)

    text = decode_text(content)
    if text is None:
        return {"kind": "unsupported_binary", "reason": "not decodable as text", "size_bytes": len(content)}

    looks_html = bool(re.match(r"\s*<(!doctype html|html)", text, re.IGNORECASE)) or "html" in content_type.lower()
    if looks_html:
        if is_directory_listing(text):
            entries = parse_directory_listing(text)
            return {"kind": "directory_listing", "entry_count": len(entries), "entries": entries}

        md = html_to_markdown(text)
        clean = remove_filler_words(md)
        return {
            "kind": "html_page",
            "dates": extract_dates(clean),
            "time_windows": extract_time_windows(clean),
            "clean_markdown_preview": clean[:1500] + ("..." if len(clean) > 1500 else ""),
            # Full text, not just the preview - needed by LLM extraction
            # (core/llm.py), which can't work from a 1500-char snippet on
            # longer pages. Regex-based extract_dates() above only catches
            # numeric dates (DD.MM.YYYY); pages using written month names
            # with the year given separately (e.g. bundestag.de/parlament/
            # wahlen/wahltermine) come back with dates: [] even though the
            # full text has everything needed - that's the gap LLM
            # extraction fills.
            "clean_markdown_full": clean,
        }

    delimiter = sniff_delimiter(text)
    if delimiter:
        parsed = parse_delimited(text, delimiter)
        return {"kind": "tabular_text", "format": "delimited", "delimiter": delimiter, **parsed}

    if looks_fixed_width(text):
        parsed = parse_fixed_width(text)
        return {"kind": "tabular_text", "format": "fixed_width", **parsed}

    return {"kind": "plain_text", "preview": text[:1500] + ("..." if len(text) > 1500 else "")}


def extract_zip(content: bytes) -> Dict[str, Any]:
    entries = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            try:
                member_bytes = zf.read(info.filename)
                member_result = extract_any(info.filename, member_bytes)
            except Exception as e:
                member_result = {"kind": "error", "reason": str(e)}
            member_result["name"] = info.filename
            member_result["size_bytes"] = info.file_size
            entries.append(member_result)
    return {"kind": "zip_archive", "file_count": len(entries), "entries": entries}


class SimpleScraper:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

    def scrape(self, url: str) -> Dict[str, Any]:
        print(f"[scraper] Fetching {url}")
        content, content_type = fetch_bytes(url, self.config)

        print(f"[scraper] Extracting ({len(content)} bytes, content-type={content_type or 'unknown'})")
        data = extract_any(url, content, content_type)
        data["url"] = url
        data["extracted_at"] = datetime.now().isoformat()
        return data

    def save(self, data: Dict[str, Any], output_path: str) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        print(f"[scraper] Saved to {output_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scraper.py <URL> [output.yaml]")
        sys.exit(1)

    url = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None

    scraper = SimpleScraper()
    result = scraper.scrape(url)

    if output:
        scraper.save(result, output)
    else:
        print(yaml.dump(result, allow_unicode=True, sort_keys=False))
