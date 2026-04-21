"""Retrieval logic for searching and inspecting the email vector database."""

from __future__ import annotations

import collections
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import resolve_runtime_settings

if TYPE_CHECKING:
    from .bm25_index import BM25Index
    from .colbert_reranker import ColBERTReranker
    from .email_db import EmailDatabase
    from .reranker import CrossEncoderReranker
    from .sparse_index import SparseIndex
from .multi_vector_embedder import MultiVectorEmbedder
from .result_filters import (
    _deduplicate_by_email as _deduplicate_by_email_impl,
)
from .result_filters import _email_dedup_key
from .retriever_admin import (
    expand_query_impl,
    expand_query_lanes_impl,
    list_senders_impl,
    resolve_semantic_uids_impl,
    stats_impl,
)
from .retriever_filtered_search import (
    collect_candidates_impl,
    execute_filtered_search_impl,
    post_process_candidates_impl,
    prepare_filtered_search_impl,
)
from .retriever_formatting import format_results_for_llm_impl, serialize_results_impl
from .retriever_hybrid import (
    get_bm25_results_impl,
    get_sparse_results_impl,
    merge_hybrid_impl,
)
from .retriever_models import SearchFilters as _SearchFilters
from .retriever_models import SearchPlan as _SearchPlan
from .retriever_models import SearchResult
from .retriever_query import encode_query_impl, query_with_embedding_impl, search_impl
from .retriever_threads import search_by_thread_impl
from .storage import get_chroma_client, get_collection

logger = logging.getLogger(__name__)
MAX_TOP_K = 1000
_deduplicate_by_email = _deduplicate_by_email_impl

# Overfetch multipliers for search_filtered — empirically tuned so that
# after post-retrieval filtering, dedup (many chunks map to one email),
# and reranking (which may shuffle low-scorers out), we still have enough
# candidates to fill the requested top_k without extra round-trips.
_FILTER_OVERFETCH = 4  # metadata filters can discard 50-75% of results
_DEDUP_OVERFETCH = 2  # ~2 chunks/email on average after chunking
_RERANK_OVERFETCH = 2  # reranking may demote borderline candidates
_MAX_FETCH_SIZE = 10_000
_MAX_FETCH_ATTEMPTS = 6

# Query embedding cache — avoids re-encoding identical queries
_QUERY_CACHE_MAX = 128


