"""Public persistence facade composed from focused mailbox repositories."""

from __future__ import annotations

from mailarium.archive.mailbox_schema import MAILBOX_SCHEMA_SQL, ensure_mailbox_schema_compatibility, initialize_mailbox_schema

from .store_accounts import MailboxAccountRepository
from .store_proposals import MailboxProposalRepository
from .store_sources import MailboxSourceRepository

__all__ = ["MAILBOX_SCHEMA_SQL", "MailboxStore", "ensure_mailbox_schema_compatibility", "initialize_mailbox_schema"]


class MailboxStore(MailboxAccountRepository, MailboxSourceRepository, MailboxProposalRepository):
    """Transactional composition of account, source, cursor, and proposal repositories."""
