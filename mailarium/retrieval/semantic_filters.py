"""Resolve topic and cluster filters into allowed email UIDs from SQLite."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

    from .diagnostics import SearchDiagnostics

logger = logging.getLogger(__name__)


class SemanticFilterResolver:
    """Pre-fetch UID constraints for semantic filters and record their failures."""

    def __init__(self, database: ArchiveDatabase | None, diagnostics: SearchDiagnostics) -> None:
        """Bind the caller-owned archive and the owner of semantic-filter diagnostics."""
        self._database = database
        self._diagnostics = diagnostics

    def allowed_uids(self, *, topic_id: int | None, cluster_id: int | None) -> set[str] | None:
        """Resolve semantic UID constraints, or None when no constraint applies."""
        if not self._database or (topic_id is None and cluster_id is None):
            return None
        return self._resolve(topic_id=topic_id, cluster_id=cluster_id)

    def release(self) -> list[Any]:
        """Drop the archive reference; the resolver owns no closable resources."""
        self._database = None
        return []

    def _resolve(self, *, topic_id: int | None, cluster_id: int | None) -> set[str]:
        """Pre-fetch email UIDs matching semantic filters from SQLite."""
        errors: list[dict[str, Any]] = []
        self._diagnostics.set_semantic_filter_errors(errors)
        db = self._database
        if db is None:
            return set()

        uid_sets: list[set[str]] = []
        if topic_id is not None:
            try:
                rows = db.analytics.emails_by_topic(topic_id, limit=10_000)
                uid_sets.append({r["uid"] for r in rows})
            except Exception as exc:
                logger.debug("topic_id filter failed", exc_info=True)
                errors.append(
                    {
                        "filter": "topic_id",
                        "value": topic_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                uid_sets.append(set())

        if cluster_id is not None:
            try:
                rows = db.analytics.emails_in_cluster(cluster_id, limit=10_000)
                uid_sets.append({r["uid"] for r in rows})
            except Exception as exc:
                logger.debug("cluster_id filter failed", exc_info=True)
                errors.append(
                    {
                        "filter": "cluster_id",
                        "value": cluster_id,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    }
                )
                uid_sets.append(set())

        self._diagnostics.set_semantic_filter_errors(errors)
        if not uid_sets:
            return set()

        result = uid_sets[0]
        for item in uid_sets[1:]:
            result &= item
        return result
