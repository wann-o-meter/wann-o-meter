"""Per-domain consent ledger: who said yes, who said no, who was asked and
when. Lives in pipeline/config/consent.yaml (operational state of the
pipeline, not decreed data - nothing under /data reads it).

Why this exists: some sites publish an explicit reservation of rights, e.g.
volksfestundkirmes.de's "Kein Teil dieses Internet-Angebots darf ... zum
Anlernen von KI-Systemen genutzt werden". robots.txt does not carry that -
it is prose on the page, and it is a "no" until the owner says otherwise.

Three-way, not two-way: `denied` blocks (crawler skips the URL, review
refuses to approve it into data/), `granted` unlocks the
`permission_granted` license, and everything else - `unknown`, `pending` -
proceeds and is merely flagged. Defaulting unknown to "block" would break
every source that predates this file and turn adding a source into a
two-step dance; the ask was "respect it, or at least inform".

Each record keeps its own append-only `history`, because the point of a
consent ledger is being able to prove months later WHEN a domain was asked
and what it answered - a bare `domain: denied` is worth little then.
"""

import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import yaml

CONSENT_PATH = Path(__file__).resolve().parent.parent / "config" / "consent.yaml"
OUTBOX_DIR = Path(__file__).resolve().parent.parent / "consent-outbox"

STATUSES = ("unknown", "pending", "granted", "denied")

# The one status that stops work. Split out so the check reads as intent at
# both enforcement points (crawler.crawl, main._approve_one).
BLOCKING_STATUS = "denied"


class ConsentError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_domain(url_or_domain: str) -> str:
    """Host, lowercased, without www./port/scheme. Consent is given by a
    site owner, not per-subdomain-spelling - www.volksfestundkirmes.de and
    volksfestundkirmes.de are the same "no"."""
    text = (url_or_domain or "").strip()
    if "//" in text:
        text = urlparse(text).netloc
    else:
        text = text.split("/")[0]
    host = text.lower().split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def load() -> Dict[str, Dict[str, Any]]:
    if not CONSENT_PATH.exists():
        return {}
    with CONSENT_PATH.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return dict(raw.get("domains") or {})


def save(records: Dict[str, Dict[str, Any]]) -> None:
    CONSENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONSENT_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"domains": dict(sorted(records.items()))},
            f, allow_unicode=True, sort_keys=False, default_flow_style=False,
        )


def covers(parent: str, host: str) -> bool:
    """Whether a decision recorded for `parent` governs `host` - the same
    host, or a subdomain of it. Both already normalized."""
    return host == parent or host.endswith("." + parent)


def _matching_key(records: Dict[str, Any], key: str) -> Optional[str]:
    """The record that governs `key`: itself, else the nearest parent domain
    with a record. A site's "no" is about the site, not about one hostname -
    volksfestundkirmes.de saying no covers events.volksfestundkirmes.de,
    which would otherwise be a one-subdomain hole in the block.

    ponytail: stops at two labels, so a record on a public suffix like
    "co.uk" would govern everything under it. Nobody can register one as a
    site owner, and the ledger is hand-curated - swap in a public-suffix
    list if that ever stops being true."""
    labels = key.split(".")
    while len(labels) >= 2:
        candidate = ".".join(labels)
        if candidate in records:
            return candidate
        labels.pop(0)
    return None


def get(domain: str) -> Dict[str, Any]:
    """The record governing a domain, or an all-defaults one for a domain
    nobody has decided anything about yet. `inherited_from` names the parent
    domain when the decision was made one level up."""
    key = normalize_domain(domain)
    records = load()
    match = _matching_key(records, key)
    if match:
        return {"domain": key, "inherited_from": "" if match == key else match, **records[match]}
    return {"domain": key, "inherited_from": "", "status": "unknown", "contact_email": "", "note": "", "history": []}


def status(url_or_domain: str) -> str:
    return get(url_or_domain).get("status", "unknown")


def is_denied(url_or_domain: str) -> bool:
    return status(url_or_domain) == BLOCKING_STATUS


