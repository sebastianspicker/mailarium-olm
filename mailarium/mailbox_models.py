"""Source-neutral, immutable mailbox state records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProposalState(StrEnum):
    """Enumerate the durable lifecycle states for a mailbox action proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    RETRYABLE = "retryable"
    CONFLICTED = "conflicted"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ActorKind(StrEnum):
    """Identify the trusted actor category recorded for mailbox actions."""

    ASSISTANT = "assistant"
    HUMAN = "human"
    SYSTEM = "system"
    SERVER = "assistant"  # compatibility spelling
    USER = "human"  # compatibility spelling


@dataclass(frozen=True)
class MailboxMessageRecord:
    """A source-neutral mailbox item; source identifiers remain external mappings."""

    account_id: str
    folder_id: str
    source: str
    source_identity: str
    canonical_email_uid: str = ""
    remote_item_id: str = ""
    subject: str = ""
    received_at: str = ""
    internet_message_id: str = ""
    sender_name: str = ""
    sender_email: str = ""
    to: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    body_text: str = ""
    body_html: str = ""
    is_read: bool = True
    importance: str = "Normal"
    categories: tuple[str, ...] = ()
    conversation_id: str = ""
    in_reply_to: str = ""
    attachments: tuple[Mapping[str, Any], ...] = ()
    attachment_contents: tuple[tuple[str, bytes], ...] = ()
    change_key: str = ""
    is_tombstone: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MailboxActionProposal:
    """Store immutable requested action data and its approval lifecycle state."""

    proposal_id: str
    account_id: str
    folder_id: str
    operation: str
    target_identity: str
    target_change_key: str
    proposal_digest: str
    state: ProposalState
    proposer_kind: ActorKind
    created_at: str
    expires_at: str
    approved_at: str | None = None
    execution_deadline: str | None = None
    target: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MailboxActionClaim:
    """Represent the exclusive execution lease for an approved mailbox proposal."""

    proposal: MailboxActionProposal
    attempt_id: int
    claimed_at: str
    execution_deadline: str


@dataclass(frozen=True)
class MailboxActionOutcome:
    """Describe the persisted result of one mailbox proposal execution attempt."""

    proposal_id: str
    state: ProposalState
    detail: Mapping[str, Any] = field(default_factory=dict)
