"""Corpus-vocabulary query expansion with a cached expander."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.platform.settings import Settings

    from .diagnostics import SearchDiagnostics
    from .query_encoding import QueryEncoder
    from .query_planning import QueryExpander

logger = logging.getLogger(__name__)


class QueryExpansion:
    """Expand queries with archive keywords and record expansion diagnostics.

    The ``QueryExpander`` and its pre-computed vocabulary embeddings are built
    once and reused to avoid re-encoding the vocabulary on every call.
    """

    def __init__(
        self,
        *,
        database: ArchiveDatabase | None,
        encoder: QueryEncoder,
        settings: Settings,
        diagnostics: SearchDiagnostics,
    ) -> None:
        """Bind the keyword source, the shared embedder, and the diagnostics owner."""
        self._database = database
        self._encoder = encoder
        self._settings = settings
        self._diagnostics = diagnostics
        self._expander: QueryExpander | None = None

    def resolve_scope(self, scope: str | None) -> str:
        """Use an explicit scope or fall back to the configured RAG scope."""
        configured_scope = self._settings.rag_scope
        if not isinstance(configured_scope, str):
            configured_scope = "general"
        return configured_scope if scope is None else scope

    def expand(self, query: str, *, scope: str | None = None) -> str:
        """Expand query with semantically related terms."""
        resolved_scope = self.resolve_scope(scope)
        self._diagnostics.set_query_expansion(
            {
                "original_query": query,
                "expanded_query": query,
                "used_query_expansion": False,
                "query_expansion_status": "unchanged",
                "scope": resolved_scope,
            }
        )
        try:
            expander = self._current_expander()
            if expander is None:
                return query
            expanded = expander.expand(query, n_terms=3, scope=resolved_scope)
            self._diagnostics.set_query_expansion(
                {
                    "original_query": query,
                    "expanded_query": expanded,
                    "used_query_expansion": expanded != query,
                    "query_expansion_status": "expanded" if expanded != query else "unchanged",
                    "scope": resolved_scope,
                }
            )
            return expanded
        except Exception as exc:
            logger.debug("Query expansion failed", exc_info=True)
            self._diagnostics.set_query_expansion(
                {
                    "original_query": query,
                    "expanded_query": query,
                    "used_query_expansion": False,
                    "query_expansion_status": "error",
                    "query_expansion_error_type": type(exc).__name__,
                    "query_expansion_error": str(exc),
                }
            )
            return query

    def expand_lanes(self, query: str, *, max_lanes: int = 4, scope: str | None = None) -> list[str]:
        """Expand one query into deterministic retrieval lanes."""
        resolved_scope = self.resolve_scope(scope)
        self._diagnostics.set_query_expansion(
            {
                "original_query": query,
                "query_lanes": [query],
                "used_query_expansion": False,
                "scope": resolved_scope,
            }
        )
        try:
            expander = self._current_expander()
            if expander is None:
                return [query]
            lanes = expander.expand_lanes(query, n_terms=3, max_lanes=max_lanes, scope=resolved_scope)
            self._diagnostics.set_query_expansion(
                {
                    "original_query": query,
                    "query_lanes": lanes,
                    "used_query_expansion": len(lanes) > 1,
                    "scope": resolved_scope,
                }
            )
            return lanes or [query]
        except Exception:
            logger.debug("Query lane expansion failed", exc_info=True)
            return [query]

    def release(self) -> list[Any]:
        """Drop the archive reference; the cached expander is retained like other query caches."""
        self._database = None
        return []

    def _current_expander(self) -> QueryExpander | None:
        """Return the cached expander, building it from archive keywords on first use."""
        from .query_planning import QueryExpander

        db = self._database
        if db is None:
            return None
        if self._expander is None:
            keywords = db.analytics.top_keywords(limit=400)
            if not keywords:
                return None
            vocab = [kw["keyword"] for kw in keywords]
            self._expander = QueryExpander(model=self._encoder.embedder, vocabulary=vocab)
        return self._expander
