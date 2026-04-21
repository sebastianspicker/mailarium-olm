"""Regex-based entity extraction from email text."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Common email providers — domains here are NOT treated as organizations
_COMMON_PROVIDERS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "google.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "yahoo.de",
        "yahoo.co.uk",
        "gmx.de",
        "gmx.net",
        "gmx.at",
        "gmx.ch",
        "web.de",
        "t-online.de",
        "freenet.de",
        "arcor.de",
        "aol.com",
        "aol.de",
        "icloud.com",
        "me.com",
        "mac.com",
        "protonmail.com",
        "proton.me",
        "zoho.com",
        "yandex.com",
        "mail.com",
        "posteo.de",
        "mailbox.org",
    }
)

_URL_RE = re.compile(r"https?://[^\s<>\"'\]]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[ \t.-]?)?"  # optional country code
    r"(?:\(?\d{2,5}\)?[ \t.-]?)?"  # optional area code
    r"\d[\d \t.\-/]{5,16}\d",  # starts/ends with digit, capped length
)
_DATE_LIKE_RE = re.compile(r"^\d{1,4}[/\-\.]\d{1,2}[/\-\.]\d{1,4}$")
_IP_LIKE_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
_MENTION_RE = re.compile(r"@[a-zA-Z]\w{1,30}")


@dataclass
class ExtractedEntity:
    """A single extracted entity."""

    text: str
    entity_type: str
    normalized_form: str


def extract_entities(text: str, sender_email: str | None = None) -> list[ExtractedEntity]:
    """Extract entities from email body text.

    Returns deduplicated list of ExtractedEntity.
    """
    if not text:
        return []

    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()

    def _add(text_val: str, etype: str, norm: str) -> None:
        key = (norm.lower(), etype)
        if key not in seen:
            seen.add(key)
            entities.append(ExtractedEntity(text_val, etype, norm.lower()))

    # URLs
    for match in _URL_RE.finditer(text):
        url = match.group().rstrip(".,;:!?")
        # Only strip trailing ) if parens are unbalanced
        while url.endswith(")") and url.count("(") < url.count(")"):
            url = url[:-1]
        _add(url, "url", url)

    # Email addresses
    for match in _EMAIL_RE.finditer(text):
        addr = match.group()
        _add(addr, "email", addr)

    # Phone numbers
    for match in _PHONE_RE.finditer(text):
        raw = match.group().strip()
        # Skip date-like patterns (e.g. 2024-01-15, 15/01/2024) and IPs
        if _DATE_LIKE_RE.match(raw) or _IP_LIKE_RE.match(raw):
            continue
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 7:
            _add(raw, "phone", digits)

    # @mentions
    for match in _MENTION_RE.finditer(text):
        mention = match.group()
        _add(mention, "mention", mention)

    # Organizations from sender domain
    if sender_email and "@" in sender_email:
        domain = sender_email.split("@", 1)[1].lower().strip()
        if domain and domain not in _COMMON_PROVIDERS:
            _add(domain, "organization", domain)

    return entities
