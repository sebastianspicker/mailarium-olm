"""RFC 2822 header/body parsing, MIME decoding, and iCalendar text extraction."""
# pylint: disable=too-many-branches,too-many-statements

from __future__ import annotations

import email
import email.errors
import email.policy
import functools
import logging
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .html_converter import _RE_WHITESPACE_COLLAPSE

logger = logging.getLogger(__name__)

_RE_ICAL_UNFOLD = re.compile(r"\r?\n[\t ]")
_RE_MAILTO = re.compile(r"(?i)mailto:")


@functools.lru_cache(maxsize=32)
def _header_pattern(name: str) -> re.Pattern:
    """Compile and cache a regex for extracting a named RFC 2822 header."""
    return re.compile(
        rf"^{re.escape(name)}:[ \t]*(.+?)(?=\n\S|\n\n|\Z)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )


@functools.lru_cache(maxsize=16)
def _ical_pattern(name: str) -> re.Pattern:
    """Compile and cache a regex for extracting a named iCalendar field."""
    return re.compile(
        rf"^{re.escape(name)}(?:;[^:]*)?:(.+?)(?=\r?\n[^\t ]|\Z)",
        re.MULTILINE | re.DOTALL,
    )


def _normalize_date(value: str) -> str:
    """Normalize a date string to ISO 8601 format.

    Handles both ISO 8601 (from OLM XML) and RFC 2822 (from email headers).
    Returns the original value if parsing fails.
    """
    if not value or not value.strip():
        return ""
    value = value.strip()
    # Already looks like ISO 8601 - normalize to UTC
    if re.match(r"\d{4}-\d{2}-\d{2}T", value):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is not None:
                dt = dt.astimezone(UTC)
            return dt.isoformat()
        except ValueError, OverflowError:
            logger.debug("Failed to parse ISO date: %s", value[:80])
            return ""
    # Try RFC 2822 (e.g. "Wed, 25 Jun 2025 10:52:47 +0200")
    try:
        dt = parsedate_to_datetime(value)
        # Normalize to UTC so all stored dates use a consistent timezone
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC)
        return dt.isoformat()
    except ValueError, TypeError, OverflowError:
        logger.debug("Failed to parse date: %s", value[:80])
        return ""


def _parse_int(value: str, default: int = 0) -> int:
    """Safely parse an integer from a string."""
    if not value or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _extract_body_from_source(raw_source: str) -> tuple[str, str]:
    """Extract body text and HTML from raw RFC 2822 source.

    When OLM has no OPFMessageCopyBody/HTMLBody elements, the full email
    (headers + body) is in OPFMessageCopySource.  This function splits
    headers from body at the first blank line, then handles MIME multipart
    and Content-Transfer-Encoding.
    """
    try:
        msg = email.message_from_string(raw_source, policy=email.policy.default)
    except email.errors.MessageError:
        parts = raw_source.split("\n\n", 1)
        if len(parts) == 2:
            return parts[1].strip(), ""
        return "", ""

    body_text, body_html, calendar_text = _message_bodies(msg)

    # Append calendar details when both text/plain and text/calendar exist
    if calendar_text:
        body_text = f"{body_text}\n\n{calendar_text}" if body_text else calendar_text

    # Fallback for multipart emails with only calendar or attachment parts
    if not body_text and not body_html and msg.is_multipart():
        body_text = _multipart_fallback(msg)

    return body_text.strip(), body_html.strip()


def _message_bodies(message) -> tuple[str, str, str]:
    if message.is_multipart():
        return _multipart_bodies(message)
    body_text, body_html = _singlepart_bodies(message)
    return body_text, body_html, ""


def _multipart_fallback(message) -> str:
    content_types = {part.get_content_type() for part in message.walk() if not part.is_multipart()}
    if "text/calendar" in content_types:
        return "[Calendar meeting invitation]"
    return "[Attachment-only email]" if content_types else ""


def _decoded_part(part) -> str:
    try:
        payload = part.get_content()
    except email.errors.MessageError, LookupError:
        logger.debug("Failed to decode MIME part", exc_info=True)
        return ""
    return payload if isinstance(payload, str) else ""


def _multipart_bodies(message) -> tuple[str, str, str]:
    body_text = body_html = calendar = ""
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type == "text/plain" and not body_text:
            body_text = _decoded_part(part)
        elif content_type == "text/html" and not body_html:
            body_html = _decoded_part(part)
        elif content_type == "text/calendar" and not calendar:
            payload = _decoded_part(part)
            calendar = _calendar_to_text(payload) if payload else ""
    return body_text, body_html, calendar


def _singlepart_bodies(message) -> tuple[str, str]:
    payload = _decoded_part(message)
    if message.get_content_type() == "text/html":
        return "", payload
    if message.get_content_type() == "text/calendar":
        return _calendar_to_text(payload), ""
    return payload, ""


