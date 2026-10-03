"""Canonical SQLite archive database for messages and investigative records."""

from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager, suppress

from .connection import ArchiveConnection
from .locking import archive_repository
from .repositories.analytics import AnalyticsRepository
from .repositories.attachments import AttachmentRepository
from .repositories.custody import CustodyRepository
from .repositories.diagnostics import DiagnosticsRepository
from .repositories.entities import EntityRepository
from .repositories.events import EventRepository
from .repositories.evidence import EvidenceRepository
from .repositories.ingest_ledger import IngestLedgerRepository
from .repositories.mailbox.repository import MailboxRepository
from .repositories.mailbox.session import MailboxSession
from .repositories.messages import MessageRepository
from .repositories.queries import MessageQueryRepository
from .repositories.sparse import SparseVectorRepository
from .repositories.vector_maintenance import VectorMaintenanceRepository
from .repositories.visibility import MailboxVisibilityRepository
from .session import ArchiveSession


@archive_repository
class ArchiveDatabase:
    """Canonical local archive: one SQLite session shared by focused repositories.

    ``ArchiveDatabase`` owns the archive connection, the single re-entrant
    operation lock, and the explicit transaction boundary.  Each repository
    attribute receives the same :class:`ArchiveSession`, so every public
    repository operation serializes on that one lock:

    - ``messages``: canonical message inserts and mutable-field refreshes
    - ``queries``: message counts, browsing, full records, threads, segments
    - ``attachments``: attachment rows, surfaces, statistics, and search
    - ``evidence``: evidence items, quote verification, and evidence provenance
    - ``custody``: chain-of-custody events and email provenance
    - ``ingest_ledger``: ingestion runs, checkpoints, and per-message ingest state
    - ``entities`` / ``events``: extracted entities and event records
    - ``analytics``: clusters, topics, contacts, temporal, language, sentiment
    - ``sparse``: packed sparse-vector rows
    - ``vector_maintenance``: body-vector provenance and vector-state resets
    - ``diagnostics``: read-only corpus diagnostics
    - ``visibility``: mailbox source visibility for default retrieval
    - ``mailbox``: mailbox accounts, sources, cursors, and action proposals
    """

    def __init__(self, db_path: str = ":memory:", *, busy_timeout_ms: int = 5000) -> None:
        """Open the SQLite archive path lazily and compose repositories over one session."""
        self._session = ArchiveSession(ArchiveConnection(db_path, busy_timeout_ms=busy_timeout_ms))
        session = self._session
        self.custody = CustodyRepository(session)
        self.attachments = AttachmentRepository(session)
        self.evidence = EvidenceRepository(session, custody=self.custody)
        self.ingest_ledger = IngestLedgerRepository(session, custody=self.custody)
        self.messages = MessageRepository(session, attachments=self.attachments)
        self.queries = MessageQueryRepository(session, attachments=self.attachments)
        self.entities = EntityRepository(session)
        self.events = EventRepository(session)
        self.analytics = AnalyticsRepository(session)
        self.sparse = SparseVectorRepository(session)
        self.vector_maintenance = VectorMaintenanceRepository(session)
        self.diagnostics = DiagnosticsRepository(session)
        self.visibility = MailboxVisibilityRepository(session)
        self._mailbox: MailboxRepository | None = None

    def operation(self) -> AbstractContextManager[None]:
        """Hold the explicit archive-operation lock for one complete call."""
        return self._session.operation()

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the shared connection owned by this archive."""
        return self._session.conn

    @property
    def mailbox(self) -> MailboxRepository:
        """Return mailbox persistence bound to this archive's connection and operation lock.

        The repository is created on first use, which opens the connection and
        confirms the mailbox tables exactly as a newly constructed store would.
        """
        with self._session.operation():
            if self._mailbox is None:
                self._mailbox = MailboxRepository(MailboxSession.shared(self._session))
            return self._mailbox

    def owns_mailbox_session(self, session: MailboxSession) -> bool:
        """Return whether ``session`` is bound to this archive's connection and operation lock."""
        return session.archive is self._session

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._session.close()

    def __enter__(self) -> ArchiveDatabase:
        """Enter an explicitly managed archive lifetime."""
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Close the archive connection at the end of a managed lifetime."""
        self.close()

    def __del__(self) -> None:
        """Best-effort close to avoid leaked SQLite handles during teardown."""
        with suppress(OSError, sqlite3.Error):
            self.close()

    # ------------------------------------------------------------------
    # Explicit transaction boundary for multi-call units of work

    def begin_immediate(self) -> None:
        """Open a write transaction that the caller completes with ``commit`` or ``rollback``."""
        self.conn.execute("BEGIN IMMEDIATE")

    def commit(self) -> None:
        """Commit writes deferred by ``commit=False`` repository calls."""
        self.conn.commit()

    def rollback(self) -> None:
        """Discard writes deferred by ``commit=False`` repository calls."""
        self.conn.rollback()

    def checkpoint_wal_passive(self) -> None:
        """Run a passive WAL checkpoint without blocking concurrent readers or writers."""
        self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")

    def change_revision(self) -> tuple[int, int]:
        """Return a revision token that changes after local or external archive writes."""
        conn = self.conn
        return int(conn.total_changes), int(conn.execute("PRAGMA data_version").fetchone()[0])


__all__ = ["ArchiveDatabase"]
