"""Retrieval logic for searching and inspecting the email vector database."""
# pylint: disable=too-many-arguments,too-many-instance-attributes,too-many-locals,too-many-positional-arguments

from __future__ import annotations

import collections
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import resolve_runtime_settings

if TYPE_CHECKING:
    from .bm25_index import BM25Index
    from .email_db import EmailDatabase
    from .image_embedder import ImageEmbedder
    from .late_interaction_backend import LocalLateInteractionBackend
    from .reranker import CrossEncoderReranker
    from .retrieval_policy import RetrievalPolicy
    from .sparse_index import SparseIndex
from .mailbox_visibility import (
    effective_source_folders,
    filter_active_mailbox_results,
    has_tombstoned_mailbox_sources,
)
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
from .retriever_models import FilteredSearchRequest, SearchResult
from .retriever_models import SearchFilters as _SearchFilters
from .retriever_models import SearchPlan as _SearchPlan
from .retriever_query import encode_query_impl, query_with_embedding_impl, search_impl
from .retriever_threads import search_by_thread_impl
from .storage import get_vector_collection

logger = logging.getLogger(__name__)
MAX_TOP_K = 1000
_deduplicate_by_email = _deduplicate_by_email_impl

# Overfetch multipliers for search_filtered - empirically tuned so that
# after post-retrieval filtering, dedup (many chunks map to one email),
# and reranking (which may shuffle low-scorers out), we still have enough
# candidates to fill the requested top_k without extra round-trips.
_FILTER_OVERFETCH = 4  # metadata filters can discard 50-75% of results
_DEDUP_OVERFETCH = 2  # ~2 chunks/email on average after chunking
_RERANK_OVERFETCH = 2  # reranking may demote borderline candidates
_MAX_FETCH_SIZE = 10_000
_MAX_FETCH_ATTEMPTS = 13

# Query embedding cache - avoids re-encoding identical queries
_QUERY_CACHE_MAX = 128


