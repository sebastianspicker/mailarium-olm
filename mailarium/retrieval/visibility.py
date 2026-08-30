"""Retrieval-facing adapter for archive-owned mailbox visibility policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mailarium.archive.visibility import effective_source_folders, filter_active_mailbox_results

if TYPE_CHECKING:
    from .retriever_models import SearchResult


def visible_results(database: Any, results: list[SearchResult]) -> list[SearchResult]:
    """Apply canonical source visibility and project deterministic folder membership."""
    conn = database.conn if database is not None else None
    active = filter_active_mailbox_results(results, conn=conn)
    canonical_folders = {
        _result_uid(result): str(result.metadata.get("folder") or "") for result in active if _result_uid(result)
    }
    projected = effective_source_folders(conn, canonical_folders)
    for result in active:
        folders = projected.get(_result_uid(result))
        if folders:
            result.metadata["source_folders"] = list(folders)
    return active


def _result_uid(result: SearchResult) -> str:
    return str(result.metadata.get("uid") or result.metadata.get("email_uid") or "").strip()
