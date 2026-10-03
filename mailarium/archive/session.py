"""One archive connection plus the operation lock shared by its repositories."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from .connection import ArchiveConnection


class ArchiveSession:
    """Own the shared SQLite connection and its re-entrant operation lock.

    SQLite permits the connection to be used from MCP worker threads, but
    transactions on one connection must remain atomic with respect to one
    another.  Every archive repository serializes its public operations on this
    single ``RLock``; re-entrancy lets one public operation call another
    repository's public operations without self-deadlocking.
    """

    def __init__(self, connection: ArchiveConnection) -> None:
        self._connection_owner = connection
        self._operation_lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the shared connection, opening and migrating it on first use."""
        return self._connection_owner.connection

    @contextmanager
    def operation(self) -> Iterator[None]:
        """Hold the archive-operation lock for one complete call."""
        with self._operation_lock:
            yield

    def close(self) -> None:
        """Close the shared connection under the operation lock."""
        with self.operation():
            self._connection_owner.close()
