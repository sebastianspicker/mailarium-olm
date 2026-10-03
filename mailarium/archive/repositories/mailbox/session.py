"""Connection, lock, and write-transaction state shared by mailbox repositories.

Mailbox persistence has no transport dependency. Source adapters own EWS,
Graph, or local-file calls and supply only stable source identities/change keys.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Protocol

from ...schema.mailbox import initialize_mailbox_schema
from ...session import ArchiveSession


class MailboxSession:
    """Small transactional state layer for source adapters and action executors.

    In shared mode the session uses the archive's connection and the archive's
    single operation lock, so mailbox writes serialize with every archive
    repository.  In standalone mode it owns one SQLite file and its own lock.
    Writes always run under the lock inside ``BEGIN IMMEDIATE``; reads run on
    the connection without taking the lock, as they always have.
    """

    def __init__(
        self,
        connection: Callable[[], sqlite3.Connection],
        operation: Callable[[], AbstractContextManager[object]],
        *,
        owned_connection: sqlite3.Connection | None = None,
        archive: ArchiveSession | None = None,
    ) -> None:
        self._connection = connection
        self._operation_context = operation
        self._owned_connection = owned_connection
        self.archive = archive
        self._batch_cursor: sqlite3.Cursor | None = None
        self.initialize()

    @classmethod
    def shared(cls, archive: ArchiveSession) -> MailboxSession:
        """Bind mailbox persistence to the archive connection and its operation lock."""
        return cls(lambda: archive.conn, archive.operation, archive=archive)

    @classmethod
    def standalone(cls, path: str | Path) -> MailboxSession:
        """Open a separate mailbox-state SQLite file whose lifetime this session owns."""
        connection = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        lock = threading.RLock()
        return cls(lambda: connection, lambda: lock, owned_connection=connection)

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the connection that stores mailbox state."""
        return self._connection()

    def close(self) -> None:
        """Close the SQLite connection when this session created and owns it."""
        if self._owned_connection is not None:
            self._owned_connection.close()

    def initialize(self) -> None:
        """Install the mailbox schema within the session's serialized operation context."""
        with self._operation_context():
            initialize_mailbox_schema(self.conn)

    @contextmanager
    def batch_write(self) -> Iterator[None]:
        """Commit related source writes once, rolling back the batch on failure."""
        with self.write() as cur:
            if self._batch_cursor is not None:
                raise RuntimeError("mailbox write batches cannot be nested")
            self._batch_cursor = cur
            try:
                yield
            finally:
                self._batch_cursor = None

    @contextmanager
    def write(self) -> Iterator[sqlite3.Cursor]:
        """Run one write under the lock, joining an open batch or owning a ``BEGIN IMMEDIATE`` transaction."""
        with self._operation_context():
            if self._batch_cursor is not None:
                yield self._batch_cursor
                return
            cur = self.conn.cursor()
            try:
                cur.execute("BEGIN IMMEDIATE")
                yield cur
            except BaseException:
                self.conn.rollback()
                raise
            else:
                self.conn.commit()


class SessionOwner(Protocol):
    """Archive facade that can confirm whether it hosts a mailbox session."""

    def owns_mailbox_session(self, session: MailboxSession) -> bool: ...


class MailboxSessionRepository:
    """Base for mailbox repositories that share one :class:`MailboxSession`."""

    def __init__(self, session: MailboxSession) -> None:
        self._session = session

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the connection that stores mailbox state."""
        return self._session.conn

    def shares_archive(self, database: SessionOwner) -> bool:
        """Return whether this mailbox state uses ``database``'s connection and operation lock."""
        return database.owns_mailbox_session(self._session)

    def batch_write(self) -> AbstractContextManager[None]:
        """Group related writes into one transaction committed at the end of the block."""
        return self._session.batch_write()

    def _write(self) -> AbstractContextManager[sqlite3.Cursor]:
        return self._session.write()
