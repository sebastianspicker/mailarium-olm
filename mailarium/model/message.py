import hashlib
import re
from dataclasses import dataclass, field
from functools import cached_property

from mailarium.model.body_normalization import (
    NormalizedBody,
    _select_normalized_body,
    _strip_normalized_leading_forward_header_block,
    _strip_normalized_quoted_content,
    _strip_normalized_reply_header_tail,
)

from .body_recovery import BodyRecovery, classify_body_state
from .conversation_segments import ConversationSegment

MESSAGE_UID_VERSION = 1
"""Version of the immutable message UID derivation contract."""

MESSAGE_UID_ALGORITHM = "sha256-v1"
"""Algorithm identifier persisted implicitly by the current UID values."""

_RE_FW_PREFIX = re.compile(
    r"^(RE|AW|FW|WG|SV|VS|Antw|Doorst)\s*:\s*",
    re.IGNORECASE,
)


def classify_message_type(subject: str, in_reply_to: str) -> str:
    """Classify replies and forwards from localized prefixes and reply metadata."""
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


def canonical_message_uid(
    message_id: str,
    subject: str,
    date: str,
    sender_email: str,
    body_text: str,
    *,
    override: str = "",
) -> str:
    """Return the frozen v1 UID used for deduplication and persisted references.

    This intentionally preserves the pre-model-extraction SHA-256 input format.
    Changing it would invalidate existing UIDs and archive deduplication.
    """
    if override:
        return override
    if message_id:
        return hashlib.sha256(message_id.encode()).hexdigest()
    body_snippet = (body_text or "")[:500]
    key = f"{subject}|{date}|{sender_email}|{body_snippet}"
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass
class Message:
    """A durable mailbox message independent of any archive or transport parser."""

    message_id: str
    subject: str
    sender_name: str
    sender_email: str
    to: list[str]
    cc: list[str]
    bcc: list[str]
    date: str
    body_text: str
    body_html: str
    folder: str
    has_attachments: bool
    to_identities: list[str] = field(default_factory=list)
    cc_identities: list[str] = field(default_factory=list)
    bcc_identities: list[str] = field(default_factory=list)
    recipient_identity_source: str = ""
    forensic_body_text: str = ""
    forensic_body_source: str = ""
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
    priority: int = 0
    is_read: bool = True
    categories: list[str] = field(default_factory=list)
    thread_topic: str = ""
    thread_index: str = ""
    inference_classification: str = ""
    is_calendar_message: bool = False
    meeting_data: dict = field(default_factory=dict)
    exchange_extracted_links: list[dict] = field(default_factory=list)
    exchange_extracted_emails: list[str] = field(default_factory=list)
    exchange_extracted_contacts: list[str] = field(default_factory=list)
    exchange_extracted_meetings: list[dict] = field(default_factory=list)
    canonical_uid_override: str = ""

    # Parser-specific payload is owned by ingestion. Durable messages retain
    # empty source surfaces when reconstructed from storage.
    source_folders: list[str] = field(default_factory=list, init=False)
    preview_text: str = field(default="", init=False)
    raw_body_text: str = field(default="", init=False)
    raw_body_html: str = field(default="", init=False)
    raw_source: str = field(default="", init=False)
    raw_source_headers: dict[str, str] = field(default_factory=dict, init=False)
    attachment_contents: list[tuple[str, bytes]] = field(default_factory=list, init=False)

    @property
    def uid(self) -> str:
        """Stable v1 unique ID for deduplication."""
        return canonical_message_uid(
            self.message_id,
            self.subject,
            self.date,
            self.sender_email,
            self.body_text,
            override=self.canonical_uid_override,
        )

    @property
    def email_type(self) -> str:
        """Compatibility name for the durable message classification."""
        return classify_message_type(self.subject, self.in_reply_to)

    @property
    def base_subject(self) -> str:
        """Subject with reply and forward prefixes stripped for thread grouping."""
        subject = (self.subject or "").strip()
        while True:
            match = _RE_FW_PREFIX.match(subject)
            if not match:
                break
            subject = subject[match.end() :].strip()
        return subject

    @property
    def clean_body(self) -> str:
        """Best available plain text body, with HTML stripped."""
        return self.normalized_body.text

    @property
    def body_kind(self) -> str:
        return self.body_recovery.body_kind

    @property
    def body_empty_reason(self) -> str:
        return self.body_recovery.body_empty_reason

    @property
    def recovery_strategy(self) -> str:
        return self.body_recovery.recovery_strategy

    @property
    def recovery_confidence(self) -> float:
        return self.body_recovery.recovery_confidence

    @cached_property
    def _normalized_body_base(self) -> NormalizedBody:
        normalized = _select_normalized_body(self.body_text or "", self.body_html or "")
        stripped_text = _strip_normalized_quoted_content(normalized.text, self.email_type)
        stripped_text = _strip_normalized_reply_header_tail(stripped_text, self.email_type)
        stripped_text = _strip_normalized_leading_forward_header_block(stripped_text, self.email_type)
        if stripped_text != normalized.text:
            normalized = NormalizedBody(stripped_text, normalized.source, normalized.version)
        return normalized

    @cached_property
    def body_recovery(self) -> BodyRecovery:
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
        return self.normalized_body.source

    @property
    def body_normalization_version(self) -> int:
        return self.normalized_body.version

    def to_dict(self) -> dict:
        """Expose the message as JSON-compatible report data."""
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
