"""LLM-based date/event extraction for pages the deterministic scraper
can't fully handle - e.g. bundestag.de/parlament/wahlen/wahltermine, where
dates are written as day + month name ("6. September") with the year given
only as a separate table heading above the row, not attached to each date at
all. A regex over flattened text can't reconstruct that association; an LLM
reading the surrounding context can.

extract_subjects additionally handles pages that cover MORE THAN ONE subject
in a single fetch (school holidays for all 16 Bundeslaender, produce seasons
for several fruits/vegetables, ...) - the model discovers the split from the
actual content, guided only by a caller-supplied hint, instead of a
per-source Python module enumerating the subjects in advance.

Deliberately narrow: find calendar-relevant dates/spans and what each one
means, not a general-purpose extraction framework."""

import json
import re
from typing import Any, Dict, List

from core.llm import call_llm

SYSTEM_PROMPT = (
    "Du extrahierst Kalenderdaten aus Webseiten-Text, der in JEDER Sprache vorliegen kann. "
    "Antworte AUSSCHLIESSLICH mit einem JSON-Array, keine Erklaerung, kein Markdown, "
    "kein Codeblock. Jedes Element hat genau die Felder "
    '{"date": "YYYY-MM-DD", "label": "kurze Beschreibung"}. '
    "Das 'label' ist IMMER auf Deutsch, auch wenn der Quelltext in einer anderen Sprache "
    "ist - uebersetze insbesondere Ereignis- und Feiertagsnamen (z.B. 'Solar Eclipse' -> "
    "'Sonnenfinsternis', 'Good Friday' -> 'Karfreitag'), nicht nur woertlich uebernehmen. "
    "Loese relative/implizite Jahresangaben auf (z.B. eine Jahreszahl als Tabellen-"
    "ueberschrift, die fuer mehrere darunterliegende Zeilen gilt). "
    "Ueberspringe JEDEN Eintrag, der keinen konkreten Tag nennt (z.B. nur 'Herbst 2028' "
    "oder nur eine Jahreszahl ohne Tag/Monat) - lass ihn komplett aus der Antwort weg. "
    "Erfinde NIEMALS einen Tag oder Monat, den der Text nicht explizit nennt - insbesondere "
    "ist '01' als Platzhalter-Tag/Monat (z.B. \"2028-01-01\" fuer einen Eintrag, der nur "
    "'2028' oder 'Herbst 2028' sagt) IMMER falsch. Der gegebene Text ist die EINZIGE Quelle: "
    "ergaenze KEIN Ereignis und KEIN Datum aus Hintergrundwissen, selbst wenn du das Thema "
    "erkennst (z.B. bekannte Feiertage, Ereignisse oder ein Datumsmuster) und glaubst, "
    "weitere Termine zu kennen, die im Text nicht stehen. Im Zweifel: Eintrag weglassen "
    "statt raten oder ergaenzen."
)


class ExtractionError(Exception):
    pass


# Single-shot prompt/response, no chunking - a huge page (a festival/event
# listing with hundreds of entries, not the "one page, one topic" case this
# module targets, see the module docstring) risks the model's response
# itself getting cut off mid-JSON by ITS OWN output-length limit, which then
# fails to parse - a confusing failure after a slow (up to
# REQUEST_TIMEOUT_SECONDS) round trip that looks like nothing happened. Fail
# fast with a clear reason instead of attempting it.
MAX_TEXT_LENGTH = 20_000


def _check_length(text: str) -> None:
    if len(text) > MAX_TEXT_LENGTH:
        raise ExtractionError(
            f"Page text is too large for single-shot LLM extraction "
            f"({len(text)} chars, max {MAX_TEXT_LENGTH}) - likely a listing/index "
            "page with many entries rather than a single topic; not attempted."
        )


_VAGUE_SEASON_WORDS = ("frühjahr", "fruehjahr", "sommer", "herbst", "winter")