def set_status(
    domain: str,
    new_status: str,
    *,
    contact_email: Optional[str] = None,
    note: Optional[str] = None,
    event: str = "",
) -> Dict[str, Any]:
    if new_status not in STATUSES:
        raise ConsentError(f"unknown consent status '{new_status}' (expected one of {', '.join(STATUSES)})")
    key = normalize_domain(domain)
    if not key:
        raise ConsentError("empty domain")

    records = load()
    record = records.get(key) or {"status": "unknown", "contact_email": "", "note": "", "history": []}
    record["status"] = new_status
    if contact_email is not None:
        record["contact_email"] = contact_email.strip()
    # An explicitly-passed blank note (the form always sends the field)
    # CLEARS the old one: a "denied per the banner on their site" note
    # surviving a later flip to granted would describe the opposite of the
    # current status. The old text stays readable in history. None means
    # "not part of this change" - what send_request does when it only moves
    # the status to pending.
    if note is not None:
        record["note"] = note
    if new_status == "pending":
        record["requested_at"] = _now()
    if new_status in ("granted", "denied"):
        record["responded_at"] = _now()
    record.setdefault("history", []).append({
        "at": _now(),
        "status": new_status,
        "event": event or f"status set to {new_status}",
        "note": note or "",
    })
    records[key] = record
    save(records)
    return {"domain": key, **record}


_MAILTO_RE = re.compile(rb"mailto:([^\"'?>\s]+@[^\"'?>\s]+)", re.IGNORECASE)
_IMPRESSUM_PATHS = ("/impressum", "/impressum.html", "/kontakt", "/contact")


DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "data"


