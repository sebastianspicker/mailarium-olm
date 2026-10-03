"""Fuse dense retrieval with learned-sparse or BM25 recall and diagnostics."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .models import SearchResult
from .retrieval_policy import RetrievalPolicy, resolve_retrieval_policy

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase
    from mailarium.platform.settings import Settings

    from .bm25_index import BM25Index
    from .diagnostics import SearchDiagnostics
    from .query_encoding import QueryEncoder
    from .sparse_index import SparseIndex

logger = logging.getLogger(__name__)


def collection_revision(collection: Any) -> tuple[int, str]:
    """Get the current collection revision info (count and index_revision metadata)."""
    if collection is None:
        return (0, "")
    try:
        count = int(collection.count())
    except Exception:
        count = -1
    metadata = dict(getattr(collection, "metadata", {}) or {})
    return (count, str(metadata.get("index_revision") or ""))


class SparseRetriever:
    """Own the learned-sparse index and rebuild it when the text collection revision changes."""

    def __init__(
        self,
        *,
        collection: Any,
        database: ArchiveDatabase | None,
        encoder: QueryEncoder,
        settings: Settings,
        diagnostics: SearchDiagnostics,
    ) -> None:
        """Bind the canonical sparse vectors, the query encoder, and the diagnostics owner."""
        self._collection = collection
        self._database = database
        self._encoder = encoder
        self._settings = settings
        self._diagnostics = diagnostics
        self._index: SparseIndex | None = None
        self._build_revision: tuple[int, str] | None = None

    @property
    def index(self) -> SparseIndex | None:
        """Return the sparse index once a query has built it."""
        return self._index

    def ranked_ids(self, query: str, top_k: int) -> list[str] | None:
        """Try learned sparse retrieval. Returns None if unavailable."""
        db = self._database
        if not self._encoder.embedder.has_sparse or db is None:
            return None
        try:
            sparse_index = self._current_index(db)
            if not sparse_index.is_built or sparse_index.doc_count == 0:
                self._record("status", "empty")
                return None
            self._record_coverage(sparse_index)
            return self._query_ids(sparse_index, query, top_k)
        except Exception:
            self._record("status", "error")
            logger.debug("Sparse retrieval failed", exc_info=True)
            return None

    def release(self) -> list[Any]:
        """Drop the sparse index and archive reference, returning the index for closing."""
        index, self._index = self._index, None
        self._database = None
        return [index]

    def _current_index(self, db: ArchiveDatabase) -> Any:
        """Create or refresh the sparse index against the collection revision."""
        if self._index is None:
            from .sparse_index import SparseIndex

            self._index = SparseIndex()
            self._index.build_from_db(
                db,
                model_id=self._settings.sparse_model,
                model_revision=self._settings.sparse_model_revision,
            )
            self._build_revision = collection_revision(self._collection)
            return self._index
        try:
            revision = collection_revision(self._collection)
            if self._build_revision != revision:
                self._index.build_from_db(
                    db,
                    model_id=self._settings.sparse_model,
                    model_revision=self._settings.sparse_model_revision,
                )
                self._build_revision = revision
        except Exception:
            logger.debug("Skipping sparse index staleness check", exc_info=True)
        return self._index

    def _record(self, key: str, value: Any) -> None:
        debug = self._diagnostics.search_debug
        sparse_diag = debug.get("sparse_diagnostics")
        if not isinstance(sparse_diag, dict):
            sparse_diag = {}
            debug["sparse_diagnostics"] = sparse_diag
        sparse_diag[key] = value

    def _record_coverage(self, sparse_index: Any) -> None:
        """Preserve full versus partial sparse-index diagnostics."""
        collection_count, _revision = collection_revision(self._collection)
        indexed_docs = int(sparse_index.doc_count)
        partial = collection_count > 0 and indexed_docs != collection_count
        self._record(
            "coverage",
            {"status": "partial" if partial else "full", "indexed_docs": indexed_docs, "collection_docs": int(collection_count)},
        )
        if partial:
            logger.debug(
                "Sparse coverage incomplete (%d/%d); continuing with partial sparse retrieval", indexed_docs, collection_count
            )

    def _query_ids(self, sparse_index: Any, query: str, top_k: int) -> list[str] | None:
        """Encode the query and return sparse-hit IDs while retaining status diagnostics."""
        query_sparse = self._encoder.embedder.encode_sparse_query([query])
        if not query_sparse or not query_sparse[0]:
            self._record("status", "query_encoding_empty")
            return None
        results = sparse_index.search(query_sparse[0], top_k=top_k)
        self._record("status", "ok")
        return [chunk_id for chunk_id, _ in results] if results else None


class BM25Retriever:
    """Own the BM25 keyword index and rebuild it when the text collection revision changes."""

    def __init__(self, *, collection: Any, diagnostics: SearchDiagnostics) -> None:
        """Bind the text collection that BM25 indexes and the diagnostics owner."""
        self._collection = collection
        self._diagnostics = diagnostics
        self._index: BM25Index | None = None
        self._build_revision: tuple[int, str] | None = None

    def ranked_ids(self, query: str, top_k: int) -> list[str] | None:
        """BM25 keyword retrieval fallback."""
        try:
            bm25_index = self._current_index()
            if not bm25_index.is_built:
                return None
            results = self._search_results(bm25_index, query, top_k)
            return [chunk_id for chunk_id, _ in results] if results else None
        except ImportError:
            return None
        except Exception:
            logger.debug("BM25 retrieval failed", exc_info=True)
            return None

    def release(self) -> list[Any]:
        """Drop the BM25 index and return it for closing."""
        index, self._index = self._index, None
        return [index]

    def _current_index(self) -> Any:
        """Create or refresh BM25 only when the collection revision changes."""
        if self._index is None:
            from .bm25_index import BM25Index

            self._index = BM25Index()
            self._index.build_from_collection(self._collection)
            self._build_revision = collection_revision(self._collection)
            return self._index
        try:
            revision = collection_revision(self._collection)
            if self._build_revision != revision:
                self._index.build_from_collection(self._collection)
                self._build_revision = revision
        except Exception:
            logger.debug("Skipping BM25 staleness check", exc_info=True)
        return self._index

    def _search_results(self, bm25_index: Any, query: str, top_k: int) -> Any:
        """Use diagnostic search when available, retaining fallback search semantics."""
        diagnostic_search = getattr(bm25_index, "search_with_diagnostics", None)
        if not callable(diagnostic_search):
            return bm25_index.search(query, top_k=top_k)
        diagnostic_result = diagnostic_search(query, top_k=top_k)
        if not isinstance(diagnostic_result, tuple) or len(diagnostic_result) != 2:
            return bm25_index.search(query, top_k=top_k)
        results, diagnostics = diagnostic_result
        if isinstance(diagnostics, dict):
            self._diagnostics.record_search_debug("bm25_diagnostics", dict(diagnostics))
        return results


class HybridFusion:
    """Merge semantic results with sparse or BM25 keyword results via weighted RRF."""

    def __init__(
        self,
        *,
        collection: Any,
        sparse: SparseRetriever,
        bm25: BM25Retriever,
        diagnostics: SearchDiagnostics,
    ) -> None:
        """Compose both keyword channels and the collection that hydrates keyword-only hits."""
        self._collection = collection
        self._sparse = sparse
        self._bm25 = bm25
        self._diagnostics = diagnostics

    def merge(
        self,
        query: str,
        semantic_results: list[SearchResult],
        fetch_size: int,
        *,
        retrieval_policy: RetrievalPolicy | None = None,
    ) -> list[SearchResult]:
        """Merge semantic and keyword results using query-adaptive weighted RRF.

        Prefers learned sparse vectors when available, falling back to BM25 otherwise.
        """
        policy = retrieval_policy or resolve_retrieval_policy(query)
        try:
            keyword_ids = self._keyword_ids(query, fetch_size)
            if not keyword_ids:
                return semantic_results
            merged = self._merged_results(semantic_results, keyword_ids, policy)
            self._record_fusion(policy)
            return merged
        except ImportError:
            logger.warning("rank_bm25 not installed; hybrid search disabled")
            return semantic_results
        except Exception:
            logger.warning("Hybrid merge failed, returning semantic-only results", exc_info=True)
            return semantic_results

    def _keyword_ids(self, query: str, fetch_size: int) -> list[str] | None:
        """Prefer learned sparse retrieval and retain BM25 as its fallback."""
        sparse_ids = self._sparse.ranked_ids(query, fetch_size)
        return sparse_ids if sparse_ids is not None else self._bm25.ranked_ids(query, fetch_size)

    def _merged_results(
        self,
        semantic_results: list[SearchResult],
        keyword_ids: list[str],
        retrieval_policy: RetrievalPolicy,
    ) -> list[SearchResult]:
        """Fuse rankings, add keyword-only rows, then preserve semantic tail order."""
        from .bm25_index import reciprocal_rank_fusion

        fused_ids = reciprocal_rank_fusion(
            [result.chunk_id for result in semantic_results],
            keyword_ids,
            semantic_weight=retrieval_policy.semantic_weight,
            keyword_weight=retrieval_policy.keyword_weight,
        )
        result_map = {result.chunk_id: result for result in semantic_results}
        self._add_keyword_only_results(fused_ids, result_map)
        return _rank_hybrid_results(semantic_results, fused_ids, result_map)

    def _record_fusion(self, policy: RetrievalPolicy) -> None:
        """Expose the exact fusion weights used for the current request."""
        self._diagnostics.record_search_debug(
            "fusion",
            {
                "method": "weighted_reciprocal_rank_fusion",
                "semantic_weight": policy.semantic_weight,
                "keyword_weight": policy.keyword_weight,
            },
        )

    def _add_keyword_only_results(self, fused_ids: list[str], result_map: dict[str, SearchResult]) -> None:
        """Populate the result map with query-independent keyword-only records."""
        missing_ids = [chunk_id for chunk_id in fused_ids if chunk_id not in result_map]
        if not missing_ids or not self._collection:
            return
        try:
            fetched = self._collection.get(ids=missing_ids, include=["documents", "metadatas"])
            documents = fetched.get("documents") or []
            metadatas = fetched.get("metadatas") or []
            for index, chunk_id in enumerate(fetched.get("ids", [])):
                result_map[chunk_id] = _keyword_only_result(chunk_id, documents, metadatas, index)
        except Exception:
            logger.debug("Hybrid merge: failed to fetch %d keyword-only results", len(missing_ids), exc_info=True)


def _keyword_only_result(chunk_id: str, documents: list[Any], metadatas: list[Any], index: int) -> SearchResult:
    """Create the stable synthetic-score row for a keyword-only chunk."""
    metadata = metadatas[index] if index < len(metadatas) else {}
    payload = dict(metadata) if isinstance(metadata, Mapping) else {}
    payload.update(score_kind="keyword_fused", score_calibration="synthetic", hybrid_source="keyword_only")
    text = documents[index] if index < len(documents) else ""
    return SearchResult(chunk_id=chunk_id, text=text or "", metadata=payload, distance=0.5)


def _rank_hybrid_results(
    semantic_results: list[SearchResult],
    fused_ids: list[str],
    result_map: dict[str, SearchResult],
) -> list[SearchResult]:
    """Apply fused rank and preserve the semantic tail."""
    fused_rank = {chunk_id: index for index, chunk_id in enumerate(fused_ids)}
    merged = [result_map[chunk_id] for chunk_id in fused_ids if chunk_id in result_map]
    merged.sort(
        key=lambda result: (
            fused_rank[result.chunk_id],
            result.distance,
        )
    )
    seen = set(fused_ids)
    return merged + [result for result in semantic_results if result.chunk_id not in seen]