def _parse_json_array(raw: str) -> List[Dict[str, Any]]:
    """Models sometimes wrap JSON in ```json ... ``` despite instructions not
    to - strip that before parsing rather than failing on it."""
    text = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Model response was not valid JSON: {e}\nResponse: {raw[:500]}") from e
    if not isinstance(data, list):
        raise ExtractionError(f"Expected a JSON array, got {type(data).__name__}")
    return data


def extract_dated_events(text: str) -> List[Dict[str, str]]:
    """Returns a list of {"date": "YYYY-MM-DD", "label": str}, validated and
    de-duplicated. Raises ExtractionError (missing config, API failure,
    unparseable response) rather than returning empty/fabricated data on
    failure - callers must surface that to the operator."""
    if not text.strip():
        return []
    _check_length(text)

    prompt = f"Text:\n\n{text}\n\nExtrahiere alle Kalenderdaten als JSON-Array."
    try:
        raw = call_llm(prompt, system=SYSTEM_PROMPT)
    except Exception as e:
        raise ExtractionError(str(e)) from e

    items = _parse_json_array(raw)

    events = []
    seen = set()
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for item in items:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date", "")).strip()
        label = str(item.get("label", "")).strip()
        if not date_pattern.match(date) or not label:
            continue
        # Despite explicit instructions not to, models reliably fabricate
        # "01-01" as a placeholder day/month for entries that only give a
        # season+year ("Herbst 2028" -> "2028-01-01", with "Herbst" still
        # showing up in the label) - verified against bundestag.de/
        # wahltermine, reproduced with temperature=0 too, so this isn't a
        # sampling-randomness issue. Scoped to the season-word tell rather
        # than dropping every 01-01 outright, since e.g. "Neujahr" (New
        # Year's Day) is a real, common Jan-1st holiday.
        if date.endswith("-01-01") and any(season in label.lower() for season in _VAGUE_SEASON_WORDS):
            continue
        key = (date, label)
        if key in seen:
            continue
        seen.add(key)
        events.append({"date": date, "label": label})

    return sorted(events, key=lambda e: e["date"])

TAGS_SYSTEM_PROMPT = (
    "Du schlaegst Tags fuer eine Wann-Frage-Seite vor. Titel und Text koennen in "
    "JEDER Sprache vorliegen - die Tags sind aber IMMER kurze, kleingeschriebene "
    "deutsche Substantive (z.B. \"religion\", \"sport\"), auch wenn der Quelltext in "
    "einer anderen Sprache ist. Antworte AUSSCHLIESSLICH mit einem JSON-Array aus "
    "solchen Substantiven, keine Erklaerung, kein Markdown, kein Codeblock. "
    "Bevorzuge IMMER einen der 'Bereits verwendete Tags' unten, wenn einer davon "
    "thematisch passt - erfinde nur dann ein neues Tag, wenn wirklich keines der "
    "vorhandenen passt. Hoechstens {max_tags} Tags, weniger wenn nicht so viele "
    "wirklich passen."
)


def suggest_tags(text: str, title: str, existing_tags: List[str], max_tags: int = 5) -> List[str]:
    """Suggests up to `max_tags` tags for a page, preferring reuse of
    `existing_tags` (the site's current tag vocabulary) over inventing new
    ones - keeps the tag set from fragmenting into near-duplicates
    ("feiertag" vs "feiertage") the way free-typed tags would. Raises
    ExtractionError rather than silently returning [] on failure, same as
    the other extract_*/suggest_* functions here."""
    if not text.strip():
        return []

    system = TAGS_SYSTEM_PROMPT.format(max_tags=max_tags)
    tag_list = ", ".join(existing_tags) if existing_tags else "(noch keine)"
    prompt = (
        f"Titel: {title}\n\n"
        f"Bereits verwendete Tags: {tag_list}\n\n"
        f"Text:\n\n{text[:3000]}\n\n"
        "Schlage passende Tags als JSON-Array vor."
    )
    try:
        raw = call_llm(prompt, system=system)
    except Exception as e:
        raise ExtractionError(str(e)) from e

    text_stripped = raw.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text_stripped, re.DOTALL)
    if fenced:
        text_stripped = fenced.group(1)
    try:
        data = json.loads(text_stripped)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Model response was not valid JSON: {e}\nResponse: {raw[:500]}") from e
    if not isinstance(data, list):
        raise ExtractionError(f"Expected a JSON array, got {type(data).__name__}")

    tags = []
    seen = set()
    for item in data:
        tag = str(item).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tags[:max_tags]


