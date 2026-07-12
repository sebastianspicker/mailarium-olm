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

    rows = [
        *_url_rows(text),
        *_simple_regex_rows(text, _EMAIL_RE, "email"),
        *_phone_rows(text),
        *_simple_regex_rows(text, _MENTION_RE, "mention"),
        *_domain_rows(sender_email),
    ]
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()
    for text_value, entity_type, normalized in rows:
        key = (normalized.lower(), entity_type)
        if key not in seen:
            seen.add(key)
            entities.append(ExtractedEntity(text_value, entity_type, normalized.lower()))
    return entities


def _url_rows(text: str):
    for match in _URL_RE.finditer(text):
        url = match.group().rstrip(".,;:!?")
        while url.endswith(")") and url.count("(") < url.count(")"):
            url = url[:-1]
        yield url, "url", url


def _simple_regex_rows(text: str, pattern, entity_type: str):
    for match in pattern.finditer(text):
        value = match.group()
        yield value, entity_type, value


def _phone_rows(text: str):
    for match in _PHONE_RE.finditer(text):
        raw = match.group().strip()
        digits = re.sub(r"\D", "", raw)
        if not (_DATE_LIKE_RE.match(raw) or _IP_LIKE_RE.match(raw)) and len(digits) >= 7:
            yield raw, "phone", digits


def _domain_rows(sender_email: str | None):
    if sender_email and "@" in sender_email:
        domain = sender_email.split("@", 1)[1].lower().strip()
        if domain and domain not in _COMMON_PROVIDERS:
            yield domain, "organization", domain
