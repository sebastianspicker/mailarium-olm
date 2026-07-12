# mypy: disable-error-code=name-defined
# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split multi-source case-bundle helpers (multi_source_case_bundle_common)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from itertools import pairwise
from typing import Any

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


class _LinearMatch:
    def __init__(self, start: int, end: int, groups: tuple[str, ...]) -> None:
        self._start = start
        self._end = end
        self._groups = groups

    def start(self) -> int:
        return self._start

    def end(self) -> int:
        return self._end

    def group(self, index: int = 0) -> str:
        if index == 0:
            return self._groups[0]
        return self._groups[index]

    def groups(self):
        return self._groups[1:]


class _LinearPattern:
    def __init__(self, finder: Callable[[str], Iterator[_LinearMatch]]) -> None:
        self._finder = finder

    def finditer(self, text: str) -> Iterator[_LinearMatch]:
        return self._finder(text)

    def search(self, text: str) -> _LinearMatch | None:
        return next(self._finder(text), None)

    def sub(self, replacement: str, text: str) -> str:
        output: list[str] = []
        start = 0
        for match in self._finder(text):
            output.extend((text[start : match.start()], replacement))
            start = match.end()
        output.append(text[start:])
        return "".join(output)


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def _fixed_date_at(text: str, index: int, separator: str) -> tuple[str, str, str] | None:
    if separator == "-":
        return _iso_date_parts(text[index : index + 10])
    return _eu_date_parts(text, index)


def _iso_date_parts(token: str) -> tuple[str, str, str] | None:
    """Return ISO date parts when a fixed-width token is valid."""
    if len(token) != 10 or token[4] != "-" or token[7] != "-":
        return None
    year, month, day = token[:4], token[5:7], token[8:]
    return (year, month, day) if year.isdigit() and month.isdigit() and day.isdigit() else None


def _eu_date_parts(text: str, index: int) -> tuple[str, str, str] | None:
    """Return day, month, and year from a European date beginning at index."""
    day, first_end = _one_or_two_digits(text, index)
    if not day or first_end >= len(text) or text[first_end] not in "./":
        return None
    month, second_end = _one_or_two_digits(text, first_end + 1)
    if not month or second_end >= len(text) or text[second_end] not in "./":
        return None
    year = text[second_end + 1 : second_end + 5]
    return (day, month, year) if len(year) == 4 and year.startswith("20") and year.isdigit() else None


def _one_or_two_digits(text: str, index: int) -> tuple[str, int]:
    """Read one or two digits without accepting a non-digit prefix."""
    candidate = text[index : index + 2]
    length = 2 if candidate.isdigit() else 1
    value = text[index : index + length]
    return (value, index + length) if value.isdigit() else ("", index)


def _date_matches(text: str, *, separator: str) -> Iterator[_LinearMatch]:
    for index in range(len(text)):
        parts = _fixed_date_at(text, index, separator)
        if parts is None:
            continue
        length = 10 if separator == "-" else len(parts[0]) + len(parts[1]) + 6
        if (index == 0 or not text[index - 1].isdigit()) and (index + length == len(text) or not text[index + length].isdigit()):
            token = text[index : index + length]
            groups = (token, token) if separator == "-" else (token, *parts)
            yield _LinearMatch(index, index + length, groups)


def _title_date_matches(text: str) -> Iterator[_LinearMatch]:
    for index in range(len(text) - 9):
        token = text[index : index + 10]
        if (
            token[:4].startswith("20")
            and token[:4].isdigit()
            and token[4] in "-._"
            and token[5:7].isdigit()
            and token[7] in "-._"
            and token[8:].isdigit()
        ):
            if (index == 0 or not text[index - 1].isdigit()) and (index + 10 == len(text) or not text[index + 10].isdigit()):
                yield _LinearMatch(index, index + 10, (token, token[:4], token[5:7], token[8:]))


def _token_matches(text: str) -> Iterator[_LinearMatch]:
    index = 0
    while index < len(text):
        if not (text[index].isalnum() and not text[index].isupper()):
            index += 1
            continue
        end = index + 1
        while end < len(text) and (text[end].isalnum() and not text[end].isupper()):
            end += 1
        token = text[index:end]
        yield _LinearMatch(index, end, (token, token))
        index = end


