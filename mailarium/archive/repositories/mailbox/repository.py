"""Mailbox persistence composed from focused account, source, and proposal repositories."""

from __future__ import annotations

from pathlib import Path

from .accounts import MailboxAccountRepository
from .proposals import MailboxProposalRepository
from .session import MailboxSession
from .sources import MailboxSourceRepository


class MailboxRepository:
    """Account, source/cursor, and proposal repositories over one mailbox session.

    ``ArchiveDatabase.mailbox`` binds this to the archive connection and lock.
    :meth:`open_standalone` keeps a separate mailbox-state file for callers
    that operate without a canonical archive.
    """

    def __init__(self, session: MailboxSession) -> None:
        self._session = session
        self.accounts = MailboxAccountRepository(session)
        self.sources = MailboxSourceRepository(session)
        self.proposals = MailboxProposalRepository(session)

    @classmethod
    def open_standalone(cls, path: str | Path) -> MailboxRepository:
        """Open mailbox state in its own SQLite file; the caller must :meth:`close` it."""
        return cls(MailboxSession.standalone(path))

    def close(self) -> None:
        """Close a standalone connection; a shared archive connection stays open."""
        self._session.close()


__all__ = ["MailboxRepository"]
