"""Hybrid retrieval helpers extracted from ``src.retriever``."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .query_expander import legal_support_query_profile

if TYPE_CHECKING:
    from .retriever import EmailRetriever, SearchResult

logger = logging.getLogger(__name__)


def _collection_revision(instance: EmailRetriever) -> tuple[int, str]:
    collection = getattr(instance, "collection", None)
    if collection is None:
        return (0, "")
    try:
        count = int(collection.count())
    except Exception:
        count = -1
    metadata = dict(getattr(collection, "metadata", {}) or {})
    return (count, str(metadata.get("index_revision") or ""))


def _result_text(result: SearchResult) -> str:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    return " ".join(
        part
        for part in (
            str(result.text or ""),
            str(metadata.get("subject") or ""),
            str(metadata.get("attachment_name") or ""),
            str(metadata.get("attachment_filename") or ""),
            str(metadata.get("filename") or ""),
            str(metadata.get("attachment_type") or ""),
        )
        if part
    ).lower()


def _legal_support_result_boost(query: str, result: SearchResult) -> int:
    """Return a bounded legal-support retrieval boost for one result."""
    profile = legal_support_query_profile(query)
    if not profile["is_legal_support"]:
        return 0
    text = _result_text(result)
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    boost = 0
    if "chronology" in profile["intents"]:
        chronology_terms = (
            "meeting",
            "calendar",
            "timeline",
            "chronology",
            "attendance",
            "time record",
            "timesheet",
        )
        if any(term in text for term in chronology_terms):
            boost += 4
        if str(metadata.get("is_calendar_message") or "").lower() in {"true", "1"}:
            boost += 3
    if "participation" in profile["intents"] and any(
        term in text for term in ("sbv", "personalrat", "betriebsrat", "participation", "consultation", "bem")
    ):
        boost += 5
    if "contradiction" in profile["intents"] and any(
        term in text
        for term in (
            " not ",
            " without ",
            " didn't ",
            " kein ",
            " keine ",
            " nicht ",
        )
    ):
        boost += 4
    if "comparator" in profile["intents"] and any(
        term in text for term in ("comparator", "peer", "unequal", "similarly situated", "other employee", "vergleich")
    ):
        boost += 4
    if "document_request" in profile["intents"] and any(
        term in text for term in ("record", "document", "attachment", "file", "custodian", "preserve")
    ):
        boost += 2
    if metadata.get("attachment_filename") or metadata.get("attachment_name") or metadata.get("filename"):
        boost += 1
    return boost


def _record_sparse_diagnostic(instance: EmailRetriever, key: str, value: Any) -> None:
    debug = getattr(instance, "_last_search_debug", None)
    if not isinstance(debug, dict):
        return
    sparse_diag = debug.get("sparse_diagnostics")
    if not isinstance(sparse_diag, dict):
        sparse_diag = {}
        debug["sparse_diagnostics"] = sparse_diag
    sparse_diag[key] = value


def _record_bm25_diagnostic(instance: EmailRetriever, payload: dict[str, Any]) -> None:
    debug = getattr(instance, "_last_search_debug", None)
    if not isinstance(debug, dict):
        return
    debug["bm25_diagnostics"] = dict(payload)


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
                    meta_dict: dict[str, Any]
                    if isinstance(meta, Mapping):
                        meta_dict = {
                            **dict(meta),
                            "score_kind": "keyword_fused",
                            "score_calibration": "synthetic",
                            "hybrid_source": "keyword_only",
                        }
                    else:
                        meta_dict = {}
                    result_map[chunk_id] = SearchResult(
                        chunk_id=chunk_id,
                        text=doc or "",
                        metadata=meta_dict,
                        distance=0.5,
                    )
            except Exception:
                logger.debug(
                    "Hybrid merge: failed to fetch %d keyword-only results",
                    len(missing_ids),
                    exc_info=True,
                )

        fused_rank = {chunk_id: index for index, chunk_id in enumerate(fused_ids)}
        merged = [result_map[chunk_id] for chunk_id in fused_ids if chunk_id in result_map]
        merged.sort(
            key=lambda result: (
                -_legal_support_result_boost(query, result),
                fused_rank.get(result.chunk_id, len(fused_ids)),
                result.distance,
            )
        )
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
            instance._sparse_build_count = _collection_revision(instance)
        else:
            try:
                collection_count, collection_revision = _collection_revision(instance)
                last_count = getattr(instance, "_sparse_build_count", None)
                if last_count != (collection_count, collection_revision):
                    instance._sparse_index.build_from_db(db)
                    instance._sparse_build_count = (collection_count, collection_revision)
            except Exception:
                logger.debug("Skipping sparse index staleness check", exc_info=True)

        if not instance._sparse_index.is_built or instance._sparse_index.doc_count == 0:
            _record_sparse_diagnostic(instance, "status", "empty")
            return None
        collection_count, _collection_revision_value = _collection_revision(instance)
        if collection_count > 0 and instance._sparse_index.doc_count != collection_count:
            _record_sparse_diagnostic(
                instance,
                "coverage",
                {
                    "status": "partial",
                    "indexed_docs": int(instance._sparse_index.doc_count),
                    "collection_docs": int(collection_count),
                },
            )
            logger.debug(
                "Sparse coverage incomplete (%d/%d); continuing with partial sparse retrieval",
                instance._sparse_index.doc_count,
                collection_count,
            )
        else:
            _record_sparse_diagnostic(
                instance,
                "coverage",
                {
                    "status": "full",
                    "indexed_docs": int(instance._sparse_index.doc_count),
                    "collection_docs": int(collection_count),
                },
            )

        query_sparse = instance.embedder.encode_sparse([query])
        if not query_sparse or not query_sparse[0]:
            _record_sparse_diagnostic(instance, "status", "query_encoding_empty")
            return None

        results = instance._sparse_index.search(query_sparse[0], top_k=top_k)
        _record_sparse_diagnostic(instance, "status", "ok")
        return [chunk_id for chunk_id, _ in results] if results else None
    except Exception:
        _record_sparse_diagnostic(instance, "status", "error")
        logger.debug("Sparse retrieval failed", exc_info=True)
        return None


def get_bm25_results_impl(instance: EmailRetriever, query: str, top_k: int) -> list[str] | None:
    """BM25 keyword retrieval fallback."""
    try:
        if instance._bm25_index is None:
            from .bm25_index import BM25Index

            instance._bm25_index = BM25Index()
            instance._bm25_index.build_from_collection(instance.collection)
            instance._bm25_build_revision = _collection_revision(instance)
        else:
            try:
                current_revision = _collection_revision(instance)
                if getattr(instance, "_bm25_build_revision", None) != current_revision:
                    instance._bm25_index.build_from_collection(instance.collection)
                    instance._bm25_build_revision = current_revision
            except Exception:
                logger.debug("Skipping BM25 staleness check", exc_info=True)

        if not instance._bm25_index.is_built:
            return None

        results = None
        diagnostic_search = getattr(instance._bm25_index, "search_with_diagnostics", None)
        if callable(diagnostic_search):
            diagnostic_result = diagnostic_search(query, top_k=top_k)
            if isinstance(diagnostic_result, tuple) and len(diagnostic_result) == 2:
                results, diagnostics = diagnostic_result
                if isinstance(diagnostics, dict):
                    _record_bm25_diagnostic(instance, diagnostics)
        if results is None:
            results = instance._bm25_index.search(query, top_k=top_k)
        return [chunk_id for chunk_id, _ in results] if results else None
    except ImportError:
        return None
    except Exception:
        logger.debug("BM25 retrieval failed", exc_info=True)
        return None