TITLE_SYSTEM_PROMPT = (
    "Du bereinigst den Titel fuer eine Wann-Frage-Seite (z.B. 'Islamische Feiertage', "
    "'Schulferien Bayern'). Der rohe Titel kommt unbearbeitet aus dem <title>-Tag der "
    "gescrapten Seite und enthaelt oft Muell: Jahreszahlen/Jahresspannen, Organisations- "
    "oder Websitenamen, Trennzeichen wie '-' oder '|', und manchmal denselben Namen "
    "versehentlich doppelt. Antworte AUSSCHLIESSLICH mit dem bereinigten Titel als "
    "Klartext - keine Anfuehrungszeichen, kein Markdown, keine Erklaerung. Der bereinigte "
    "Titel nennt NUR das eigentliche Thema (z.B. 'Islamische Feiertage'), OHNE Jahreszahlen, "
    "Datumsspannen, Organisationsnamen oder sonstigen Zusatz. Nicht mehr, nicht weniger. "
    "Der rohe Titel kann in JEDER Sprache vorliegen - der bereinigte Titel ist IMMER auf "
    "Deutsch, uebersetze ihn also gegebenenfalls (z.B. 'Solar Eclipse 2027 - NASA' -> "
    "'Sonnenfinsternis')."
)


def suggest_title(text: str, raw_title: str) -> str:
    """Cleans up a page's scraped <title> tag into a short, generic page
    title - the raw title (see crawl_page() in main.py) is often polluted
    with year ranges and a duplicated/appended site name (e.g. "Islamische
    Feiertage 2026 - 2029 - Islamisches Zentrum MuenchenIslamisches Zentrum
    Muenchen"), which then gets used verbatim as page.yaml's title unless an
    operator manually edits it. Raises ExtractionError on failure, same
    contract as the other suggest_*/extract_*() functions here."""
    if not raw_title.strip():
        return ""

    prompt = (
        f"Roher Titel: {raw_title}\n\n"
        f"Text (zur Einordnung):\n\n{text[:1500]}\n\n"
        "Gib den bereinigten Titel zurueck."
    )
    try:
        raw = call_llm(prompt, system=TITLE_SYSTEM_PROMPT)
    except Exception as e:
        raise ExtractionError(str(e)) from e

    return raw.strip().strip('"').strip("'")


CATEGORY_SYSTEM_PROMPT = (
    "Du schlaegst die passende Kategorie fuer eine Wann-Frage-Seite vor. Titel und Text "
    "koennen in JEDER Sprache vorliegen - die Kategorie ist aber IMMER auf Deutsch, auch "
    "wenn der Quelltext in einer anderen Sprache ist. Antworte AUSSCHLIESSLICH mit der "
    "Kategorie als Klartext (kein JSON, keine Anfuehrungszeichen, keine Erklaerung). "
    "Bevorzuge IMMER eine der 'Bereits vorhandenen Kategorien' unten, "
    "wenn eine davon thematisch passt - erfinde nur dann eine neue Kategorie, wenn wirklich "
    "keine der vorhandenen passt. Fuer eine neue, tiefer verschachtelte Kategorie: "
    "'/'-getrennter Pfad (z.B. 'Sport/Fussball/Bundesliga')."
)


