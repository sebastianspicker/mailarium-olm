"""Retrieval-facing adapter for archive-owned mailbox visibility policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mailarium.archive.visibility import effective_source_folders, filter_active_mailbox_results

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

    from .models import SearchResult


class ResultVisibility:
    """Apply canonical mailbox source visibility to retrieved results."""

    def __init__(self, database: ArchiveDatabase | None) -> None:
        """Bind the caller-owned archive that decides source visibility."""
        self._database = database

    def may_hide_results(self) -> bool:
        """Report whether mailbox tombstones can hide retrieved rows."""
        database = self._database
        return database is not None and database.visibility.has_tombstoned_sources()

    def visible(self, results: list[SearchResult]) -> list[SearchResult]:
        """Hide mailbox-only tombstones and project deterministic folder membership."""
        database = self._database
        active = (
            database.visibility.active_results(results)
            if database is not None
            else filter_active_mailbox_results(results, conn=None)
        )
        canonical_folders = {
            _result_uid(result): str(result.metadata.get("folder") or "") for result in active if _result_uid(result)
        }
        projected = (
            database.visibility.effective_source_folders(canonical_folders)
            if database is not None
            else effective_source_folders(None, canonical_folders)
        )
        for result in active:
            folders = projected.get(_result_uid(result))
            if folders:
                result.metadata["source_folders"] = list(folders)
        return active

    def release(self) -> list[Any]:
        """Drop the archive reference; visibility owns no closable resources."""
        self._database = None
        return []


def _result_uid(result: SearchResult) -> str:
    return str(result.metadata.get("uid") or result.metadata.get("email_uid") or "").strip()
