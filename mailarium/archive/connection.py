"""Explicit SQLite connection ownership for a local mail archive."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .db_schema import init_schema


class ArchiveConnection:
    """Lazily open, configure, and close one SQLite archive connection.

    The archive database owns transaction serialization.  This object owns
    only connection setup and lifetime, so SQLite configuration cannot drift
    between archive repositories or vector storage.
    """

    def __init__(self, path: str = ":memory:", *, busy_timeout_ms: int = 5000) -> None:
        self.path = path
        self.busy_timeout_ms = max(int(busy_timeout_ms), 0)
        self._connection: sqlite3.Connection | None = None
        self._open_lock = threading.Lock()

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the configured shared connection, opening it once on demand."""
        if self._connection is not None:
            return self._connection
        with self._open_lock:
            if self._connection is None:
                if self.path != ":memory:":
                    Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                timeout = max(self.busy_timeout_ms / 1000.0, 0.1)
                connection = sqlite3.connect(self.path, check_same_thread=False, timeout=timeout)
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
                connection.execute("PRAGMA foreign_keys=ON")
                connection.row_factory = sqlite3.Row
                init_schema(connection)
                self._connection = connection
        return self._connection

    def close(self) -> None:
        """Release the connection; the instance can be opened again later."""
        with self._open_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