def _rank_fuse_results(
    text_results: list[SearchResult],
    image_results: list[SearchResult],
    top_k: int,
) -> list[SearchResult]:
    """Fuse incompatible vector spaces by reciprocal rank only."""
    scores: dict[str, float] = {}
    rows: dict[str, SearchResult] = {}
    sources: dict[str, set[str]] = {}
    for source, results in (("text", text_results), ("image", image_results)):
        for rank, result in enumerate(results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + 1.0 / (60 + rank)
            rows.setdefault(result.chunk_id, result)
            sources.setdefault(result.chunk_id, set()).add(source)
    if not scores:
        return []
    maximum = max(scores.values())
    ranked_ids = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [
        SearchResult(
            chunk_id=rows[chunk_id].chunk_id,
            text=rows[chunk_id].text,
            metadata={
                **rows[chunk_id].metadata,
                "retrieval_spaces": sorted(sources[chunk_id]),
                "score_kind": "rank_fused",
            },
            distance=max(0.0, 1.0 - (scores[chunk_id] / maximum)),
        )
        for chunk_id in ranked_ids[:top_k]
    ]


def _result_uid(result: SearchResult) -> str:
    """Return the canonical email identifier exposed by a search result."""
    return str(result.metadata.get("uid") or result.metadata.get("email_uid") or "").strip()


class EmailRetriever:
    """Search interface for the email vector database."""

    MAX_TOP_K = MAX_TOP_K

    def __init__(
        self,
        vector_index_path: str | None = None,
        model_name: str | None = None,
        sqlite_path: str | None = None,
        sparse_enabled: bool | None = None,
        image_search_enabled: bool | None = None,
        model_revision: str | None = None,
    ):
        """Initialize retrieval configuration, storage handles, and per-search diagnostic state."""
        self.settings = resolve_runtime_settings(
            vector_index_path=vector_index_path,
            embedding_model=model_name,
            sqlite_path=sqlite_path,
            sparse_enabled=sparse_enabled,
            image_search_enabled=image_search_enabled,
            embedding_model_revision=model_revision,
        )

        self.vector_index_path = self.settings.vector_index_path
        self.model_name = self.settings.embedding_model

        self._embedder: MultiVectorEmbedder | None = None
        self._email_db: EmailDatabase | None = None
        self._email_db_checked = False
        self._reranker: CrossEncoderReranker | None = None
        self._late_interaction_backend: LocalLateInteractionBackend | None = None
        self._image_embedder: ImageEmbedder | None = None
        self._bm25_index: BM25Index | None = None
        self._sparse_index: SparseIndex | None = None
        self._sparse_build_count: tuple[int, str] | None = None
        self._bm25_build_revision: tuple[int, str] | None = None
        self._last_search_debug: dict[str, Any] = {}
        self._search_debug_state = threading.local()
        # Bounded LRU cache - evicts oldest entry when len > _QUERY_CACHE_MAX (128).
        # See _encode_query() for eviction logic.
        self._query_cache: collections.OrderedDict[str, list[list[float]]] = collections.OrderedDict()
        self._set_last_search_debug()
        self.collection = get_vector_collection(
            vector_index_path=self.vector_index_path,
            sqlite_path=self.settings.sqlite_path,
            embedding_space="text",
            model_id=self.model_name,
            model_revision=self.settings.embedding_model_revision,
        )
        self.image_collection = get_vector_collection(
            vector_index_path=self.vector_index_path,
            sqlite_path=self.settings.sqlite_path,
            embedding_space="image",
            model_id=self.settings.image_embedding_model,
            model_revision=self.settings.image_embedding_model_revision,
        )

    def close(self) -> None:
        """Release owned vector collections and the lazily opened email database."""
        for attribute in ("collection", "image_collection"):
            collection = getattr(self, attribute, None)
            close = getattr(collection, "close", None)
            if callable(close):
                close()
        database = getattr(self, "_email_db", None)
        if database is not None:
            database.close()
            self._email_db = None

    @property
    def last_search_debug(self) -> dict[str, Any]:
        """Return an isolated copy of diagnostics for the current thread's last search."""
        state = getattr(self, "_search_debug_state", None)
        if state is None:
            state = threading.local()
            self._search_debug_state = state
        debug = getattr(state, "payload", None)
        if not isinstance(debug, dict):
            legacy = getattr(self, "_last_search_debug", None)
            debug = dict(legacy) if isinstance(legacy, dict) else {}
            state.payload = debug
        return debug

    def _set_last_search_debug(self, payload: dict[str, Any] | None = None) -> None:
        """Store diagnostics in thread-local state and the compatibility slot."""
        debug = dict(payload or {})
        state = getattr(self, "_search_debug_state", None)
        if state is None:
            state = threading.local()
            self._search_debug_state = state
        state.payload = debug
        self._last_search_debug = debug

    @property
    def last_query_expansion(self) -> dict[str, Any]:
        """Return an isolated copy of query-expansion diagnostics for the current thread."""
        state = getattr(self, "_search_debug_state", None)
        if state is None:
            state = threading.local()
            self._search_debug_state = state
        debug = getattr(state, "query_expansion", None)
        if not isinstance(debug, dict):
            legacy = getattr(self, "_last_query_expansion", None)
            debug = dict(legacy) if isinstance(legacy, dict) else {}
            state.query_expansion = debug
        return debug

    def _set_last_query_expansion(self, payload: dict[str, Any] | None = None) -> None:
        """Store query-expansion diagnostics for the current worker thread."""
        debug = dict(payload or {})
        state = getattr(self, "_search_debug_state", None)
        if state is None:
            state = threading.local()
            self._search_debug_state = state
        state.query_expansion = debug
        self._last_query_expansion = debug

    @property
    def last_semantic_filter_errors(self) -> list[dict[str, Any]]:
        """Return copied semantic-filter errors accumulated by the current thread's search."""
        state = getattr(self, "_search_debug_state", None)
        if state is None:
            state = threading.local()
            self._search_debug_state = state
        errors = getattr(state, "semantic_filter_errors", None)
        if not isinstance(errors, list):
            legacy = getattr(self, "_last_semantic_filter_errors", None)
            errors = list(legacy) if isinstance(legacy, list) else []
            state.semantic_filter_errors = errors
        return errors

    def _set_last_semantic_filter_errors(self, errors: list[dict[str, Any]] | None = None) -> None:
        """Store semantic-filter errors for the current worker thread."""
        snapshot = [dict(error) for error in (errors or [])]
        state = getattr(self, "_search_debug_state", None)
        if state is None:
            state = threading.local()
            self._search_debug_state = state
        state.semantic_filter_errors = snapshot
        self._last_semantic_filter_errors = snapshot

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
            self.collection.attach_database(self._email_db)
            self.image_collection.attach_database(self._email_db)
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
                sparse_model=self.settings.sparse_model,
                sparse_model_revision=self.settings.sparse_model_revision,
                batch_size=self.settings.embedding_batch_size,
                load_mode=self.settings.embedding_load_mode,
                model_revision=self.settings.embedding_model_revision,
            )
        return self._embedder

    @property
    def model(self) -> MultiVectorEmbedder:
        """Backward-compatible alias used by query-expansion consumers."""
        return self.embedder

    def _encode_query(self, query: str) -> list[list[float]]:
        """Encode a query string, using a bounded cache to avoid re-encoding."""
        return encode_query_impl(self, query)

    def search(self, query: str, top_k: int | None = None, where: dict | None = None) -> list[SearchResult]:
        """Run filtered semantic search and merge eligible image results.

        Raises:
            ValueError: If ``top_k`` is non-positive or exceeds the supported
                retrieval limit.
        """
        requested = self._requested_search_limit(top_k)
        fetch_size = self._initial_search_fetch_size(requested)
        query_embedding: list[list[float]] | None = None
        for _ in range(_MAX_FETCH_ATTEMPTS):
            results, query_embedding = self._text_search_batch(
                query,
                fetch_size,
                where,
                query_embedding,
            )
            merged = self._merge_image_results(query, results, fetch_size, where=where)
            active = self._active_mailbox_results(merged)
            if self._search_is_complete(active, merged, requested, fetch_size):
                return active[:requested]
            fetch_size = min(_MAX_FETCH_SIZE, fetch_size * 2)
        return active[:requested]

    def _requested_search_limit(self, top_k: int | None) -> int:
        """Validate and resolve the public semantic-search result limit."""
        if top_k is not None and top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if top_k is not None and top_k > MAX_TOP_K:
            raise ValueError(f"top_k must be <= {MAX_TOP_K}.")
        requested = top_k if top_k is not None else getattr(getattr(self, "settings", None), "top_k", 10)
        return requested if requested > 0 else 10

    def _initial_search_fetch_size(self, requested: int) -> int:
        """Overfetch only when mailbox tombstones may hide retrieved rows."""
        database = self.email_db
        if database is None or not has_tombstoned_mailbox_sources(database.conn):
            return requested
        return min(_MAX_FETCH_SIZE, max(requested, requested * _FILTER_OVERFETCH))

    def _text_search_batch(
        self,
        query: str,
        fetch_size: int,
        where: dict | None,
        query_embedding: list[list[float]] | None,
    ) -> tuple[list[SearchResult], list[list[float]] | None]:
        """Fetch one text-search batch, reusing an embedding above the public limit."""
        if fetch_size <= MAX_TOP_K:
            return search_impl(self, query, top_k=fetch_size, where=where), query_embedding
        if query_embedding is None:
            query_embedding = self._encode_query(query)
        return self._query_with_embedding(query_embedding, fetch_size, where=where), query_embedding

    @staticmethod
    def _search_is_complete(
        active: list[SearchResult],
        merged: list[SearchResult],
        requested: int,
        fetch_size: int,
    ) -> bool:
        """Stop when the requested rows are filled or no larger batch can help."""
        return len(active) >= requested or len(merged) < fetch_size or fetch_size >= _MAX_FETCH_SIZE

    def _query_with_embedding(
        self,
        query_embedding: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Execute a collection query from a precomputed embedding."""
        return query_with_embedding_impl(self, query_embedding, n_results, where=where)

    def _merge_image_results(
        self,
        query: str,
        text_results: list[SearchResult],
        top_k: int,
        *,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Rank-fuse text and image spaces without comparing raw distances."""
        image_collection = self._available_image_collection()
        if image_collection is None:
            return text_results[:top_k]
        image_results = self._image_search_results(query, top_k, where, image_collection)
        if image_results is None:
            return text_results[:top_k]
        return _rank_fuse_results(text_results, image_results, top_k)

    def _available_image_collection(self) -> Any | None:
        """Return a non-empty configured image collection, when enabled."""
        settings = getattr(self, "settings", None)
        image_collection = getattr(self, "image_collection", None)
        if not getattr(settings, "image_search_enabled", False) or image_collection is None:
            return None
        return image_collection if image_collection.count() else None

    def _image_search_results(
        self,
        query: str,
        top_k: int,
        where: dict[str, Any] | None,
        image_collection: Any,
    ) -> list[SearchResult] | None:
        """Encode and query the image space, returning None for an unusable query."""
        if self._image_embedder is None:
            from .image_embedder import ImageEmbedder

            self._image_embedder = ImageEmbedder(
                model_name=self.settings.image_embedding_model,
                model_revision=self.settings.image_embedding_model_revision,
                device=self.settings.device,
                load_mode=self.settings.embedding_load_mode,
            )
        query_vector = self._image_embedder.encode_text(query)
        if not query_vector:
            return None
        payload = image_collection.query(
            query_embeddings=[query_vector],
            n_results=max(top_k, 1),
            include=["documents", "metadatas", "distances"],
            where=where,
        )
        return self._image_results_from_payload(payload)

    @staticmethod
    def _image_results_from_payload(payload: dict[str, Any]) -> list[SearchResult]:
        """Hydrate ranked image rows from the collection response shape."""
        ids = (payload.get("ids") or [[]])[0]
        documents = (payload.get("documents") or [[]])[0]
        metadatas = (payload.get("metadatas") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        return [
            EmailRetriever._image_result_from_payload_row(chunk_id, index, documents, metadatas, distances)
            for index, chunk_id in enumerate(ids)
        ]

    @staticmethod
    def _image_result_from_payload_row(
        chunk_id: str,
        index: int,
        documents: list[Any],
        metadatas: list[Any],
        distances: list[Any],
    ) -> SearchResult:
        """Hydrate one image result while retaining payload-array defaults."""
        document = documents[index] if index < len(documents) else ""
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = float(distances[index]) if index < len(distances) else 1.0
        return SearchResult(
            chunk_id=chunk_id,
            text=document,
            metadata={**metadata, "retrieval_space": "image"},
            distance=distance,
        )

    def search_filtered(self, query: str, top_k: int = 10, **filter_values: Any) -> list[SearchResult]:
        """Search with optional filters.

        Supports: sender, date_from, date_to, subject, folder, cc, to, bcc,
        has_attachments, priority, min_score, email_type, topic_id, cluster_id.

        Results are deduplicated per email UID - only the best-scoring chunk
        per email is returned.
        """
        request = FilteredSearchRequest(query=query, top_k=top_k, **filter_values)
        plan, filters = self._prepare_filtered_search(request)
        if plan is None:
            return []
        return self._execute_filtered_search(plan, filters)

    def _prepare_filtered_search(self, request: FilteredSearchRequest) -> tuple[_SearchPlan | None, _SearchFilters]:
        """Normalize request inputs and derive a search plan."""
        return prepare_filtered_search_impl(self, request)

    def _resolve_allowed_uids(self, *, topic_id: int | None, cluster_id: int | None) -> set[str] | None:
        """Resolve semantic UID constraints for topic and cluster filters."""
        if not self.email_db or (topic_id is None and cluster_id is None):
            return None
        return self._resolve_semantic_uids(topic_id=topic_id, cluster_id=cluster_id)

    @staticmethod
    def _validate_filtered_search(*, top_k: int, min_score: float | None, filters: _SearchFilters) -> None:
        """Validate normalized filtered-search inputs."""
        if top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if top_k > MAX_TOP_K:
            raise ValueError(f"top_k must be <= {MAX_TOP_K}.")
        if min_score is not None and not (0.0 <= min_score <= 1.0):
            raise ValueError("min_score must be between 0.0 and 1.0.")
        if filters.date_from and filters.date_to and filters.date_from > filters.date_to:
            raise ValueError(f"date_from ({filters.date_from}) must be <= date_to ({filters.date_to}).")

    def _build_search_plan(
        self,
        query: str,
        lexical_query: str,
        top_k: int,
        filters: _SearchFilters,
        *,
        rerank: bool,
        hybrid: bool,
        retrieval_policy: RetrievalPolicy,
    ) -> _SearchPlan:
        settings = getattr(self, "settings", None)
        use_rerank = rerank or (settings.rerank_enabled if settings else False)
        use_hybrid = hybrid or (settings.hybrid_enabled if settings else False)
        rerank_multiplier = _RERANK_OVERFETCH if use_rerank else 1
        multiplier = (_FILTER_OVERFETCH if filters.has_filters else 1) * _DEDUP_OVERFETCH * rerank_multiplier
        fetch_size = max(top_k * multiplier, top_k)
        return _SearchPlan(
            query=query,
            lexical_query=lexical_query,
            top_k=top_k,
            use_rerank=use_rerank,
            use_hybrid=use_hybrid,
            fetch_size=fetch_size,
            retrieval_policy=retrieval_policy,
        )

    def _execute_filtered_search(self, plan: _SearchPlan, filters: _SearchFilters) -> list[SearchResult]:
        return execute_filtered_search_impl(self, plan, filters)

    def _post_process_candidates(
        self,
        plan: _SearchPlan,
        filters: _SearchFilters,
        raw_candidates: list[SearchResult],
    ) -> list[SearchResult]:
        """Apply filters, deduplication, reranking, and post-rerank score trimming."""
        return post_process_candidates_impl(
            self,
            plan,
            filters,
            self._active_mailbox_results(raw_candidates),
        )

    def _apply_rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        """Apply a configured local late-interaction runner or cross-encoder."""
        settings = getattr(self, "settings", None)
        use_late_interaction = bool(
            getattr(settings, "late_interaction_enabled", False)
            and getattr(settings, "late_interaction_runner", "")
            and getattr(settings, "late_interaction_model_path", "")
        )
        if use_late_interaction:
            try:
                if self._late_interaction_backend is None:
                    from .late_interaction_backend import LocalLateInteractionBackend

                    self._late_interaction_backend = LocalLateInteractionBackend(
                        runner_path=settings.late_interaction_runner,
                        model_path=settings.late_interaction_model_path,
                    )
                return self._late_interaction_backend.rerank(query, results, top_k=top_k)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Local late-interaction reranking failed; using cross-encoder", exc_info=True)

        if self._reranker is None:
            from .reranker import CrossEncoderReranker

            model = getattr(settings, "rerank_model", None)
            self._reranker = CrossEncoderReranker(model_name=model)
        return self._reranker.rerank(query, results, top_k=top_k)

    def _merge_hybrid(
        self,
        query: str,
        semantic_results: list[SearchResult],
        fetch_size: int,
        retrieval_policy: RetrievalPolicy | None = None,
    ) -> list[SearchResult]:
        """Merge semantic results with sparse/BM25 keyword results via RRF.

        Prefers BGE-M3 learned sparse vectors (from SparseIndex) when available,
        falling back to BM25 otherwise.
        """
        return merge_hybrid_impl(self, query, semantic_results, fetch_size, retrieval_policy=retrieval_policy)

    def _get_sparse_results(self, query: str, top_k: int) -> list[str] | None:
        """Try learned sparse retrieval. Returns None if unavailable."""
        return get_sparse_results_impl(self, query, top_k)

    def _get_bm25_results(self, query: str, top_k: int) -> list[str] | None:
        """BM25 keyword retrieval fallback."""
        return get_bm25_results_impl(self, query, top_k)

    def search_by_thread(self, conversation_id: str, top_k: int = 50) -> list[SearchResult]:
        """Load one canonical result per email in the requested conversation.

        Uses canonical SQLite metadata for ``conversation_id``, then deduplicates
        by email UID to return one result per email.
        """
        return self._active_mailbox_results(search_by_thread_impl(self, conversation_id, top_k))

    def _active_mailbox_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """Hide mailbox-only tombstones while preserving explicit source history."""
        database = self.email_db
        conn = database.conn if database is not None else None
        active = filter_active_mailbox_results(
            results,
            conn=conn,
        )
        canonical_folders = {
            _result_uid(result): str(result.metadata.get("folder") or "") for result in active if _result_uid(result)
        }
        projected = effective_source_folders(conn, canonical_folders)
        for result in active:
            uid = _result_uid(result)
            if uid in projected:
                result.metadata["source_folders"] = list(projected[uid])
        return active

    def list_senders(self, limit: int = 50) -> list[dict[str, Any]]:
        """List unique senders sorted by message count.

        Uses SQLite when available for O(1) query, falls back to
        iterating canonical vector metadata otherwise.
        """
        return list_senders_impl(self, limit=limit)

    def list_folders(self) -> list[dict[str, Any]]:
        """List all folders with email counts, sorted by count descending."""
        stats = self.stats()
        return [{"folder": name, "count": count} for name, count in stats.get("folders", {}).items()]

    def stats(self) -> dict[str, Any]:
        """Get summary statistics about the indexed archive.

        Uses SQLite for O(1) aggregates when available, falls back to
        iterating canonical vector metadata otherwise.
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
        """Clear derived vector rows without deleting relational email data."""
        logger.warning("Resetting vector indexes at %s", getattr(self, "vector_index_path", "<unconfigured>"))
        self.collection.reset()
        self.image_collection.reset()

    def _resolve_semantic_uids(
        self,
        topic_id: int | None = None,
        cluster_id: int | None = None,
    ) -> set[str]:
        """Pre-fetch email UIDs matching semantic filters from SQLite."""
        return resolve_semantic_uids_impl(self, topic_id=topic_id, cluster_id=cluster_id)

    _query_expander: Any = None  # Cached QueryExpander instance

    def _expand_query(self, query: str, *, scope: str | None = None) -> str:
        """Expand query with semantically related terms.

        Caches the QueryExpander instance (and its pre-computed vocab
        embeddings) on the retriever to avoid re-encoding the vocabulary
        on every call.
        """
        configured_scope = getattr(getattr(self, "settings", None), "rag_scope", "general")
        if not isinstance(configured_scope, str):
            configured_scope = "general"
        resolved_scope = configured_scope if scope is None else scope
        return expand_query_impl(self, query, scope=resolved_scope)

    def _expand_query_lanes(self, query: str, *, max_lanes: int = 4, scope: str | None = None) -> list[str]:
        """Expand a query into deterministic retrieval lanes."""
        configured_scope = getattr(getattr(self, "settings", None), "rag_scope", "general")
        if not isinstance(configured_scope, str):
            configured_scope = "general"
        resolved_scope = configured_scope if scope is None else scope
        return expand_query_lanes_impl(self, query, max_lanes=max_lanes, scope=resolved_scope)

    # _email_dedup_key is used by list_senders - delegate to result_filters
    _email_dedup_key = staticmethod(_email_dedup_key)
