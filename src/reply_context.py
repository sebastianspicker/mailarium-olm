"""Quoted reply-context extraction from embedded mail-header blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .html_converter import clean_text as _clean_text
from .html_converter import html_to_text as _html_to_text
from .html_converter import looks_like_html as _looks_like_html
from .rfc2822 import _decode_mime_words, _normalize_date, _parse_address_list

_RE_REPLY_CONTEXT_HEADER_LINE = re.compile(
    r"(?i)^(from|sent|to|cc|bcc|subject|date|"
    r"von|gesendet|an|betreff|"
    r"de|envoy[ée]|[àa]|objet|"
    r"asunto|para|enviado|assunto|"
    r"van|verzonden|onderwerp|"
    r"da|inviato|oggetto|"
    r"från|fra|skickat|sendt|till|til|emne|"
    r"od|do|wys[łl]ano|temat"
    r"):\s*(.+)$"
)

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
    match = _RE_REPLY_CONTEXT_HEADER_LINE.match(line.strip())
    if not match:
        return None
    label = _RE_REPLY_CONTEXT_LABELS.get(match.group(1).casefold())
    if not label:
        return None
    return label, match.group(2).strip()


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
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            parsed = _parse_reply_context_line(line)
            if not parsed:
                continue
            label, _value = parsed
            if label not in {"from", "sent"}:
                continue
            block, header_count = _collect_header_block(lines, idx)
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
                    confidence=0.8,
                )
    return None
