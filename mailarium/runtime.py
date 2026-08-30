"""Application composition and lifecycle ownership for one local archive."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from mailarium.archive import ArchiveDatabase, open_archive_database
from mailarium.config import Settings, resolve_runtime_settings
from mailarium.mailbox.mailbox_service import MailboxService
from mailarium.mailbox.mailbox_store import MailboxStore
from mailarium.retrieval.embedder import EmailEmbedder
from mailarium.retrieval.retriever import SearchEngine


class ApplicationRuntime:
    """Own the archive database and services for one validated path pair.

    The runtime opens SQLite only when a caller needs it.  A missing archive
    therefore remains distinguishable from a newly created one, while every
    service that is created for an existing archive shares the same
    :class:`ArchiveDatabase` connection.  Callers that create a mailbox store
    explicitly can request ``open_archive_database()``.

    ``close()`` is the sole owner shutdown operation: it closes derived search
    resources first and the canonical archive connection last.  Services
    receive the archive as an externally owned dependency and never close it.
    """

    def __init__(
        self,
        *,
        vector_index_path: str | None = None,
        sqlite_path: str | None = None,
        sparse_enabled: bool | None = None,
        image_search_enabled: bool | None = None,
    ) -> None:
        self.settings: Settings = resolve_runtime_settings(
            vector_index_path=vector_index_path,
            sqlite_path=sqlite_path,
            sparse_enabled=sparse_enabled,
            image_search_enabled=image_search_enabled,
        )
        self.vector_index_path = self.settings.vector_index_path
        self.sqlite_path = self.settings.sqlite_path
        self._archive_database: ArchiveDatabase | None = None
        self._search_engine: SearchEngine | None = None
        self._mailbox_service: MailboxService | None = None
        self._closed = False
        self._lifecycle_lock = RLock()

    @property
    def archive_database(self) -> ArchiveDatabase | None:
        """Return the existing archive database without creating a new file."""
        return self._database(create=False)

    def open_archive_database(self) -> ArchiveDatabase:
        """Open the canonical archive database, creating it when requested."""
        database = self._database(create=True)
        if database is None:  # pragma: no cover - ``create=True`` always opens it
            raise RuntimeError("Could not open the configured archive database")
        return database

    def _database(self, *, create: bool) -> ArchiveDatabase | None:
        with self._lifecycle_lock:
            self._ensure_open()
            if self._archive_database is not None:
                return self._archive_database
            database_path = Path(self.sqlite_path)
            if not create and not database_path.exists():
                return None
            database = open_archive_database(self.sqlite_path)
            self._archive_database = database
            return database

    @property
    def search_engine(self) -> SearchEngine:
        """Return the shared search engine, injected with this runtime's DB."""
        with self._lifecycle_lock:
            self._ensure_open()
            if self._search_engine is None:
                self._search_engine = SearchEngine(
                    self.open_archive_database(),
                    vector_index_path=self.vector_index_path,
                    sqlite_path=self.sqlite_path,
                )
            return self._search_engine

    def mailbox_service(self, *, create_archive: bool = False) -> MailboxService | None:
        """Return the shared mailbox service over the canonical archive connection."""
        with self._lifecycle_lock:
            self._ensure_open()
            if self._mailbox_service is not None:
                return self._mailbox_service
            database = self._database(create=create_archive)
            if database is None:
                return None
            self._mailbox_service = MailboxService(
                MailboxStore(database.conn, operation_context=database.operation),
                db=database,
                embedder_factory=lambda: EmailEmbedder(
                    database,
                    vector_index_path=self.vector_index_path,
                    sqlite_path=self.sqlite_path,
                ),
            )
            return self._mailbox_service

    def close(self) -> None:
        """Close resources owned by this runtime exactly once."""
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            mailbox_service = self._mailbox_service
            search_engine = self._search_engine
            archive_database = self._archive_database
            self._mailbox_service = None
            self._search_engine = None
            self._archive_database = None
        if mailbox_service is not None:
            mailbox_service.close()
        if search_engine is not None:
            search_engine.close()
        if archive_database is not None:
            archive_database.close()

    def __enter__(self) -> ApplicationRuntime:
        with self._lifecycle_lock:
            self._ensure_open()
            return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("ApplicationRuntime is closed")
