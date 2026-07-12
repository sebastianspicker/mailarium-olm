"""ColBERT MaxSim reranking using BGE-M3 token-level embeddings.

Uses the same BGE-M3 model as the primary embedder — no additional model
load required.  ColBERT scores are computed on-the-fly for top-N candidates
(typically 30-50), trading ~25MB temporary memory for high-precision reranking.

Particularly effective for:
- German compound words (token-level matching handles subwords)
- Legal evidence queries (exact phrase matching)
"""

from __future__ import annotations

# pylint: disable=too-many-branches,too-many-locals
import collections
import logging
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .multi_vector_embedder import MultiVectorEmbedder
    from .retriever import SearchResult

logger = logging.getLogger(__name__)


_DOC_VEC_CACHE_MAX = 256


class ColBERTReranker:
    """Re-score search results using ColBERT MaxSim token-level matching.

    Unlike cross-encoders, ColBERT reranking uses the same BGE-M3 model
    that produced the initial embeddings, so there is no extra model load.

    Document token vectors are cached by chunk ID to avoid re-encoding
    the same documents across successive rerank calls.
    """

    def __init__(self, embedder: MultiVectorEmbedder) -> None:
        self._embedder = embedder
        # Bounded LRU cache: chunk_id -> ColBERT token vectors (np.ndarray)
        self._doc_vec_cache: collections.OrderedDict[str, np.ndarray | None] = collections.OrderedDict()

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """Re-rank results by ColBERT MaxSim score.

        Encodes the query and all candidate documents at the token level,
        then computes MaxSim scores for reranking.

        Args:
            query: The original search query.
            results: Candidate results from initial retrieval.
            top_k: Number of top results to return (default: all).

        Returns:
            Re-ranked list of SearchResult objects sorted by descending
            ColBERT score. The ``distance`` field is updated.
        """
        if not results:
            return []

        if not self._embedder.has_colbert:
            logger.debug("ColBERT not available, returning results unchanged")
            return results[:top_k] if top_k else results

        query_vecs = self._embedder.encode_colbert([query])
        if not query_vecs or query_vecs[0] is None:
            return results[:top_k] if top_k else results

        q_vecs = query_vecs[0]  # (num_query_tokens, dim)

        doc_vecs_by_id = self._document_vectors(results)

        if not doc_vecs_by_id:
            return results[:top_k] if top_k else results

        scored = self._score_results(q_vecs, results, doc_vecs_by_id)
        return self._reranked_results(scored, top_k)

    def _document_vectors(self, results: list[SearchResult]) -> dict[str, np.ndarray | None]:
        """Return cached vectors plus successfully encoded cache misses."""
        cached, uncached = self._split_cached_results(results)
        if not uncached:
            return cached
        new_vecs = self._embedder.encode_colbert([result.text for result in uncached])
        if not new_vecs or len(new_vecs) != len(uncached):
            if new_vecs:
                logger.warning("ColBERT encode returned %d vectors for %d texts — skipping cache", len(new_vecs), len(uncached))
            return cached
        for result, vectors in zip(uncached, new_vecs, strict=True):
            cached[result.chunk_id] = vectors
            self._doc_vec_cache[result.chunk_id] = vectors
            if len(self._doc_vec_cache) > _DOC_VEC_CACHE_MAX:
                self._doc_vec_cache.popitem(last=False)
        return cached

    def _split_cached_results(self, results: list[SearchResult]) -> tuple[dict[str, np.ndarray | None], list[SearchResult]]:
        """Separate cache hits from documents that still require encoding."""
        cached: dict[str, np.ndarray | None] = {}
        uncached: list[SearchResult] = []
        for result in results:
            if result.chunk_id not in self._doc_vec_cache:
                uncached.append(result)
                continue
            self._doc_vec_cache.move_to_end(result.chunk_id)
            cached[result.chunk_id] = self._doc_vec_cache[result.chunk_id]
        return cached, uncached

    @staticmethod
    def _score_results(
        query_vectors: np.ndarray, results: list[SearchResult], vectors_by_id: dict[str, np.ndarray | None]
    ) -> list[tuple[SearchResult, float]]:
        """Score each original candidate while preserving candidate order for ties."""
        scored = [
            (result, maxsim(query_vectors, vectors) if vectors is not None and len(vectors) else 0.0)
            for result in results
            for vectors in [vectors_by_id.get(result.chunk_id)]
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)

    @staticmethod
    def _reranked_results(scored: list[tuple[SearchResult, float]], top_k: int | None) -> list[SearchResult]:
        """Convert scores back to the public SearchResult shape."""
        from .retriever import SearchResult as SearchResultModel

        limit = top_k if top_k is not None else len(scored)
        return [
            SearchResultModel(result.chunk_id, result.text, result.metadata, max(0.0, 1.0 - score))
            for result, score in scored[:limit]
        ]


def maxsim(query_vecs: np.ndarray, doc_vecs: np.ndarray) -> float:
    """Compute ColBERT MaxSim score between query and document token vectors.

    For each query token, find the maximum cosine similarity with any document
    token, then average across all query tokens.

    Args:
        query_vecs: (num_query_tokens, dim) array.
        doc_vecs: (num_doc_tokens, dim) array.

    Returns:
        MaxSim score (higher = more similar).
    """
    if query_vecs.size == 0 or doc_vecs.size == 0:
        return 0.0

    # Normalize vectors for cosine similarity
    q_norms = np.linalg.norm(query_vecs, axis=1, keepdims=True)
    d_norms = np.linalg.norm(doc_vecs, axis=1, keepdims=True)

    # Avoid division by zero
    q_norms = np.maximum(q_norms, 1e-8)
    d_norms = np.maximum(d_norms, 1e-8)

    q_normed = query_vecs / q_norms
    d_normed = doc_vecs / d_norms

    # Similarity matrix: (num_query_tokens, num_doc_tokens)
    sim_matrix = q_normed @ d_normed.T

    # MaxSim: max similarity per query token, then average
    max_sims = sim_matrix.max(axis=1)
    return float(max_sims.mean())