def suggest_category(text: str, title: str, existing_categories: List[str]) -> str:
    """Suggests the best-fit category for a page, preferring reuse of
    existing_categories over inventing a new one - same "reuse over
    fragment" policy as suggest_tags(). Raises ExtractionError on failure,
    same contract as the other suggest_*/extract_*() functions here."""
    if not text.strip() and not title.strip():
        return ""

    category_list = ", ".join(existing_categories) if existing_categories else "(noch keine)"
    prompt = (
        f"Titel: {title}\n\n"
        f"Bereits vorhandene Kategorien: {category_list}\n\n"
        f"Text:\n\n{text[:3000]}\n\n"
        "Schlage die passende Kategorie vor."
    )
    try:
        raw = call_llm(prompt, system=CATEGORY_SYSTEM_PROMPT)
    except Exception as e:
        raise ExtractionError(str(e)) from e

    return raw.strip().strip('"').strip("'")


def _validate_ranges(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Shared start/end/label validation, dedup, sort-by-start for a raw
    parsed-JSON list of range-shaped items - used by extract_subjects for
    each discovered subject's ranges. Silently drops malformed/inverted
    entries (same policy as _parse_json_array's callers throughout this
    module) rather than failing the whole extraction over one bad item."""
    ranges = []
    seen = set()
    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for item in items:
        if not isinstance(item, dict):
            continue
        start = str(item.get("start", "")).strip()
        end = str(item.get("end", "")).strip()
        label = str(item.get("label", "")).strip()
        if not date_pattern.match(start) or not date_pattern.match(end) or not label:
            continue
        if end < start:
            continue
        key = (start, end, label)
        if key in seen:
            continue
        seen.add(key)
        ranges.append({"start": start, "end": end, "label": label})

    return sorted(ranges, key=lambda r: r["start"])


SUBJECT_SYSTEM_PROMPT = (
    "Du extrahierst Datumsspannen aus Webseiten-Text, der in JEDER Sprache vorliegen "
    "kann und ggf. MEHRERE unterschiedliche Themen/Subjekte in einem Text behandelt "
    "(z.B. eine Zeile/ein Abschnitt pro Bundesland, pro Obst-/Gemuesesorte, pro Stadt). "
    "Antworte AUSSCHLIESSLICH mit einem JSON-Array, keine Erklaerung, kein Markdown, "
    "kein Codeblock. Jedes Element hat genau die Felder "
    '{"subject": {"slug": "...", "name": "..."}, "ranges": '
    '[{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "label": "kurze Beschreibung"}, ...]}. '
    "'name' und 'label' sind IMMER auf Deutsch, auch wenn der Quelltext in einer anderen "
    "Sprache ist - uebersetze insbesondere Ereignis-, Feiertags- und Themennamen (z.B. "
    "'Solar Eclipse' -> 'Sonnenfinsternis'), nicht nur woertlich uebernehmen ('slug' bleibt "
    "wie gewohnt ein kurzer technischer Bezeichner). "
    "Wenn der Text nur EIN Subjekt behandelt, gib trotzdem ein Array mit genau einem "
    "Element zurueck - erfinde niemals ein zweites. Loese relative/implizite "
    "Jahresangaben auf (z.B. eine Jahreszahl als Tabellenueberschrift, die fuer "
    "mehrere darunterliegende Zeilen gilt). Ueberspringe Datumsspannen ohne konkrete "
    "Anfangs- und Enddaten. Erfinde keine Daten - wenn ein Subjekt keine konkreten "
    "Zeitraeume nennt, gib fuer es ein leeres \"ranges\"-Array zurueck."
)


def extract_subjects(text: str, hint: str) -> List[Dict[str, Any]]:
    """Discovers however many distinct subjects `text` actually covers (one
    Bundesland, one fruit, ...) instead of assuming exactly one - this is
    what lets a single fetch of a page like kmk.org/service/ferien.html
    (which already lists all 16 Bundeslaender) become 16 pages in one run,
    with no per-source Python deciding the split in advance. `hint` is
    caller-supplied domain framing from sources.yaml's extraction_hint
    (subject vocabulary, slug format, what the ranges mean) - the model does
    the actual subject discovery from the real page content, the hint only
    orients it.

    Returns a list of {"subject": {"slug": str, "name": str}, "ranges": [...]}
    (ranges validated via _validate_ranges). Raises ExtractionError on
    failure (missing config, API failure, unparseable response), same
    contract as the other extract_*() functions here.

    No _check_length() guard here (unlike extract_dated_events): like the
    schulferien_kmk source this replaces, callers may pass raw, undecoded
    HTML rather than cleaned text, so inputs are legitimately much larger for
    the same real content."""
    if not text.strip():
        return []

    prompt = f"{hint}\n\nText:\n\n{text}\n\nExtrahiere alle Subjekte und ihre Datumsspannen als JSON-Array."
    try:
        raw = call_llm(prompt, system=SUBJECT_SYSTEM_PROMPT)
    except Exception as e:
        raise ExtractionError(str(e)) from e

    items = _parse_json_array(raw)

    subjects: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        if not isinstance(subject, dict):
            continue
        slug = str(subject.get("slug", "")).strip()
        name = str(subject.get("name", "")).strip()
        if not slug or not name:
            continue
        subjects.append({
            "subject": {"slug": slug, "name": name},
            "ranges": _validate_ranges(item.get("ranges") or []),
        })

    return subjects


SEASON_SYSTEM_PROMPT = (
    "Du extrahierst wiederkehrende JAEHRLICHE Saisonfenster (z.B. Ernte-/"
    "Verfuegbarkeitssaison von Obst oder Gemuese) aus Text, der die farbliche "
    "oder sonstige visuelle Hervorhebung einzelner Monate PRO OBJEKT/SORTE "
    "BESCHREIBT (z.B. 'Aepfel: 1-4 gruen, 5-8 orange, 9-12 gruen', 'Aprikosen: "
    "nur 6-8 orange hervorgehoben, Rest grau'). Der Text kann in JEDER Sprache "
    "vorliegen. Antworte AUSSCHLIESSLICH mit einem JSON-Array, keine Erklaerung, "
    "kein Markdown, kein Codeblock. Jedes Element hat genau die Felder "
    '{"subject": {"slug": "...", "name": "..."}, "windows": '
    '[{"type": "...", "name": "...", "from": "--MM", "to": "--MM"}, ...]}. '
    "'name' ist auf Deutsch, 'type' ein kurzer technischer Slug (z.B. "
    "'main_season', 'peak_season'). 'from'/'to' sind IMMER genau im Format "
    "'--MM' (zwei Bindestriche, zweistelliger Monat 01-12) OHNE Jahr - diese "
    "Fenster gelten JEDES Jahr gleich, nie fuer ein bestimmtes Jahr. Ein "
    "Fenster darf ueber den Jahreswechsel gehen (z.B. '--12' bis '--02'). "
    "Wenn mehrere Hervorhebungsstufen vorkommen (z.B. eine schwaechere Farbe "
    "fuer die normale Saison und eine staerkere/abweichende fuer eine "
    "Spitzensaison), gib pro Stufe ein eigenes Fenster zurueck, nicht nur "
    "eines. NICHT hervorgehobene Monate gehoeren zu KEINEM Fenster - lass sie "
    "weg. Erfinde KEIN Fenster, das nicht durch eine im Text beschriebene "
    "Hervorhebung gestuetzt ist. Wenn der Text mehrere Objekte/Sorten "
    "behandelt, gib fuer jedes ein eigenes Array-Element zurueck; behandelt er "
    "nur eines, trotzdem ein Array mit genau einem Element."
)

_MONTH_ONLY_PATTERN = re.compile(r"^--(0[1-9]|1[0-2])$")


def _validate_season_windows(items: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    windows = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        type_ = str(item.get("type", "")).strip()
        name = str(item.get("name", "")).strip()
        start = str(item.get("from", "")).strip()
        end = str(item.get("to", "")).strip()
        if not type_ or not name or not _MONTH_ONLY_PATTERN.match(start) or not _MONTH_ONLY_PATTERN.match(end):
            continue
        key = (type_, start, end)
        if key in seen:
            continue
        seen.add(key)
        windows.append({"type": type_, "name": name, "from": start, "to": end})
    return windows


def extract_season_windows(text: str, hint: str) -> List[Dict[str, Any]]:
    """Like extract_subjects above, but for year-less RECURRING month
    windows (RawWindow's year: null / "--MM" shape, see lib/schema.ts and
    the hand-authored data/saisonkalender/*) instead of concrete dated
    ranges - the right shape for e.g. "Aepfel are in season May-August every
    year", which has no specific year attached at all. `text` is expected to
    already describe any color-coding/highlighting in words (see
    scraper.py's VISION_PROMPT for images/PDFs) - this function only
    interprets that description, it does not see the image itself.

    Returns a list of {"subject": {"slug": str, "name": str}, "windows":
    [...]} (windows validated via _validate_season_windows). Raises
    ExtractionError on failure, same contract as the other extract_*()
    functions here."""
    if not text.strip():
        return []

    prompt = f"{hint}\n\nText:\n\n{text}\n\nExtrahiere alle Saisonfenster als JSON-Array."
    try:
        raw = call_llm(prompt, system=SEASON_SYSTEM_PROMPT)
    except Exception as e:
        raise ExtractionError(str(e)) from e

    items = _parse_json_array(raw)

    subjects: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        subject = item.get("subject")
        if not isinstance(subject, dict):
            continue
        slug = str(subject.get("slug", "")).strip()
        name = str(subject.get("name", "")).strip()
        if not slug or not name:
            continue
        subjects.append({
            "subject": {"slug": slug, "name": name},
            "windows": _validate_season_windows(item.get("windows") or []),
        })

    return subjects


# Keyword -> type mapping for the "label" an LLM returns for a recurring
# calendar window (e.g. "Osterferien"). Shared across sources rather than
# living in one source's Python, so any multi-subject source (not just
# Schulferien) gets stable replace_key matching across independent LLM runs
# for the common German holiday vocabulary - see type_slug_from_label below.
# Order matters: checked top to bottom, first match wins (e.g. "weihnacht"
# must be checked before a hypothetical looser match).
_TYPE_SLUG_KEYWORDS = [
    ("weihnacht", "school_holidays-christmas"),
    ("oster", "school_holidays-easter"),
    ("pfingst", "school_holidays-whitsun"),
    ("sommer", "school_holidays-summer"),
    ("herbst", "school_holidays-autumn"),
    ("fasching", "school_holidays-winter"),
    ("fasnet", "school_holidays-winter"),
    ("winter", "school_holidays-winter"),
]


def type_slug_from_label(label: str) -> str:
    """Maps a recurring-window label (e.g. "Osterferien") to a stable "type"
    slug (e.g. "school_holidays-easter") for use as part of a merge
    replace_key. Matters because the label is free text an LLM re-generates
    on every run - naively slugifying it verbatim would let small phrasing
    drift (e.g. "Osterferien" vs "Osterferien (angepasst)") change the merge
    key and duplicate windows instead of updating them. Falls back to a
    generic slug for labels not in the keyword list above (e.g. a
    Bundesland-specific bridge day, or a wholly different domain's labels)
    rather than dropping the entry."""
    lower = label.lower()
    for keyword, typ in _TYPE_SLUG_KEYWORDS:
        if keyword in lower:
            return typ
    slug = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    return slug or "other"