def _email_matches(text: str) -> Iterator[_LinearMatch]:
    allowed = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._%+-@")
    index = 0
    while index < len(text):
        if text[index] not in allowed:
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end] in allowed:
            end += 1
        token = text[index:end]
        local, marker, domain = token.partition("@")
        suffix = domain.rpartition(".")[2]
        if marker and local and domain and "." in domain and len(suffix) >= 2 and suffix.isalpha():
            yield _LinearMatch(index, end, (token, token))
        index = end


def _range_matches(text: str, pattern: _LinearPattern) -> Iterator[_LinearMatch]:
    matches = list(pattern.finditer(text))
    connectors = {"to", "through", "until", "bis", "-", "–"}
    for first, second in pairwise(matches):
        if text[first.end() : second.start()].strip().casefold() in connectors:
            yield _LinearMatch(first.start(), second.end(), (text[first.start() : second.end()], first.group(1), second.group(1)))


def _sheet_name_matches(text: str) -> Iterator[_LinearMatch]:
    marker = "[Sheet:"
    start = 0
    while (index := text.find(marker, start)) >= 0:
        end = text.find("]", index + len(marker))
        if end < 0:
            return
        name = text[index + len(marker) : end].lstrip()
        if name:
            yield _LinearMatch(index, end + 1, (text[index : end + 1], name))
        start = end + 1


_MONTH_NAMES = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "januar",
        "februar",
        "märz",
        "maerz",
        "mai",
        "juni",
        "juli",
        "oktober",
        "dezember",
    }
)


def _month_matches(text: str) -> Iterator[_LinearMatch]:
    index = 0
    while index < len(text):
        if not text[index].isalpha():
            index += 1
            continue
        end = index + 1
        while end < len(text) and text[end].isalpha():
            end += 1
        token = text[index:end]
        if token.casefold() in _MONTH_NAMES:
            yield _LinearMatch(index, end, (token, token))
        index = end


_ICAL_FIELDS = frozenset(
    {
        "SUMMARY",
        "DTSTART",
        "DTEND",
        "LOCATION",
        "ORGANIZER",
        "ATTENDEE",
        "STATUS",
        "METHOD",
        "SEQUENCE",
        "UID",
        "RECURRENCE-ID",
        "DESCRIPTION",
    }
)


def _ical_field_matches(text: str) -> Iterator[_LinearMatch]:
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        head, separator, value = line.partition(":")
        field = head.split(";", 1)[0].upper()
        if separator and field in _ICAL_FIELDS and value:
            yield _LinearMatch(offset, offset + len(line), (line, field, value))
        offset += len(raw_line)


def _ical_datetime_matches(text: str) -> Iterator[_LinearMatch]:
    for index in range(len(text) - 7):
        date_token = text[index : index + 8]
        if not date_token.startswith("20") or not date_token.isdigit() or (index > 0 and _is_word_character(text[index - 1])):
            continue
        end = index + 8
        groups: list[str | None] = [date_token[:4], date_token[4:6], date_token[6:8], None, None, None]
        if end < len(text) and text[end] == "T" and text[end + 1 : end + 5].isdigit():
            groups[3:5] = [text[end + 1 : end + 3], text[end + 3 : end + 5]]
            end += 5
            if text[end : end + 2].isdigit():
                groups[5] = text[end : end + 2]
                end += 2
        yield _LinearMatch(index, end, (text[index:end], *groups))  # type: ignore[arg-type]


_ISO_DATE_RE = _LinearPattern(lambda text: _date_matches(text, separator="-"))
_EU_DATE_RE = _LinearPattern(lambda text: _date_matches(text, separator="."))
_DATE_RANGE_RE = _LinearPattern(lambda text: _range_matches(text, _ISO_DATE_RE))
_DATE_RANGE_EU_RE = _LinearPattern(lambda text: _range_matches(text, _EU_DATE_RE))
_SHEET_NAME_RE = _LinearPattern(_sheet_name_matches)
_MONTH_LABEL_RE = _LinearPattern(_month_matches)
_ICAL_FIELD_RE = _LinearPattern(_ical_field_matches)
_ICAL_DATETIME_RE = _LinearPattern(_ical_datetime_matches)
_TITLE_DATE_RE = _LinearPattern(_title_date_matches)
_EMAIL_LINK_TOKEN_RE = _LinearPattern(_token_matches)
_INLINE_EMAIL_RE = _LinearPattern(_email_matches)
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
_DATE_ORIGIN_PRIORITY = {
    "meeting_metadata": 60,
    "calendar_dtstart": 55,
    "time_record_range_start": 50,
    "document_text": 45,
    "time_record_range_end": 35,
    "source_timestamp": 25,
}


