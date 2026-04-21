"""Post-processing helpers for parsed OLM email fields."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .body_forensics import render_forensic_text
from .conversation_segments import ConversationSegment, extract_segments
from .olm_xml_helpers import _parse_references
from .reply_context import extract_reply_context
from .rfc2822 import (
    _decode_mime_words,
    _extract_body_from_source,
    _extract_email_from_header,
    _extract_header,
    _extract_name_from_header,
    _normalize_date,
    _parse_address_list,
)

logger = logging.getLogger(__name__)


@dataclass
class ParsedEmailParts:
    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]
    to_identities: list[str]
    cc_identities: list[str]
    bcc_identities: list[str]
    recipient_identity_source: str
    date: str
    body_text: str
    body_html: str
    folder: str
    preview: str
    raw_body_text: str
    raw_body_html: str
    raw_source: str
    raw_source_headers: dict[str, str]
    attachment_names: list[dict] | list[str]
    attachments: list[dict]
    conversation_id: str
    in_reply_to: str
    references: list[str]
    priority: int
    is_read: bool
    categories: list[str]
    thread_topic: str
    thread_index: str
    inference_classification: str
    is_calendar_message: bool
    meeting_data: dict
    exchange_extracted_links: list[dict]
    exchange_extracted_emails: list[str]
    exchange_extracted_contacts: list[str]
    exchange_extracted_meetings: list[dict]


@dataclass
class ParsedEmailEnrichments:
    forensic_body_text: str
    forensic_body_source: str
    email_type: str
    reply_context_from: str = ""
    reply_context_to: list[str] = field(default_factory=list)
    reply_context_subject: str = ""
    reply_context_date: str = ""
    reply_context_source: str = ""
    segments: list[ConversationSegment] = field(default_factory=list)


def apply_source_header_fallbacks(
    parts: ParsedEmailParts,
    *,
    extract_identity_addresses_fn: Any,
) -> None:
    """Fill missing fields from the raw RFC 2822 source headers."""
    if not parts.raw_source:
        return

    if not parts.message_id:
        parts.message_id = _extract_header(parts.raw_source, "Message-ID").strip("<>")
    if not parts.subject:
        parts.subject = _extract_header(parts.raw_source, "Subject")
    if not parts.sender_email:
        parts.sender_email = _extract_email_from_header(parts.raw_source, "From")
    if not parts.sender_name:
        parts.sender_name = _extract_name_from_header(parts.raw_source, "From")
    if not parts.date:
        parts.date = _normalize_date(_extract_header(parts.raw_source, "Date"))
    if not parts.to_addresses:
        to_raw = _extract_header(parts.raw_source, "To")
        if to_raw:
            parts.to_addresses = _parse_address_list(to_raw)
    elif not parts.to_identities:
        to_raw = _extract_header(parts.raw_source, "To")
        if to_raw:
            parts.to_identities = extract_identity_addresses_fn([to_raw])
            if parts.to_identities:
                parts.recipient_identity_source = "source_header"
    if not parts.cc_addresses:
        cc_raw = _extract_header(parts.raw_source, "CC")
        if cc_raw:
            parts.cc_addresses = _parse_address_list(cc_raw)
    if not parts.cc_identities and parts.cc_addresses:
        parts.cc_identities = extract_identity_addresses_fn(parts.cc_addresses)
    if not parts.bcc_addresses:
        bcc_raw = _extract_header(parts.raw_source, "BCC")
        if bcc_raw:
            parts.bcc_addresses = _parse_address_list(bcc_raw)
    if not parts.bcc_identities and parts.bcc_addresses:
        parts.bcc_identities = extract_identity_addresses_fn(parts.bcc_addresses)
    if not parts.in_reply_to:
        parts.in_reply_to = _extract_header(parts.raw_source, "In-Reply-To").strip("<>")
    if not parts.references:
        refs_raw = _extract_header(parts.raw_source, "References")
        if refs_raw:
            parts.references = _parse_references(refs_raw)


def finalize_parsed_email_parts(
    parts: ParsedEmailParts,
    *,
    extract_identity_addresses_fn: Any,
) -> None:
    """Apply deterministic recipient, body, and normalization fallbacks."""
    if not parts.to_identities and parts.to_addresses:
        parts.to_identities = extract_identity_addresses_fn(parts.to_addresses)
    if not parts.cc_identities and parts.cc_addresses:
        parts.cc_identities = extract_identity_addresses_fn(parts.cc_addresses)
    if not parts.bcc_identities and parts.bcc_addresses:
        parts.bcc_identities = extract_identity_addresses_fn(parts.bcc_addresses)
    if not parts.recipient_identity_source and (parts.to_identities or parts.cc_identities or parts.bcc_identities):
        parts.recipient_identity_source = "parsed_addresses"

    if not parts.body_text and not parts.body_html and parts.raw_source:
        parts.body_text, parts.body_html = _extract_body_from_source(parts.raw_source)

    if not parts.body_text and not parts.body_html and parts.preview:
        parts.body_text = parts.preview

    parts.subject = _decode_mime_words(parts.subject) if parts.subject else ""
    parts.sender_name = _decode_mime_words(parts.sender_name) if parts.sender_name else ""
    parts.sender_email = parts.sender_email.strip().lower() if parts.sender_email else ""

    if not parts.subject:
        parts.subject = "(no subject)"


def derive_email_enrichments(
    parts: ParsedEmailParts,
    source_path: str,
    *,
    classify_email_type_fn: Any,
) -> ParsedEmailEnrichments:
    """Derive forensic, reply-context, and segmentation enrichments."""
    forensic_body = render_forensic_text(parts.raw_body_text, parts.raw_body_html, parts.raw_source)
    email_type = classify_email_type_fn(parts.subject, parts.in_reply_to)

    reply_context = None
    if email_type in {"reply", "forward"}:
        reply_context = extract_reply_context(parts.body_text, parts.body_html, email_type)

    try:
        segments = extract_segments(parts.body_text, parts.body_html, parts.raw_source, email_type)
    except Exception:  # pragma: no cover - defensive guard for optional enrichment
        logger.exception("Failed to segment conversation body for %s", source_path)
        segments = []

    return ParsedEmailEnrichments(
        forensic_body_text=forensic_body.text,
        forensic_body_source=forensic_body.source,
        email_type=email_type,
        reply_context_from=reply_context.from_email if reply_context else "",
        reply_context_to=reply_context.to_emails if reply_context else [],
        reply_context_subject=reply_context.subject if reply_context else "",
        reply_context_date=reply_context.date if reply_context else "",
        reply_context_source=reply_context.source if reply_context else "",
        segments=segments,
    )
