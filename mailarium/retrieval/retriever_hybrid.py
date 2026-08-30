"""Fuse dense retrieval with learned-sparse or BM25 recall and diagnostics."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .retrieval_policy import RetrievalPolicy, resolve_retrieval_policy

if TYPE_CHECKING:
    from .retriever import SearchEngine, SearchResult

logger = logging.getLogger(__name__)


def _collection_revision(instance: SearchEngine) -> tuple[int, str]:
    """Get the current collection revision info (count and index_revision metadata)."""
    collection = getattr(instance, "collection", None)
    if collection is None:
        return (0, "")
    try:
        count = int(collection.count())
    except Exception:
        count = -1
    metadata = dict(getattr(collection, "metadata", {}) or {})
    return (count, str(metadata.get("index_revision") or ""))


def _record_sparse_diagnostic(instance: SearchEngine, key: str, value: Any) -> None:
    debug = getattr(instance, "last_search_debug", None)
    if not isinstance(debug, dict):
        return
    sparse_diag = debug.get("sparse_diagnostics")
    if not isinstance(sparse_diag, dict):
        sparse_diag = {}
        debug["sparse_diagnostics"] = sparse_diag
    sparse_diag[key] = value


def _record_bm25_diagnostic(instance: SearchEngine, payload: dict[str, Any]) -> None:
    debug = getattr(instance, "last_search_debug", None)
    if not isinstance(debug, dict):
        return
    debug["bm25_diagnostics"] = dict(payload)


def merge_hybrid_impl(
    instance: SearchEngine,
    query: str,
    semantic_results: list[SearchResult],
    fetch_size: int,
    *,
    retrieval_policy: RetrievalPolicy | None = None,
) -> list[SearchResult]:
    """Merge semantic and keyword results using query-adaptive weighted RRF."""
    policy = retrieval_policy or resolve_retrieval_policy(query)
    try:
        keyword_ids = _hybrid_keyword_ids(instance, query, fetch_size)
        if not keyword_ids:
            return semantic_results
        merged = _merged_hybrid_results(instance, query, semantic_results, keyword_ids, policy)
        _record_fusion_diagnostic(instance, policy)
        return merged
    except ImportError:
        logger.warning("rank_bm25 not installed; hybrid search disabled")
        return semantic_results
    except Exception:
        logger.warning("Hybrid merge failed, returning semantic-only results", exc_info=True)
        return semantic_results


def _hybrid_keyword_ids(instance: SearchEngine, query: str, fetch_size: int) -> list[str] | None:
    """Prefer learned sparse retrieval and retain BM25 as its fallback."""
    sparse_ids = instance._get_sparse_results(query, fetch_size)
    return sparse_ids if sparse_ids is not None else instance._get_bm25_results(query, fetch_size)


def _merged_hybrid_results(
    instance: SearchEngine,
    query: str,
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
    _add_keyword_only_results(instance, fused_ids, result_map)
    return _rank_hybrid_results(semantic_results, fused_ids, result_map)


def _record_fusion_diagnostic(instance: SearchEngine, policy: RetrievalPolicy) -> None:
    """Expose the exact fusion weights used for the current request."""
    debug = getattr(instance, "last_search_debug", None)
    if not isinstance(debug, dict):
        return
    debug["fusion"] = {
        "method": "weighted_reciprocal_rank_fusion",
        "semantic_weight": policy.semantic_weight,
        "keyword_weight": policy.keyword_weight,
    }


def _add_keyword_only_results(instance: SearchEngine, fused_ids: list[str], result_map: dict[str, SearchResult]) -> None:
    """Populate the result map with query-independent keyword-only records."""
    missing_ids = [chunk_id for chunk_id in fused_ids if chunk_id not in result_map]
    if not missing_ids or not instance.collection:
        return
    try:
        fetched = instance.collection.get(ids=missing_ids, include=["documents", "metadatas"])
        documents = fetched.get("documents") or []
        metadatas = fetched.get("metadatas") or []
        for index, chunk_id in enumerate(fetched.get("ids", [])):
            result_map[chunk_id] = _keyword_only_result(chunk_id, documents, metadatas, index)
    except Exception:
        logger.debug("Hybrid merge: failed to fetch %d keyword-only results", len(missing_ids), exc_info=True)


def _keyword_only_result(chunk_id: str, documents: list[Any], metadatas: list[Any], index: int) -> SearchResult:
    """Create the stable synthetic-score row for a keyword-only chunk."""
    from .retriever import SearchResult as SearchResultModel

    metadata = metadatas[index] if index < len(metadatas) else {}
    payload = dict(metadata) if isinstance(metadata, Mapping) else {}
    payload.update(score_kind="keyword_fused", score_calibration="synthetic", hybrid_source="keyword_only")
    text = documents[index] if index < len(documents) else ""
    return SearchResultModel(chunk_id=chunk_id, text=text or "", metadata=payload, distance=0.5)


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


def get_sparse_results_impl(instance: SearchEngine, query: str, top_k: int) -> list[str] | None:
    """Try learned sparse retrieval. Returns None if unavailable."""
    db = instance.email_db
    if not instance.embedder.has_sparse or db is None:
        return None
    try:
        sparse_index = _current_sparse_index(instance, db)
        if not sparse_index.is_built or sparse_index.doc_count == 0:
            _record_sparse_diagnostic(instance, "status", "empty")
            return None
        _record_sparse_coverage(instance, sparse_index)
        return _sparse_query_ids(instance, sparse_index, query, top_k)
    except Exception:
        _record_sparse_diagnostic(instance, "status", "error")
        logger.debug("Sparse retrieval failed", exc_info=True)
        return None


def _current_sparse_index(instance: SearchEngine, db: Any) -> Any:
    """Create or refresh the sparse index against the collection revision."""
    if instance._sparse_index is None:
        from .sparse_index import SparseIndex

        instance._sparse_index = SparseIndex()
        instance._sparse_index.build_from_db(
            db,
            model_id=instance.settings.sparse_model,
            model_revision=instance.settings.sparse_model_revision,
        )
        instance._sparse_build_count = _collection_revision(instance)
        return instance._sparse_index
    try:
        revision = _collection_revision(instance)
        if getattr(instance, "_sparse_build_count", None) != revision:
            instance._sparse_index.build_from_db(
                db,
                model_id=instance.settings.sparse_model,
                model_revision=instance.settings.sparse_model_revision,
            )
            instance._sparse_build_count = revision
    except Exception:
        logger.debug("Skipping sparse index staleness check", exc_info=True)
    return instance._sparse_index


def _record_sparse_coverage(instance: SearchEngine, sparse_index: Any) -> None:
    """Preserve full versus partial sparse-index diagnostics."""
    collection_count, _revision = _collection_revision(instance)
    indexed_docs = int(sparse_index.doc_count)
    partial = collection_count > 0 and indexed_docs != collection_count
    _record_sparse_diagnostic(
        instance,
        "coverage",
        {"status": "partial" if partial else "full", "indexed_docs": indexed_docs, "collection_docs": int(collection_count)},
    )
    if partial:
        logger.debug(
            "Sparse coverage incomplete (%d/%d); continuing with partial sparse retrieval", indexed_docs, collection_count
        )


def _sparse_query_ids(instance: SearchEngine, sparse_index: Any, query: str, top_k: int) -> list[str] | None:
    """Encode the query and return sparse-hit IDs while retaining status diagnostics."""
    query_sparse = instance.embedder.encode_sparse_query([query])
    if not query_sparse or not query_sparse[0]:
        _record_sparse_diagnostic(instance, "status", "query_encoding_empty")
        return None
    results = sparse_index.search(query_sparse[0], top_k=top_k)
    _record_sparse_diagnostic(instance, "status", "ok")
    return [chunk_id for chunk_id, _ in results] if results else None


def get_bm25_results_impl(instance: SearchEngine, query: str, top_k: int) -> list[str] | None:
    """BM25 keyword retrieval fallback."""
    try:
        bm25_index = _current_bm25_index(instance)
        if not bm25_index.is_built:
            return None
        results = _bm25_search_results(instance, bm25_index, query, top_k)
        return [chunk_id for chunk_id, _ in results] if results else None
    except ImportError:
        return None
    except Exception:
        logger.debug("BM25 retrieval failed", exc_info=True)
        return None


def _current_bm25_index(instance: SearchEngine) -> Any:
    """Create or refresh BM25 only when the collection revision changes."""
    if instance._bm25_index is None:
        from .bm25_index import BM25Index

        instance._bm25_index = BM25Index()
        instance._bm25_index.build_from_collection(instance.collection)
        instance._bm25_build_revision = _collection_revision(instance)
        return instance._bm25_index
    try:
        revision = _collection_revision(instance)
        if getattr(instance, "_bm25_build_revision", None) != revision:
            instance._bm25_index.build_from_collection(instance.collection)
            instance._bm25_build_revision = revision
    except Exception:
        logger.debug("Skipping BM25 staleness check", exc_info=True)
    return instance._bm25_index


def _bm25_search_results(instance: SearchEngine, bm25_index: Any, query: str, top_k: int) -> Any:
    """Use diagnostic search when available, retaining fallback search semantics."""
    diagnostic_search = getattr(bm25_index, "search_with_diagnostics", None)
    if not callable(diagnostic_search):
        return bm25_index.search(query, top_k=top_k)
    diagnostic_result = diagnostic_search(query, top_k=top_k)
    if not isinstance(diagnostic_result, tuple) or len(diagnostic_result) != 2:
        return bm25_index.search(query, top_k=top_k)
    results, diagnostics = diagnostic_result
    if isinstance(diagnostics, dict):
        _record_bm25_diagnostic(instance, diagnostics)
    return results