def pages_citing(domain: str) -> List[str]:
    """Which already-published pages cite this domain - data/{category}/
    {slug} paths, read-only. Blocking future crawls and future approvals
    says nothing about what is already in data/, and a `denied` decision (or
    a withdrawn consent) is exactly when someone needs to know what to take
    down. Deliberately reports rather than deletes: removing a window is a
    hand edit plus a commit, not something a status change should do behind
    the operator's back.

    Reads both the file-level `source[].url` list and each window's
    `source_urls` (see store.merge_zeitfenster) - a window can cite a domain
    the file's source list no longer mentions."""
    key = normalize_domain(domain)
    hits: List[str] = []
    if not DATA_ROOT.exists():
        return hits
    for path in sorted(DATA_ROOT.glob("**/data.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
        except Exception:
            continue
        # `source` is a bare object on every page written before the list
        # form existed (lib/pages-schema.ts accepts both, and half of
        # data/saisonkalender is still the object) - iterating that yields
        # its KEYS, so this has to normalize like main._as_quelle_list does.
        sources = doc.get("source") or []
        if isinstance(sources, dict):
            sources = [sources]
        urls = [source.get("url", "") for source in sources if isinstance(source, dict)]
        for window in doc.get("windows") or []:
            urls.extend(window.get("source_urls") or [])
        if any(covers(key, normalize_domain(url)) for url in urls if url):
            hits.append(str(path.parent.relative_to(DATA_ROOT)))
    return hits


def find_contact(url: str) -> Optional[str]:
    """First mailto: address on the site's homepage or Impressum. German
    sites are legally required to publish one there (TMG §5), which makes
    this a good-enough address hunt for a one-off consent request - the
    operator sees and can override it before anything is sent.

    ponytail: first hit wins, no ranking of info@ over datenschutz@. Add
    scoring if the wrong address keeps coming back."""
    from core.fetch import Config, fetch_bytes  # local: keeps the ledger importable without network deps

    # A denied domain is not fetched, full stop - the request email tells
    # the owner their site is "weder abgerufen noch veröffentlicht", and an
    # address lookup is still a fetch.
    if is_denied(url):
        return None

    parsed = urlparse(url if "//" in url else f"https://{url}")
    base = f"{parsed.scheme}://{parsed.netloc}"
    config = Config()
    for candidate in [url if "//" in url else base, *(base + p for p in _IMPRESSUM_PATHS)]:
        try:
            content, _ = fetch_bytes(candidate, config)
        except Exception:
            continue
        match = _MAILTO_RE.search(content)
        if match:
            return match.group(1).decode("utf-8", "replace").strip()
    return None


# German, because the recipient is a German site owner. Identifiers and
# comments stay English; this is content, not code.
CONSENT_EMAIL_SUBJECT = "Anfrage: Nutzung Ihrer Termindaten auf wannometer.de"

CONSENT_EMAIL_BODY = """Guten Tag,

wir betreiben wannometer.de, einen offenen, quellenbelegten Kalender für
Zeitfenster (Feiertage, Ferien, Saison- und Veranstaltungstermine). Jede
Angabe wird mit Quellenlink und Abrufdatum veröffentlicht.

Wir würden gerne die auf {domain} veröffentlichten Termindaten
(Datum/Zeitraum und Bezeichnung der Veranstaltung - keine Texte, keine
Bilder) übernehmen und mit Verlinkung auf Ihre Seite als Quelle anzeigen.

Bitte antworten Sie kurz auf diese E-Mail mit:

  JA   - Sie stimmen der Nutzung der Termindaten mit Quellenangabe zu
  NEIN - Sie stimmen nicht zu. Wir sperren {domain} dann dauerhaft in
         unserem System: die Domain wird weder abgerufen noch
         veröffentlicht, und bereits übernommene Daten entfernen wir.

Eine Zustimmung können Sie jederzeit formlos per E-Mail an {sender}
widerrufen; wir entfernen die Daten dann.

Vielen Dank für Ihre Zeit.

Mit freundlichen Grüßen
{sender_name}
{sender}
https://wannometer.de
"""


def build_message(domain: str, contact_email: str) -> EmailMessage:
    sender = os.environ.get("CONSENT_FROM", "am9zzwy@gmail.com")
    message = EmailMessage()
    message["Subject"] = CONSENT_EMAIL_SUBJECT
    message["From"] = sender
    message["To"] = contact_email
    message.set_content(CONSENT_EMAIL_BODY.format(
        domain=normalize_domain(domain),
        sender=sender,
        sender_name=os.environ.get("CONSENT_FROM_NAME", "wannometer.de"),
    ))
    return message


def send_request(domain: str, contact_email: str, dry_run: bool = False) -> str:
    """Writes the request to consent-outbox/ ALWAYS (that file is the record
    of what was actually sent), then hands it to SMTP if SMTP_HOST is
    configured and this isn't a dry run. Unconfigured or dry-run leaves the
    .eml for the operator to send by hand - sending mail to a real site
    owner is irreversible, so it takes explicit configuration, never a
    default."""
    key = normalize_domain(domain)
    contact_email = (contact_email or "").strip()
    if "@" not in contact_email:
        raise ConsentError(f"'{contact_email}' is not an email address")

    message = build_message(key, contact_email)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTBOX_DIR / f"{key}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.eml"
    path.write_bytes(bytes(message))

    host = os.environ.get("SMTP_HOST")
    if dry_run or not host:
        why = "dry run" if dry_run else "SMTP_HOST not set"
        set_status(key, "pending", contact_email=contact_email,
                   event=f"consent request drafted for {contact_email} ({why}): {path.name}")
        return f"Draft written to {path} - not sent ({why})."

    with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
        if user and password:
            smtp.login(user, password)
        smtp.send_message(message)
    set_status(key, "pending", contact_email=contact_email,
               event=f"consent request sent to {contact_email} via {host}: {path.name}")
    return f"Sent to {contact_email} (copy: {path})."


def overview(domains: List[str]) -> List[Dict[str, Any]]:
    """One row per domain for the dashboard - every domain a crawl source
    touches, plus every domain the ledger already knows about, so a decision
    can be recorded before (or after) a source for it exists."""
    known = load()
    keys = sorted({normalize_domain(d) for d in domains if d} | set(known))
    return [{**get(key), "published_pages": pages_citing(key)} for key in keys]