def _calendar_to_text(ical_text: str) -> str:
    """Extract human-readable text from iCalendar (ICS) content.

    No external dependency - uses simple regex patterns to extract
    SUMMARY, DESCRIPTION, DTSTART, DTEND, LOCATION, ORGANIZER.
    """
    if not ical_text:
        return ""
    parts: list[str] = []

    def _ical_field(name: str) -> str:
        # Handle folded lines and parameterized field names (e.g. DTSTART;VALUE=DATE:...)
        m = _ical_pattern(name).search(ical_text)
        if m:
            # Unfold continuation lines
            return _RE_ICAL_UNFOLD.sub("", m.group(1)).strip()
        return ""

    summary = _ical_field("SUMMARY")
    if summary:
        parts.append(f"Meeting: {summary}")

    organizer = _ical_field("ORGANIZER")
    if organizer:
        # Strip mailto: prefix
        organizer = _RE_MAILTO.sub("", organizer)
        parts.append(f"Organizer: {organizer}")

    location = _ical_field("LOCATION")
    if location:
        parts.append(f"Location: {location}")

    dtstart = _ical_field("DTSTART")
    if dtstart:
        parts.append(f"Start: {dtstart}")

    dtend = _ical_field("DTEND")
    if dtend:
        parts.append(f"End: {dtend}")

    description = _ical_field("DESCRIPTION")
    if description:
        # Unescape common ICS escapes
        description = description.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
        parts.append(f"\n{description}")

    return "\n".join(parts) if parts else "[Calendar event]"


def _decode_mime_words(value: str) -> str:
    if "=?" not in value:
        return value
    from email.header import decode_header

    try:
        parts = decode_header(value)
    except email.errors.HeaderParseError:
        return value
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_header(source: str, header_name: str) -> str:
    """Extract a single header value from raw RFC 2822 source.

    Handles continuation lines (lines starting with whitespace).
    Only searches the header section (before the first blank line)
    to avoid false matches in the body.
    """
    # Limit search to header section only (before first blank line)
    blank_line = re.search(r"\n\n|\r\n\r\n", source)
    header_section = source[: blank_line.start()] if blank_line else source

    match = _header_pattern(header_name).search(header_section)
    if not match:
        return ""
    value = match.group(1).strip()
    # Collapse continuation whitespace
    value = _RE_WHITESPACE_COLLAPSE.sub(" ", value)
    return value


def _extract_email_from_header(source: str, header_name: str) -> str:
    """Extract the email address from a From/To header like 'Name <email>'."""
    raw = _extract_header(source, header_name)
    if not raw:
        return ""
    # HTML-encoded angle brackets from OLM: &lt; and &gt;
    raw = raw.replace("&lt;", "<").replace("&gt;", ">")
    match = re.search(r"<([^>]+@[^>]+)>", raw)
    if match:
        return match.group(1)
    # Bare email
    match = re.search(r"[\w.+-]+@[\w.-]+", raw)
    return match.group(0) if match else raw


def _extract_name_from_header(source: str, header_name: str) -> str:
    """Extract the display name from a header like ``"Name" <email>``."""
    raw = _extract_header(source, header_name)
    if not raw:
        return ""
    raw = raw.replace("&lt;", "<").replace("&gt;", ">")
    # Try Python's email.utils first - handles escaped quotes, RFC 2822 names
    try:
        from email.utils import parseaddr

        name, _addr = parseaddr(raw)
        if name:
            return name
    except ValueError, TypeError:
        logger.debug("parseaddr failed for header: %s", raw[:100], exc_info=True)
    # Unquoted Name <email>
    match = re.search(r"^([^<]+)<", raw)
    if match:
        return match.group(1).strip().strip('"')
    return ""


def _parse_address_list(raw: str) -> list[str]:
    """Parse a comma/semicolon-separated list of addresses into email strings.

    Handles quoted display names (e.g. ``"Last, First" <user@example.com>``)
    by splitting only on commas/semicolons that are outside of double quotes.
    """
    raw = raw.replace("&lt;", "<").replace("&gt;", ">")
    # Outlook uses both commas and semicolons as separators
    raw = raw.replace(";", ",")

    # Split on commas outside of double quotes to preserve
    # display names like "Last, First" <user@example.com>
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in raw:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))

    addresses: list[str] = []
    for part in parts:
        part = part.strip()
        match = re.search(r"<([^>]+@[^>]+)>", part)
        if match:
            addresses.append(match.group(1))
        else:
            match = re.search(r"[\w.+-]+@[\w.-]+", part)
            if match:
                addresses.append(match.group(0))
    return addresses


def extract_identity_addresses(addresses: list[str]) -> list[str]:
    """Return unique normalized mailbox identities from parsed header values."""
    identities: list[str] = []
    for raw in addresses:
        for address in _parse_address_list(raw):
            normalized = address.strip().lower()
            if normalized and normalized not in identities:
                identities.append(normalized)
    return identities
