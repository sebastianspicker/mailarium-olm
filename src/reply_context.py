"""Quoted reply-context extraction from embedded mail-header blocks."""
# pylint: disable=too-many-locals

from __future__ import annotations

from dataclasses import dataclass

from .html_converter import clean_text as _clean_text
from .html_converter import html_to_text as _html_to_text
from .html_converter import looks_like_html as _looks_like_html
from .rfc2822 import _decode_mime_words, _normalize_date, _parse_address_list

_RE_REPLY_CONTEXT_LABELS = {
    "from": "from",
    "von": "from",
    "de": "from",
    "van": "from",
    "da": "from",
    "från": "from",
    "fra": "from",
    "od": "from",
    "sent": "sent",
    "gesendet": "sent",
    "envoyée": "sent",
    "envoyee": "sent",
    "enviado": "sent",
    "verzonden": "sent",
    "inviato": "sent",
    "skickat": "sent",
    "sendt": "sent",
    "wysłano": "sent",
    "wyslano": "sent",
    "to": "to",
    "an": "to",
    "à": "to",
    "a": "to",
    "para": "to",
    "till": "to",
    "til": "to",
    "do": "to",
    "subject": "subject",
    "betreff": "subject",
    "objet": "subject",
    "asunto": "subject",
    "assunto": "subject",
    "onderwerp": "subject",
    "oggetto": "subject",
    "emne": "subject",
    "temat": "subject",
    "date": "date",
    "cc": "cc",
    "bcc": "bcc",
}


def _is_reply_wrapper_line(line: str) -> bool:
    normalized = line.strip().casefold()
    if not normalized.endswith(":"):
        return False
    content = normalized[:-1].rstrip()
    return (content.startswith("on ") and content.endswith(" wrote")) or (content.startswith("am ") and " schrieb" in content[3:])


def _is_reply_separator_line(line: str) -> bool:
    stripped = line.strip()
    leading = len(stripped) - len(stripped.lstrip("-"))
    trailing = len(stripped) - len(stripped.rstrip("-"))
    return (
        leading >= 1 and trailing >= 1 and stripped[leading : len(stripped) - trailing].strip().casefold() == "original message"
    )


@dataclass(frozen=True)
class ReplyContext:
    """Best-effort inferred context from embedded quoted headers."""

    from_email: str
    to_emails: list[str]
    subject: str
    date: str
    source: str
    confidence: float


def _extract_identity_addresses(addresses: list[str]) -> list[str]:
    """Extract normalized email identities from mail-header values."""
    identities: list[str] = []
    for raw in addresses:
        for address in _parse_address_list(raw):
            normalized = address.strip().lower()
            if normalized and normalized not in identities:
                identities.append(normalized)
    return identities


def _parse_reply_context_line(line: str) -> tuple[str, str] | None:
    """Parse one normalized mail-header line inside a quoted reply block."""
    raw_label, separator, raw_value = line.strip().partition(":")
    if not separator:
        return None
    label = _RE_REPLY_CONTEXT_LABELS.get(raw_label.strip().casefold())
    if not label:
        return None
    return label, raw_value.strip()


def _candidate_surfaces(body_text: str, body_html: str) -> list[tuple[str, str]]:
    """Build normalized candidate surfaces in priority order."""
    candidates: list[tuple[str, str]] = []
    if body_text.strip():
        if _looks_like_html(body_text):
            candidates.append(("body_text_html", _html_to_text(body_text)))
        else:
            candidates.append(("body_text", _clean_text(body_text)))
    if body_html.strip():
        candidates.append(("body_html", _html_to_text(body_html)))
    return candidates


def _collect_header_block(lines: list[str], start_index: int) -> tuple[dict[str, str], int]:
    """Collect one contiguous header block, supporting wrapped continuation lines."""
    block: dict[str, str] = {}
    header_count = 0
    current_label = ""

    for pos in range(start_index, min(len(lines), start_index + 12)):
        current = lines[pos].rstrip()
        stripped = current.strip()
        if not stripped:
            if header_count >= 3:
                break
            continue

        parsed = _parse_reply_context_line(stripped)
        if parsed:
            current_label, current_value = parsed
            header_count += 1
            block.setdefault(current_label, current_value)
            continue

        if current_label and current.startswith((" ", "\t")):
            block[current_label] = f"{block[current_label]} {stripped}".strip()
            continue

        if header_count >= 3:
            break
        return {}, 0

    return block, header_count


def extract_reply_context(body_text: str, body_html: str, email_type: str) -> ReplyContext | None:
    """Extract inferred reply-context fields from embedded mail-header blocks."""
    if email_type == "original":
        return None

    for source, text in _candidate_surfaces(body_text, body_html):
        context = _reply_context_from_lines(text.splitlines(), source)
        if context:
            return context
    return None


def _reply_context_from_lines(lines: list[str], source: str) -> ReplyContext | None:
    for idx, line in enumerate(lines):
        start_index, confidence = _reply_block_start(line, idx)
        if start_index is None:
            continue
        block, header_count = _collect_header_block(lines, start_index)
        if header_count < 3:
            continue
        reply_from = _extract_identity_addresses([block.get("from", "")])
        reply_to = _extract_identity_addresses([block.get("to", "")])
        subject = _decode_mime_words(block.get("subject", "")).strip()
        date = _normalize_date(block.get("date", ""))
        if reply_from or reply_to or subject or date:
            return ReplyContext(
                from_email=reply_from[0] if reply_from else "",
                to_emails=reply_to,
                subject=subject,
                date=date,
                source=source,
                confidence=confidence,
            )
    return None


def _reply_block_start(line: str, index: int) -> tuple[int | None, float]:
    parsed = _parse_reply_context_line(line)
    if parsed and parsed[0] in {"from", "sent"}:
        return index, 0.8
    if _is_reply_wrapper_line(line) or _is_reply_separator_line(line):
        return index + 1, 0.65
    return None, 0.8
