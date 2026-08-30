"""Canonical SQLite archive persistence and rebuildable vector storage.

``open_archive_database`` is the production entry point for bounded archive
work.  Its caller owns the returned connection and must close it deterministically.
``ApplicationRuntime`` is the only long-lived composition owner.
"""

from .database import ArchiveDatabase


def open_archive_database(
    sqlite_path: str,
    *,
    busy_timeout_ms: int = 5000,
) -> ArchiveDatabase:
    """Open an archive database whose lifecycle remains with the caller."""
    return ArchiveDatabase(sqlite_path, busy_timeout_ms=busy_timeout_ms)


__all__ = ["ArchiveDatabase", "open_archive_database"]