class EmailRetriever:
    """Search interface for the email vector database."""

    MAX_TOP_K = MAX_TOP_K

    def __init__(
        self,
        chromadb_path: str | None = None,
        model_name: str | None = None,
        collection_name: str | None = None,
        sqlite_path: str | None = None,
    ):
        self.settings = resolve_runtime_settings(
            chromadb_path=chromadb_path,
            embedding_model=model_name,
            collection_name=collection_name,
            sqlite_path=sqlite_path,
        )

        self.chromadb_path = self.settings.chromadb_path
        self.model_name = self.settings.embedding_model
        self.collection_name = self.settings.collection_name

        self._embedder: MultiVectorEmbedder | None = None
        self._email_db: EmailDatabase | None = None
        self._email_db_checked = False
        self._reranker: CrossEncoderReranker | None = None
        self._colbert_reranker: ColBERTReranker | None = None
        self._bm25_index: BM25Index | None = None
        self._sparse_index: SparseIndex | None = None
        self._sparse_build_count: tuple[int, str] | None = None
        self._bm25_build_revision: tuple[int, str] | None = None
        # Bounded LRU cache — evicts oldest entry when len > _QUERY_CACHE_MAX (128).
        # See _encode_query() for eviction logic.
        self._query_cache: collections.OrderedDict[str, list[list[float]]] = collections.OrderedDict()
        self._set_last_search_debug()
        self.client = get_chroma_client(self.chromadb_path)
        self.collection = get_collection(self.client, self.collection_name)

    @property
    def last_search_debug(self) -> dict[str, Any]:
        """Return the stable per-search diagnostics payload."""
        debug = getattr(self, "_last_search_debug", None)
        if isinstance(debug, dict):
            return debug
        self._last_search_debug = {}
        return self._last_search_debug

    def _set_last_search_debug(self, payload: dict[str, Any] | None = None) -> None:
        """Store the last-search diagnostics in the stable compatibility slot."""
        self._last_search_debug = dict(payload or {})

    @property
    def email_db(self) -> EmailDatabase | None:
        """Lazy-loaded EmailDatabase (None if SQLite file doesn't exist)."""
        cached = getattr(self, "_email_db", None)
        if cached is not None:
            self._email_db_checked = True
            return cached

        settings = getattr(self, "settings", None)
        sqlite_path = getattr(settings, "sqlite_path", None) if settings else None
        self._email_db_checked = True
        if sqlite_path and Path(sqlite_path).exists():
            from .email_db import EmailDatabase

            self._email_db = EmailDatabase(sqlite_path)
            return self._email_db
        return None

    @property
    def embedder(self) -> MultiVectorEmbedder:
        """Lazy-loaded multi-vector embedder."""
        if self._embedder is None:
            self._embedder = MultiVectorEmbedder(
                model_name=self.model_name,
                device=self.settings.device,
                sparse_enabled=self.settings.sparse_enabled,
                colbert_enabled=self.settings.colbert_rerank_enabled,
                batch_size=self.settings.embedding_batch_size,
                mps_float16=self.settings.mps_float16,
                load_mode=self.settings.embedding_load_mode,
            )
        return self._embedder

    @property
    def model(self) -> MultiVectorEmbedder:
        """Backward-compatible alias for ``embedder``."""
        return self.embedder

    def _encode_query(self, query: str) -> list[list[float]]:
        """Encode a query string, using a bounded cache to avoid re-encoding."""
        return encode_query_impl(self, query)

    def search(self, query: str, top_k: int | None = None, where: dict | None = None) -> list[SearchResult]:
        """Semantic search across all emails."""
        return search_impl(self, query, top_k=top_k, where=where)

    def _query_with_embedding(
        self,
        query_embedding: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Execute a collection query from a precomputed embedding."""
        return query_with_embedding_impl(self, query_embedding, n_results, where=where)

    def search_filtered(
        self,
        query: str,
        top_k: int = 10,
        sender: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        subject: str | None = None,
        folder: str | None = None,
        cc: str | None = None,
        to: str | None = None,
        bcc: str | None = None,
        has_attachments: bool | None = None,
        priority: int | None = None,
        min_score: float | None = None,
        email_type: str | None = None,
        rerank: bool = False,
        hybrid: bool = False,
        topic_id: int | None = None,
        cluster_id: int | None = None,
        expand_query: bool = False,
        category: str | None = None,
        is_calendar: bool | None = None,
        attachment_name: str | None = None,
        attachment_type: str | None = None,
    ) -> list[SearchResult]:
        """Search with optional filters.

        Supports: sender, date_from, date_to, subject, folder, cc, to, bcc,
        has_attachments, priority, min_score, email_type, topic_id, cluster_id.

        Results are deduplicated per email UID — only the best-scoring chunk
        per email is returned.
        """
        plan, filters = self._prepare_filtered_search(
            query=query,
            top_k=top_k,
            sender=sender,
            date_from=date_from,
            date_to=date_to,
            subject=subject,
            folder=folder,
            cc=cc,
            to=to,
            bcc=bcc,
            has_attachments=has_attachments,
            priority=priority,
            min_score=min_score,
            email_type=email_type,
            rerank=rerank,
            hybrid=hybrid,
            topic_id=topic_id,
            cluster_id=cluster_id,
            expand_query=expand_query,
            category=category,
            is_calendar=is_calendar,
            attachment_name=attachment_name,
            attachment_type=attachment_type,
        )
        if plan is None:
            return []
        return self._execute_filtered_search(plan, filters)

    def _prepare_filtered_search(
        self,
        *,
        query: str,
        top_k: int,
        sender: str | None,
        date_from: str | None,
        date_to: str | None,
        subject: str | None,
        folder: str | None,
        cc: str | None,
        to: str | None,
        bcc: str | None,
        has_attachments: bool | None,
        priority: int | None,
        min_score: float | None,
        email_type: str | None,
        rerank: bool,
        hybrid: bool,
        topic_id: int | None,
        cluster_id: int | None,
        expand_query: bool,
        category: str | None,
        is_calendar: bool | None,
        attachment_name: str | None,
        attachment_type: str | None,
    ) -> tuple[_SearchPlan | None, _SearchFilters]:
        """Normalize request inputs and derive a search plan."""
        return prepare_filtered_search_impl(
            self,
            query=query,
            top_k=top_k,
            sender=sender,
            date_from=date_from,
            date_to=date_to,
            subject=subject,
            folder=folder,
            cc=cc,
            to=to,
            bcc=bcc,
            has_attachments=has_attachments,
            priority=priority,
            min_score=min_score,
            email_type=email_type,
            rerank=rerank,
            hybrid=hybrid,
            topic_id=topic_id,
            cluster_id=cluster_id,
            expand_query=expand_query,
            category=category,
            is_calendar=is_calendar,
            attachment_name=attachment_name,
            attachment_type=attachment_type,
        )

    def _resolve_allowed_uids(self, *, topic_id: int | None, cluster_id: int | None) -> set[str] | None:
        """Resolve semantic UID constraints for topic and cluster filters."""
        if not self.email_db or (topic_id is None and cluster_id is None):
            return None
        return self._resolve_semantic_uids(topic_id=topic_id, cluster_id=cluster_id)

    def _validate_filtered_search(self, *, top_k: int, min_score: float | None, filters: _SearchFilters) -> None:
        """Validate normalized filtered-search inputs."""
        if top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if top_k > MAX_TOP_K:
            raise ValueError(f"top_k must be <= {MAX_TOP_K}.")
        if min_score is not None and not (0.0 <= min_score <= 1.0):
            raise ValueError("min_score must be between 0.0 and 1.0.")
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise ValueError(f"date_from ({filters.date_from}) must be <= date_to ({filters.date_to}).")

    def _build_search_plan(self, query: str, top_k: int, filters: _SearchFilters, *, rerank: bool, hybrid: bool) -> _SearchPlan:
        """Compute the initial execution plan for a filtered search."""
        settings = getattr(self, "settings", None)
        use_rerank = rerank or (settings.rerank_enabled if settings else False)
        use_hybrid = hybrid or (settings.hybrid_enabled if settings else False)
        rerank_multiplier = _RERANK_OVERFETCH if use_rerank else 1
        multiplier = (_FILTER_OVERFETCH if filters.has_filters else 1) * _DEDUP_OVERFETCH * rerank_multiplier
        fetch_size = max(top_k * multiplier, top_k)
        return _SearchPlan(
            query=query,
            top_k=top_k,
            use_rerank=use_rerank,
            use_hybrid=use_hybrid,
            fetch_size=fetch_size,
        )

    def _execute_filtered_search(self, plan: _SearchPlan, filters: _SearchFilters) -> list[SearchResult]:
        """Run the iterative candidate fetch loop for filtered search."""
        return execute_filtered_search_impl(self, plan, filters)

    def _collect_candidates(
        self,
        query: str,
        fetch_size: int,
        use_hybrid: bool,
        query_embedding: list[list[float]] | None,
    ) -> tuple[list[SearchResult], int, list[list[float]] | None]:
        """Collect dense candidates and optionally merge hybrid keyword results."""
        return collect_candidates_impl(self, query, fetch_size, use_hybrid, query_embedding)

    def _post_process_candidates(
        self,
        plan: _SearchPlan,
        filters: _SearchFilters,
        raw_candidates: list[SearchResult],
    ) -> list[SearchResult]:
        """Apply filters, deduplication, reranking, and post-rerank score trimming."""
        return post_process_candidates_impl(self, plan, filters, raw_candidates)

    def _apply_rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        """Apply reranking: ColBERT (if available) or cross-encoder fallback."""
        # Try ColBERT reranking first (same model, no extra load)
        settings = getattr(self, "settings", None)
        use_colbert = getattr(settings, "colbert_rerank_enabled", False)
        if use_colbert and self.embedder.has_colbert:
            if getattr(self, "_colbert_reranker", None) is None:
                from .colbert_reranker import ColBERTReranker

                self._colbert_reranker = ColBERTReranker(self.embedder)
            return self._colbert_reranker.rerank(query, results, top_k=top_k)

        # Cross-encoder fallback
        if self._reranker is None:
            from .reranker import CrossEncoderReranker

            model = getattr(settings, "rerank_model", None)
            self._reranker = CrossEncoderReranker(model_name=model)
        return self._reranker.rerank(query, results, top_k=top_k)

    def _merge_hybrid(self, query: str, semantic_results: list[SearchResult], fetch_size: int) -> list[SearchResult]:
        """Merge semantic results with sparse/BM25 keyword results via RRF.

        Prefers BGE-M3 learned sparse vectors (from SparseIndex) when available,
        falling back to BM25 otherwise.
        """
        return merge_hybrid_impl(self, query, semantic_results, fetch_size)

    def _get_sparse_results(self, query: str, top_k: int) -> list[str] | None:
        """Try learned sparse retrieval. Returns None if unavailable."""
        return get_sparse_results_impl(self, query, top_k)

    def _get_bm25_results(self, query: str, top_k: int) -> list[str] | None:
        """BM25 keyword retrieval fallback."""
        return get_bm25_results_impl(self, query, top_k)

    def search_by_thread(self, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
        """Retrieve all emails in a conversation thread, sorted by date.

        Uses ChromaDB ``where`` filter on ``conversation_id``, then deduplicates
        by email UID to return one result per email.
        """
        return search_by_thread_impl(self, conversation_id, top_k)

    def list_senders(self, limit: int = 50) -> list[dict[str, Any]]:
        """List unique senders sorted by message count.

        Uses SQLite when available for O(1) query, falls back to
        iterating ChromaDB metadata otherwise.
        """
        return list_senders_impl(self, limit=limit)

    def list_folders(self) -> list[dict[str, Any]]:
        """List all folders with email counts, sorted by count descending."""
        stats = self.stats()
        return [{"folder": name, "count": count} for name, count in stats.get("folders", {}).items()]

    def stats(self) -> dict[str, Any]:
        """Get summary statistics about the indexed archive.

        Uses SQLite for O(1) aggregates when available, falls back to
        iterating ChromaDB metadata otherwise.
        """
        return stats_impl(self)

    def format_results_for_llm(
        self,
        results: list[SearchResult],
        max_body_chars: int | None = None,
        max_response_tokens: int | None = None,
    ) -> str:
        """Format search results as context for an LLM client.

        Groups results sharing a ``conversation_id`` under a thread header,
        sorting thread members by date.  Truncates individual bodies to
        *max_body_chars* and stops emitting results when *max_response_tokens*
        would be exceeded.  Both default to the values in ``Settings``.
        """
        return format_results_for_llm_impl(self, results, max_body_chars, max_response_tokens)

    def serialize_results(
        self,
        query: str,
        results: list[SearchResult],
        max_body_chars: int | None = None,
        max_response_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Serialize search results into stable JSON-ready payload.

        Applies per-body truncation via *max_body_chars* and stops adding
        results when the cumulative output would exceed *max_response_tokens*.
        Both default to the values in ``Settings``.
        """
        return serialize_results_impl(self, query, results, max_body_chars, max_response_tokens)

    def reset_index(self) -> None:
        """Delete and recreate the configured collection."""
        logger.warning("Resetting collection '%s' at %s", self.collection_name, self.chromadb_path)
        self.client.delete_collection(self.collection_name)
        self.collection = get_collection(self.client, self.collection_name)

    def _resolve_semantic_uids(
        self,
        topic_id: int | None = None,
        cluster_id: int | None = None,
    ) -> set[str]:
        """Pre-fetch email UIDs matching semantic filters from SQLite."""
        return resolve_semantic_uids_impl(self, topic_id=topic_id, cluster_id=cluster_id)

    _query_expander: Any = None  # Cached QueryExpander instance

    def _expand_query(self, query: str) -> str:
        """Expand query with semantically related terms.

        Caches the QueryExpander instance (and its pre-computed vocab
        embeddings) on the retriever to avoid re-encoding the vocabulary
        on every call.
        """
        return expand_query_impl(self, query)

    def _expand_query_lanes(self, query: str, *, max_lanes: int = 4) -> list[str]:
        """Expand a query into deterministic retrieval lanes."""
        return expand_query_lanes_impl(self, query, max_lanes=max_lanes)

    # _email_dedup_key is used by list_senders — delegate to result_filters
    _email_dedup_key = staticmethod(_email_dedup_key)
