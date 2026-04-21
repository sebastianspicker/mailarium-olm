"""
Parse .olm (Outlook for Mac) archive files.

OLM files are ZIP archives containing XML-formatted email messages.
Structure: Accounts/<email>/com.microsoft.__Messages/<folder>/<message>.xml

Supports two OLM variants:
- Namespaced XML (older Outlook for Mac, namespace: http://schemas.microsoft.com/outlook/mac/2011)
- Non-namespaced XML (newer Outlook for Mac, plain element names)

When structured XML elements are missing (e.g. Inbox emails with only
OPFMessageCopySource), fields are extracted from the raw RFC 2822 headers.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Generator
from dataclasses import dataclass, field
from functools import cached_property

from .body_recovery import BodyRecovery, classify_body_state
from .conversation_segments import ConversationSegment
from .html_converter import clean_text as _clean_text  # noqa: F401 - re-exported for backward compat
from .html_converter import html_to_text as _html_to_text  # noqa: F401 - re-exported for backward compat
from .olm_xml_helpers import (
    _NS_OUTLOOK,  # noqa: F401 — re-exported for backward compat
    _extract_attachment_field,  # noqa: F401 — re-exported for backward compat
    _parse_address_element,  # noqa: F401 — re-exported for backward compat
)
from .olm_xml_helpers import (
    _read_limited_bytes as _read_limited_bytes_impl,
)
from .parse_olm_normalization import (
    BODY_NORMALIZATION_VERSION,  # noqa: F401 - re-exported for backward compat
    NormalizedBody,
    _normalize_preview_candidate,  # noqa: F401 - re-exported for backward compat
    _select_normalized_body,
    _strip_normalized_leading_forward_header_block,
    _strip_normalized_quoted_content,
    _strip_normalized_reply_header_tail,
)
from .parse_olm_postprocess import (
    ParsedEmailEnrichments as _ParsedEmailEnrichments,
)
from .parse_olm_postprocess import (
    ParsedEmailParts as _ParsedEmailParts,
)
from .parse_olm_postprocess import (
    apply_source_header_fallbacks as _apply_source_header_fallbacks_impl,
)
from .parse_olm_postprocess import (
    derive_email_enrichments as _derive_email_enrichments_impl,
)
from .parse_olm_postprocess import (
    finalize_parsed_email_parts as _finalize_parsed_email_parts_impl,
)
from .parse_olm_xml_parser import (
    build_parsed_email_from_parts_impl as _build_parsed_email_from_parts_impl,
)
from .parse_olm_xml_parser import parse_email_xml_impl as _parse_email_xml_impl
from .parse_olm_xml_parser import parse_olm_archive_impl as _parse_olm_archive_impl
from .rfc2822 import (
    _calendar_to_text,  # noqa: F401 — re-exported for backward compat (used by tests)
    _extract_body_from_source,  # noqa: F401 — re-exported for backward compat (used by tests)
    _extract_email_from_header,  # noqa: F401 — re-exported for backward compat (used by tests)
    _extract_header,  # noqa: F401 — re-exported for backward compat (used by tests)
    _extract_name_from_header,  # noqa: F401 — re-exported for backward compat (used by tests)
    _parse_address_list,
)

logger = logging.getLogger(__name__)
MAX_XML_BYTES = int(os.environ.get("OLM_MAX_XML_BYTES", 50_000_000))  # 50 MB default
MAX_XML_FILES = int(os.environ.get("OLM_MAX_XML_FILES", 500_000))
MAX_TOTAL_XML_BYTES = 20_000_000_000  # 20 GB — safe because parse_olm is a generator

# Stable compatibility seam for older imports and direct tests.
_read_limited_bytes = _read_limited_bytes_impl


_RE_FW_PREFIX = re.compile(
    r"^(RE|AW|FW|WG|SV|VS|Antw|Doorst)\s*:\s*",
    re.IGNORECASE,
)


def _extract_identity_addresses(addresses: list[str]) -> list[str]:
    """Extract normalized email identities from parsed recipient strings."""
    identities: list[str] = []
    for raw in addresses:
        for address in _parse_address_list(raw):
            normalized = address.strip().lower()
            if normalized and normalized not in identities:
                identities.append(normalized)
    return identities


def _classify_email_type(subject: str, in_reply_to: str) -> str:
    """Classify email type from stable message-level metadata only."""
    subj = (subject or "").strip()
    prefix_match = _RE_FW_PREFIX.match(subj)
    if prefix_match:
        prefix = prefix_match.group(1).upper()
        if prefix in ("FW", "WG", "DOORST", "VS"):
            return "forward"
        return "reply"
    if in_reply_to:
        return "reply"
    return "original"


@dataclass
class Email:
    """Represents a single parsed email."""

    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    date: str  # ISO format string
    body_text: str
    body_html: str
    folder: str
    has_attachments: bool
    preview_text: str = ""
    raw_body_text: str = ""
    raw_body_html: str = ""
    raw_source: str = ""
    raw_source_headers: dict[str, str] = field(default_factory=dict)
    forensic_body_text: str = ""
    forensic_body_source: str = ""
    to_identities: list[str] = field(default_factory=list)
    cc_identities: list[str] = field(default_factory=list)
    bcc_identities: list[str] = field(default_factory=list)
    recipient_identity_source: str = ""
    attachment_names: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    conversation_id: str = ""
    in_reply_to: str = ""
    references: list[str] = field(default_factory=list)
    reply_context_from: str = ""
    reply_context_to: list[str] = field(default_factory=list)
    reply_context_subject: str = ""
    reply_context_date: str = ""
    reply_context_source: str = ""
    segments: list[ConversationSegment] = field(default_factory=list)
    inferred_parent_uid: str = ""
    inferred_thread_id: str = ""
    inferred_match_reason: str = ""
    inferred_match_confidence: float = 0.0
    priority: int = 0  # 0 = normal
    is_read: bool = True
    attachment_contents: list[tuple[str, bytes]] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    thread_topic: str = ""
    thread_index: str = ""
    inference_classification: str = ""  # "Focused" / "Other"
    is_calendar_message: bool = False
    meeting_data: dict = field(default_factory=dict)
    exchange_extracted_links: list[dict] = field(default_factory=list)
    exchange_extracted_emails: list[str] = field(default_factory=list)
    exchange_extracted_contacts: list[str] = field(default_factory=list)
    exchange_extracted_meetings: list[dict] = field(default_factory=list)

    @property
    def uid(self) -> str:
        """Stable unique ID for deduplication.

        When ``message_id`` is available, hashes it directly.  For the
        fallback case (no Message-ID), includes a body hash to reduce
        collision risk when subject+date+sender are identical.
        """
        if self.message_id:
            return hashlib.md5(self.message_id.encode(), usedforsecurity=False).hexdigest()
        body_snippet = (self.body_text or "")[:500]
        key = f"{self.subject}|{self.date}|{self.sender_email}|{body_snippet}"
        return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()

    @property
    def email_type(self) -> str:
        """Classify email as 'reply', 'forward', or 'original'.

        Uses subject prefix first, then falls back to ``in_reply_to``
        for implicit replies that lack a RE:/AW: prefix.
        """
        return _classify_email_type(self.subject, self.in_reply_to)

    @property
    def base_subject(self) -> str:
        """Subject with RE:/FW:/AW:/WG: prefixes stripped for thread grouping."""
        subj = (self.subject or "").strip()
        while True:
            match = _RE_FW_PREFIX.match(subj)
            if not match:
                break
            subj = subj[match.end() :].strip()
        return subj

    @property
    def clean_body(self) -> str:
        """Best available plain text body, with HTML stripped."""
        return self.normalized_body.text

    @property
    def body_kind(self) -> str:
        """Classify whether the stored body contains user-visible content."""
        return self.body_recovery.body_kind

    @property
    def body_empty_reason(self) -> str:
        """Explain why the normalized body needed recovery or stayed empty."""
        return self.body_recovery.body_empty_reason

    @property
    def recovery_strategy(self) -> str:
        """Which deterministic fallback populated the normalized body."""
        return self.body_recovery.recovery_strategy

    @property
    def recovery_confidence(self) -> float:
        """Confidence for the applied recovery strategy."""
        return self.body_recovery.recovery_confidence

    @cached_property
    def _normalized_body_base(self) -> NormalizedBody:
        """Derived normalized body before empty-body recovery."""
        normalized = _select_normalized_body(self.body_text or "", self.body_html or "")
        stripped_text = _strip_normalized_quoted_content(normalized.text, self.email_type)
        stripped_text = _strip_normalized_reply_header_tail(stripped_text, self.email_type)
        stripped_text = _strip_normalized_leading_forward_header_block(stripped_text, self.email_type)
        if stripped_text != normalized.text:
            normalized = NormalizedBody(stripped_text, normalized.source, normalized.version)
        return normalized

    @cached_property
    def body_recovery(self) -> BodyRecovery:
        """Classify and, when justified, recover an empty normalized body."""
        return classify_body_state(
            raw_body_text=self.raw_body_text or self.body_text or "",
            raw_body_html=self.raw_body_html or self.body_html or "",
            raw_source=self.raw_source or "",
            preview_text=self.preview_text or "",
            clean_body=self._normalized_body_base.text,
            email_type=self.email_type,
            has_attachments=self.has_attachments,
        )

    @cached_property
    def normalized_body(self) -> NormalizedBody:
        """Derived normalized body with source provenance."""
        normalized = self._normalized_body_base
        if normalized.text.strip():
            return normalized
        if self.body_recovery.recovered_text:
            return NormalizedBody(
                self.body_recovery.recovered_text,
                self.body_recovery.recovered_source,
                normalized.version,
            )
        return normalized

    @property
    def clean_body_source(self) -> str:
        """Which source representation produced ``clean_body``."""
        return self.normalized_body.source

    @property
    def body_normalization_version(self) -> int:
        """Version number for the body normalization pipeline."""
        return self.normalized_body.version

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "message_id": self.message_id,
            "subject": self.subject,
            "sender_name": self.sender_name,
            "sender_email": self.sender_email,
            "to": self.to,
            "cc": self.cc,
            "bcc": self.bcc,
            "to_identities": self.to_identities,
            "cc_identities": self.cc_identities,
            "bcc_identities": self.bcc_identities,
            "recipient_identity_source": self.recipient_identity_source,
            "date": self.date,
            "body": self.clean_body,
            "body_source": self.clean_body_source,
            "body_normalization_version": self.body_normalization_version,
            "body_kind": self.body_kind,
            "body_empty_reason": self.body_empty_reason,
            "recovery_strategy": self.recovery_strategy,
            "recovery_confidence": self.recovery_confidence,
            "raw_body_text": self.raw_body_text,
            "raw_body_html": self.raw_body_html,
            "raw_source": self.raw_source,
            "raw_source_headers": self.raw_source_headers,
            "forensic_body_text": self.forensic_body_text,
            "forensic_body_source": self.forensic_body_source,
            "folder": self.folder,
            "has_attachments": self.has_attachments,
            "attachment_names": self.attachment_names,
            "attachments": self.attachments,
            "attachment_count": len(self.attachment_names),
            "conversation_id": self.conversation_id,
            "in_reply_to": self.in_reply_to,
            "references": self.references,
            "reply_context_from": self.reply_context_from,
            "reply_context_to": self.reply_context_to,
            "reply_context_subject": self.reply_context_subject,
            "reply_context_date": self.reply_context_date,
            "reply_context_source": self.reply_context_source,
            "segments": [segment.to_dict() for segment in self.segments],
            "inferred_parent_uid": self.inferred_parent_uid,
            "inferred_thread_id": self.inferred_thread_id,
            "inferred_match_reason": self.inferred_match_reason,
            "inferred_match_confidence": self.inferred_match_confidence,
            "priority": self.priority,
            "is_read": self.is_read,
            "email_type": self.email_type,
            "base_subject": self.base_subject,
            "categories": self.categories,
            "thread_topic": self.thread_topic,
            "thread_index": self.thread_index,
            "inference_classification": self.inference_classification,
            "is_calendar_message": self.is_calendar_message,
            "meeting_data": self.meeting_data,
            "exchange_extracted_links": self.exchange_extracted_links,
            "exchange_extracted_emails": self.exchange_extracted_emails,
            "exchange_extracted_contacts": self.exchange_extracted_contacts,
            "exchange_extracted_meetings": self.exchange_extracted_meetings,
        }


def parse_olm(
    olm_path: str,
    extract_attachments: bool = False,
) -> Generator[Email, None, None]:
    """
    Parse an .olm file and yield Email objects.

    Args:
        olm_path: Path to the .olm file.
        extract_attachments: If True, extract binary attachment content
            and populate ``Email.attachment_contents``. Default False
            to avoid memory bloat.

    Yields:
        Email objects for each message found.
    """
    if not os.path.exists(olm_path):
        raise FileNotFoundError(f"OLM file not found: {olm_path}")

    yield from _parse_olm_archive_impl(
        olm_path,
        extract_attachments=extract_attachments,
        max_xml_files=MAX_XML_FILES,
        max_total_xml_bytes=MAX_TOTAL_XML_BYTES,
        max_xml_bytes=MAX_XML_BYTES,
        logger=logger,
        parse_email_xml_fn=_parse_email_xml,
    )


# ── Email XML Parsing ─────────────────────────────────────────


def _apply_source_header_fallbacks(parts: _ParsedEmailParts) -> None:
    _apply_source_header_fallbacks_impl(parts, extract_identity_addresses_fn=_extract_identity_addresses)


def _finalize_parsed_email_parts(parts: _ParsedEmailParts) -> None:
    _finalize_parsed_email_parts_impl(parts, extract_identity_addresses_fn=_extract_identity_addresses)


def _derive_email_enrichments(parts: _ParsedEmailParts, source_path: str) -> _ParsedEmailEnrichments:
    return _derive_email_enrichments_impl(parts, source_path, classify_email_type_fn=_classify_email_type)


def _build_parsed_email_from_parts(parts: _ParsedEmailParts, enrichments: _ParsedEmailEnrichments) -> Email:
    return _build_parsed_email_from_parts_impl(
        parts,
        enrichments,
        email_cls=Email,
    )


def _parse_email_xml(xml_bytes: bytes, source_path: str) -> Email | None:
    return _parse_email_xml_impl(
        xml_bytes,
        source_path,
        logger=logger,
        extract_identity_addresses_fn=_extract_identity_addresses,
        apply_source_header_fallbacks_fn=_apply_source_header_fallbacks,
        finalize_parsed_email_parts_fn=_finalize_parsed_email_parts,
        derive_email_enrichments_fn=_derive_email_enrichments,
        build_parsed_email_from_parts_fn=_build_parsed_email_from_parts,
    )
