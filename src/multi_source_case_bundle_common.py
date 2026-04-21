# mypy: disable-error-code=name-defined
"""Split multi-source case-bundle helpers (multi_source_case_bundle_common)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from .attachment_extractor import (
    attachment_format_profile,
    extraction_quality_profile,
)

MULTI_SOURCE_CASE_BUNDLE_VERSION = "1"
_DECLARED_SOURCE_TYPES = (
    "email",
    "attachment",
    "meeting_note",
    "chat_log",
    "formal_document",
    "note_record",
    "time_record",
    "participation_record",
)
_FORMAL_DOCUMENT_EXTENSIONS = {".doc", ".docx", ".md", ".odt", ".pdf", ".rtf", ".txt"}
_FORMAL_DOCUMENT_MIME_MARKERS = (
    "application/pdf",
    "application/msword",
    "application/rtf",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/rtf",
)
_NOTE_RECORD_KEYWORDS = (
    "notes",
    "memo",
    "minutes",
    "meeting summary",
    "protokoll",
    "gedächtnisprotokoll",
    "gedaechtnisprotokoll",
    "aktennotiz",
)
_TIME_RECORD_KEYWORDS = (
    "timesheet",
    "time sheet",
    "time record",
    "attendance",
    "arbeitszeit",
    "arbeitszeitnachweis",
    "zeiterfassung",
    "stundennachweis",
)
_PARTICIPATION_RECORD_KEYWORDS = (
    "sbv",
    "schwerbehindertenvertretung",
    "personalrat",
    "betriebsrat",
    "mitbestimmung",
    "consultation",
    "beteiligung",
    "anhoerung",
    "anhörung",
)
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DATE_RANGE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|through|until|bis|–|-)\s*(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_EU_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)")
_DATE_RANGE_EU_RE = re.compile(
    r"(?<!\d)(\d{1,2}[./]\d{1,2}[./]20\d{2})\s*(?:to|through|until|bis|–|-)\s*(\d{1,2}[./]\d{1,2}[./]20\d{2})(?!\d)",
    re.IGNORECASE,
)
_SHEET_NAME_RE = re.compile(r"\[Sheet:\s*([^\]]+)\]")
_MONTH_LABEL_RE = re.compile(
    r"(?i)\b("
    r"january|february|march|april|may|june|july|august|september|october|november|december|"
    r"januar|februar|märz|maerz|april|mai|juni|juli|august|september|oktober|november|dezember"
    r")\b"
)
_ICAL_FIELD_RE = re.compile(
    r"(?im)^(SUMMARY|DTSTART|DTEND|LOCATION|ORGANIZER|ATTENDEE|STATUS|METHOD|SEQUENCE|UID|RECURRENCE-ID|DESCRIPTION)[^:\n]*:(.+)$"
)
_ICAL_DATETIME_RE = re.compile(r"\b(20\d{2})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?)?")
_EMAIL_LINK_TOKEN_RE = re.compile(r"[a-z0-9äöüß]{4,}")
_TITLE_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[-._](\d{2})[-._](\d{2})(?!\d)")
_EMAIL_LINK_STOPWORDS = {
    "about",
    "after",
    "before",
    "document",
    "dokument",
    "email",
    "formal",
    "from",
    "meeting",
    "message",
    "note",
    "record",
    "reply",
    "status",
    "subject",
    "summary",
    "thread",
}
_INLINE_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_DATE_ORIGIN_PRIORITY = {
    "meeting_metadata": 60,
    "calendar_dtstart": 55,
    "time_record_range_start": 50,
    "document_text": 45,
    "time_record_range_end": 35,
    "source_timestamp": 25,
}

# ruff: noqa: F401,F821


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _normalized_subject(value: Any) -> str:
    subject = _normalized_text(value)
    while True:
        updated = re.sub(r"^(?:re:|aw:|fwd:|wg:)\s*", "", subject).strip()
        if updated == subject:
            return subject
        subject = updated


def _date_key(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _identity_tokens_for_source(source: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()

    def _add_identity_variants(raw_value: Any) -> None:
        value = str(raw_value or "").strip()
        normalized = _normalized_text(value)
        if normalized:
            tokens.add(normalized)
        for match in _INLINE_EMAIL_RE.finditer(value.casefold()):
            tokens.add(match.group(0))
        name_only = _normalized_text(_INLINE_EMAIL_RE.sub("", re.sub(r"[<>]", " ", value)))
        if name_only:
            tokens.add(name_only)

    for key in ("author", "sender_name", "sender_email"):
        _add_identity_variants(source.get(key))
    for key in ("recipients", "participants", "to", "cc", "bcc"):
        for item in _string_list(source.get(key)):
            _add_identity_variants(item)
    return tokens


def _issue_tokens(value: Any) -> set[str]:
    return {
        match.group(0)
        for match in _EMAIL_LINK_TOKEN_RE.finditer(_normalized_text(value))
        if match.group(0) not in _EMAIL_LINK_STOPWORDS
    }


def _link_confidence(score: int, *, explicit_uid: bool) -> str:
    if explicit_uid or score >= 7:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def _iso_date_from_eu_text(value: str) -> str:
    match = _EU_DATE_RE.search(str(value or ""))
    if not match:
        return ""
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _date_candidates_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    for match in _ISO_DATE_RE.finditer(text):
        value = str(match.group(1) or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    title_match = _TITLE_DATE_RE.search(text)
    if title_match:
        value = f"{title_match.group(1)}-{title_match.group(2)}-{title_match.group(3)}"
        if value not in candidates:
            candidates.append(value)
    for match in _EU_DATE_RE.finditer(text):
        value = _iso_date_from_eu_text(match.group(0))
        if value and value not in candidates:
            candidates.append(value)
    return candidates


__all__ = [
    "MULTI_SOURCE_CASE_BUNDLE_VERSION",
    "_DATE_ORIGIN_PRIORITY",
    "_DATE_RANGE_EU_RE",
    "_DATE_RANGE_RE",
    "_DECLARED_SOURCE_TYPES",
    "_EMAIL_LINK_STOPWORDS",
    "_EMAIL_LINK_TOKEN_RE",
    "_EU_DATE_RE",
    "_FORMAL_DOCUMENT_EXTENSIONS",
    "_FORMAL_DOCUMENT_MIME_MARKERS",
    "_ICAL_DATETIME_RE",
    "_ICAL_FIELD_RE",
    "_INLINE_EMAIL_RE",
    "_ISO_DATE_RE",
    "_MONTH_LABEL_RE",
    "_NOTE_RECORD_KEYWORDS",
    "_PARTICIPATION_RECORD_KEYWORDS",
    "_SHEET_NAME_RE",
    "_TIME_RECORD_KEYWORDS",
    "_TITLE_DATE_RE",
    "_date_candidates_from_text",
    "_date_key",
    "_identity_tokens_for_source",
    "_iso_date_from_eu_text",
    "_issue_tokens",
    "_link_confidence",
    "_normalized_subject",
    "_normalized_text",
]
