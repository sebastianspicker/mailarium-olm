"""Hybrid retrieval helpers extracted from ``src.retriever``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult

logger = logging.getLogger(__name__)


def merge_hybrid_impl(
    instance: EmailRetriever,
    query: str,
    semantic_results: list[SearchResult],
    fetch_size: int,
) -> list[SearchResult]:
    """Merge semantic results with sparse/BM25 keyword results via RRF."""
    try:
        keyword_ids = instance._get_sparse_results(query, fetch_size)

        if keyword_ids is None:
            keyword_ids = instance._get_bm25_results(query, fetch_size)

        if not keyword_ids:
            return semantic_results

        from .bm25_index import reciprocal_rank_fusion

        semantic_ids = [result.chunk_id for result in semantic_results]
        fused_ids = reciprocal_rank_fusion(semantic_ids, keyword_ids)

        result_map = {result.chunk_id: result for result in semantic_results}

        missing_ids = [chunk_id for chunk_id in fused_ids if chunk_id not in result_map]
        if missing_ids and instance.collection:
            try:
                fetched = instance.collection.get(
                    ids=missing_ids,
                    include=["documents", "metadatas"],
                )
                fetched_docs = fetched.get("documents") or []
                fetched_metas = fetched.get("metadatas") or []
                for index, chunk_id in enumerate(fetched.get("ids", [])):
                    from .retriever import SearchResult

                    doc = fetched_docs[index] if index < len(fetched_docs) else ""
                    meta = fetched_metas[index] if index < len(fetched_metas) else {}
                    result_map[chunk_id] = SearchResult(
                        chunk_id=chunk_id,
                        text=doc or "",
                        metadata=meta or {},
                        distance=0.5,
                    )
            except Exception:
                logger.debug(
                    "Hybrid merge: failed to fetch %d keyword-only results",
                    len(missing_ids),
                    exc_info=True,
                )

        merged = [result_map[chunk_id] for chunk_id in fused_ids if chunk_id in result_map]
        seen = set(fused_ids)
        for result in semantic_results:
            if result.chunk_id not in seen:
                merged.append(result)
        return merged
    except ImportError:
        logger.warning("rank_bm25 not installed; hybrid search disabled")
        return semantic_results
    except Exception:
        logger.warning("Hybrid merge failed, returning semantic-only results", exc_info=True)
        return semantic_results


def get_sparse_results_impl(instance: EmailRetriever, query: str, top_k: int) -> list[str] | None:
    """Try learned sparse retrieval. Returns None if unavailable."""
    if not instance.embedder.has_sparse:
        return None

    db = instance.email_db
    if db is None:
        return None

    try:
        if instance._sparse_index is None:
            from .sparse_index import SparseIndex

            instance._sparse_index = SparseIndex()
            instance._sparse_index.build_from_db(db)
            try:
                instance._sparse_build_count = instance.collection.count()
            except Exception:
                instance._sparse_build_count = -1
        else:
            try:
                collection_count = instance.collection.count()
                last_count = getattr(instance, "_sparse_build_count", None)
                if last_count != collection_count:
                    instance._sparse_index.build_from_db(db)
                    instance._sparse_build_count = collection_count
            except Exception:
                logger.debug("Skipping sparse index staleness check", exc_info=True)

        if not instance._sparse_index.is_built or instance._sparse_index.doc_count == 0:
            return None

        query_sparse = instance.embedder.encode_sparse([query])
        if not query_sparse or not query_sparse[0]:
            return None

        results = instance._sparse_index.search(query_sparse[0], top_k=top_k)
        return [chunk_id for chunk_id, _ in results] if results else None
    except Exception:
        logger.debug("Sparse retrieval failed", exc_info=True)
        return None


def get_bm25_results_impl(instance: EmailRetriever, query: str, top_k: int) -> list[str] | None:
    """BM25 keyword retrieval fallback."""
    try:
        if instance._bm25_index is None:
            from .bm25_index import BM25Index

            instance._bm25_index = BM25Index()
            instance._bm25_index.build_from_collection(instance.collection)
        else:
            try:
                collection_count = instance.collection.count()
                if len(instance._bm25_index._chunk_ids) != collection_count:
                    instance._bm25_index.build_from_collection(instance.collection)
            except Exception:
                logger.debug("Skipping BM25 staleness check", exc_info=True)

        if not instance._bm25_index.is_built:
            return None

        results = instance._bm25_index.search(query, top_k=top_k)
        return [chunk_id for chunk_id, _ in results] if results else None
    except ImportError:
        return None
    except Exception:
        logger.debug("BM25 retrieval failed", exc_info=True)
        return None
