"""Canonical search engine composed from explicit retrieval collaborators."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from mailarium.archive.vectors import get_vector_collection
from mailarium.platform.settings import resolve_runtime_settings

from .archive_summary import ArchiveSummary
from .dense import DenseRetriever
from .diagnostics import SearchDiagnostics
from .filtered_search import FilteredSearch
from .hybrid import BM25Retriever, HybridFusion, SparseRetriever
from .image_search import ImageSearch
from .limits import MAX_TOP_K
from .models import SearchRequest, SearchResponse, SearchResult
from .query_encoding import QueryEncoder
from .query_expansion import QueryExpansion
from .reranking import ResultReranker
from .semantic_filters import SemanticFilterResolver
from .semantic_search import SemanticSearch
from .threads import thread_results
from .visibility import ResultVisibility

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase

    from .multi_vector_embedder import MultiVectorEmbedder
    from .sparse_index import SparseIndex

__all__ = ["MAX_TOP_K", "SearchEngine", "SearchRequest", "SearchResponse", "SearchResult"]

logger = logging.getLogger(__name__)


class SearchEngine:
    """Canonical local search engine over SQLite records and derived indexes.

    SQLite remains authoritative for canonical metadata; text and image vector
    collections plus sparse/BM25 indexes are rebuildable candidate sources.
    The engine builds one collaborator per responsibility, hands each exactly
    the state it needs, and owns their combined lifecycle.
    """

    MAX_TOP_K = MAX_TOP_K

    def __init__(
        self,
        database: ArchiveDatabase,
        vector_index_path: str | None = None,
        model_name: str | None = None,
        sqlite_path: str | None = None,
        sparse_enabled: bool | None = None,
        image_search_enabled: bool | None = None,
        model_revision: str | None = None,
    ):
        """Initialize retrieval over a caller-owned archive database."""
        self.settings = resolve_runtime_settings(
            vector_index_path=vector_index_path,
            embedding_model=model_name,
            sqlite_path=sqlite_path,
            sparse_enabled=sparse_enabled,
            image_search_enabled=image_search_enabled,
            embedding_model_revision=model_revision,
        )
        settings = self.settings
        self.vector_index_path = settings.vector_index_path
        self.model_name = settings.embedding_model
        self._email_db: ArchiveDatabase | None = database
        self.collection = get_vector_collection(
            database=database,
            vector_index_path=self.vector_index_path,
            embedding_space="text",
            model_id=self.model_name,
            model_revision=settings.embedding_model_revision,
        )
        self.image_collection = get_vector_collection(
            database=database,
            vector_index_path=self.vector_index_path,
            embedding_space="image",
            model_id=settings.image_embedding_model,
            model_revision=settings.image_embedding_model_revision,
        )

        self._diagnostics = SearchDiagnostics()
        self._encoder = QueryEncoder(settings)
        self._visibility = ResultVisibility(database)
        dense = DenseRetriever(self.collection, self._encoder, settings)
        self._image_search = ImageSearch(self.image_collection, settings)
        self._semantic_search = SemanticSearch(
            dense=dense,
            encoder=self._encoder,
            image_search=self._image_search,
            visibility=self._visibility,
            settings=settings,
        )
        self._bm25 = BM25Retriever(collection=self.collection, diagnostics=self._diagnostics)
        self._sparse = SparseRetriever(
            collection=self.collection,
            database=database,
            encoder=self._encoder,
            settings=settings,
            diagnostics=self._diagnostics,
        )
        self._reranker = ResultReranker(settings)
        self._semantic_filters = SemanticFilterResolver(database, self._diagnostics)
        self._expansion = QueryExpansion(
            database=database,
            encoder=self._encoder,
            settings=settings,
            diagnostics=self._diagnostics,
        )
        self._filtered_search = FilteredSearch(
            settings=settings,
            semantic_search=self._semantic_search,
            dense=dense,
            encoder=self._encoder,
            hybrid=HybridFusion(
                collection=self.collection,
                sparse=self._sparse,
                bm25=self._bm25,
                diagnostics=self._diagnostics,
            ),
            reranker=self._reranker,
            visibility=self._visibility,
            semantic_filters=self._semantic_filters,
            expansion=self._expansion,
            diagnostics=self._diagnostics,
        )
        self._summary = ArchiveSummary(self.collection, database)

    def close(self) -> None:
        """Release derived resources without closing the caller-owned archive."""
        resources: list[Any] = [self.collection, self.image_collection]
        for collaborator in (
            self._encoder,
            self._reranker,
            self._image_search,
            self._bm25,
            self._sparse,
            self._visibility,
            self._semantic_filters,
            self._expansion,
            self._summary,
        ):
            resources.extend(collaborator.release())
        closed: set[int] = set()
        for resource in resources:
            if resource is not None and id(resource) not in closed:
                closed.add(id(resource))
                close = getattr(resource, "close", None)
                if callable(close):
                    close()
        self._email_db = None

    def __enter__(self) -> SearchEngine:
        """Use the engine as a context manager when a caller owns its lifetime."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Close every owned local resource at context-manager exit."""
        self.close()

    @property
    def last_search_debug(self) -> dict[str, Any]:
        """Return the diagnostics of the current thread's last search."""
        return self._diagnostics.search_debug

    @property
    def email_db(self) -> ArchiveDatabase | None:
        """Return the explicitly injected archive database."""
        return self._email_db

    @property
    def embedder(self) -> MultiVectorEmbedder:
        """Lazy-loaded multi-vector embedder shared by query encoding and expansion."""
        return self._encoder.embedder

    @embedder.setter
    def embedder(self, embedder: MultiVectorEmbedder) -> None:
        """Inject a text encoder, such as a deterministic local encoder in tests."""
        self._encoder.embedder = embedder

    @property
    def sparse_index(self) -> SparseIndex | None:
        """Return the learned-sparse index, when one has been loaded, for runtime diagnostics."""
        return self._sparse.index

    def search(self, query: str, top_k: int | None = None, where: dict | None = None) -> list[SearchResult]:
        """Run filtered semantic search and merge eligible image results.

        Raises:
            ValueError: If ``top_k`` is non-positive or exceeds the supported
                retrieval limit.
        """
        return self._semantic_search.search(query, top_k=top_k, where=where)

    def search_filtered(self, query: str, top_k: int = 10, **filter_values: Any) -> list[SearchResult]:
        """Search with optional filters.

        Supports: sender, date_from, date_to, subject, folder, cc, to, bcc,
        has_attachments, priority, min_score, email_type, topic_id, cluster_id.

        Results are deduplicated per email UID - only the best-scoring chunk
        per email is returned.
        """
        request = SearchRequest(query=query, top_k=top_k, **filter_values)
        return self.execute(request).as_list()

    def execute(self, request: SearchRequest) -> SearchResponse:
        """Execute one typed request and return immutable results plus diagnostics."""
        return self._filtered_search.execute(request)

    def search_by_thread(self, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
        """Load one canonical result per email in the requested conversation.

        Uses canonical SQLite metadata for ``conversation_id``, then deduplicates
        by email UID to return one result per email.
        """
        return self._visibility.visible(thread_results(self.collection, conversation_id, top_k))

    def list_senders(self, limit: int = 50) -> list[dict[str, Any]]:
        """List unique senders sorted by message count.

        Uses SQLite when available for O(1) query, falls back to
        iterating canonical vector metadata otherwise.
        """
        return self._summary.list_senders(limit=limit)

    def list_folders(self) -> list[dict[str, Any]]:
        """List all folders with email counts, sorted by count descending."""
        stats = self.stats()
        return [{"folder": name, "count": count} for name, count in stats.get("folders", {}).items()]

    def stats(self) -> dict[str, Any]:
        """Get summary statistics about the indexed archive.

        Uses SQLite for O(1) aggregates when available, falls back to
        iterating canonical vector metadata otherwise.
        """
        return self._summary.stats()

    def reset_index(self) -> None:
        """Clear derived vector rows without deleting relational email data."""
        logger.warning("Resetting vector indexes at %s", self.vector_index_path)
        self.collection.reset()
        self.image_collection.reset()

    def expand_query_lanes(self, query: str, *, max_lanes: int = 4, scope: str | None = None) -> list[str]:
        """Expand a query into deterministic retrieval lanes for answer-context assembly."""
        return self._expansion.expand_lanes(query, max_lanes=max_lanes, scope=scope)