def _normalized_text(value: Any) -> str:
    """Normalize text by converting to string, lowercasing, and collapsing whitespace.

    Args:
        value: The value to normalize.

    Returns:
        A normalized string with single spaces between words, all lowercase.
    """
    return " ".join(str(value or "").lower().split())


def _normalized_subject(value: Any) -> str:
    """Normalize a subject line by removing common email prefixes and extra whitespace.

    Args:
        value: The subject value to normalize.

    Returns:
        The normalized subject string with email prefixes (re:, aw:, fwd:, wg:) removed.
    """
    subject = _normalized_text(value)
    while True:
        updated = subject
        for prefix in ("re:", "aw:", "fwd:", "wg:"):
            if subject.startswith(prefix):
                updated = subject[len(prefix) :].lstrip()
                break
        if updated == subject:
            return subject
        subject = updated


def _date_key(value: Any) -> str:
    """Extract a date key from a value, truncating to first 10 characters if long enough.

    Args:
        value: The value to extract a date key from.

    Returns:
        The first 10 characters of the stripped string value, or the full string if shorter.
    """
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _string_list(value: Any) -> list[str]:
    """Convert list values to non-empty strings."""

    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def _identity_tokens_for_source(source: dict[str, Any]) -> set[str]:
    """Extract identity tokens (names, emails) from a source dictionary.

    Args:
        source: Dictionary containing source data with author, sender, recipients, etc.

    Returns:
        A set of normalized identity tokens including emails and names from the source.
    """
    tokens: set[str] = set()

    def _add_identity_variants(raw_value: Any) -> None:
        """Add identity variants (normalized text, emails) from a raw value to tokens set.

        Args:
            raw_value: The raw value to extract identity variants from.
        """
        value = str(raw_value or "").strip()
        normalized = _normalized_text(value)
        if normalized:
            tokens.add(normalized)
        for match in _INLINE_EMAIL_RE.finditer(value.casefold()):
            tokens.add(match.group(0))
        name_only = _normalized_text(_INLINE_EMAIL_RE.sub("", value.replace("<", " ").replace(">", " ")))
        if name_only:
            tokens.add(name_only)

    for key in ("author", "sender_name", "sender_email"):
        _add_identity_variants(source.get(key))
    for key in ("recipients", "participants", "to", "cc", "bcc"):
        for item in _string_list(source.get(key)):
            _add_identity_variants(item)
    return tokens


def _issue_tokens(value: Any) -> set[str]:
    """Extract issue tokens from text using the email link token regex.

    Args:
        value: The value to extract issue tokens from.

    Returns:
        A set of matched tokens that are not in the stopwords list.
    """
    return {
        match.group(0)
        for match in _EMAIL_LINK_TOKEN_RE.finditer(_normalized_text(value))
        if len(match.group(0)) >= 4 and match.group(0) not in _EMAIL_LINK_STOPWORDS
    }


def _link_confidence(score: int, *, explicit_uid: bool) -> str:
    """Determine link confidence level based on score and explicit UID presence.

    Args:
        score: The matching score for the link.
        explicit_uid: Whether an explicit UID is present.

    Returns:
        Confidence level string: 'high' (score >= 7 or explicit_uid), 'medium' (score >= 5), or 'low'.
    """
    if explicit_uid or score >= 7:
        return "high"
    if score >= 5:
        return "medium"
    return "low"


def _iso_date_from_eu_text(value: str) -> str:
    """Convert a European date format string to ISO date format.

    Args:
        value: The string potentially containing a European date (dd/mm/yyyy or dd.mm.yyyy).

    Returns:
        ISO format date string (yyyy-mm-dd), or empty string if no match found or conversion fails.
    """
    match = _EU_DATE_RE.search(str(value or ""))
    if not match:
        return ""
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _date_candidates_from_text(text: str) -> list[str]:
    """Extract date candidates from text using various date patterns.

    Args:
        text: The text to search for date patterns.

    Returns:
        A list of unique ISO date strings found in the text, ordered by discovery.
        Searches for ISO dates, title dates, and European dates.
    """
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
