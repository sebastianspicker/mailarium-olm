"""ColBERT MaxSim reranking using BGE-M3 token-level embeddings.

Uses the same BGE-M3 model as the primary embedder — no additional model
load required.  ColBERT scores are computed on-the-fly for top-N candidates
(typically 30-50), trading ~25MB temporary memory for high-precision reranking.

Particularly effective for:
- German compound words (token-level matching handles subwords)
- Legal evidence queries (exact phrase matching)
"""

from __future__ import annotations

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

        # Separate cached and uncached documents
        doc_vecs_by_id: dict[str, np.ndarray | None] = {}
        uncached_results: list[SearchResult] = []
        for r in results:
            if r.chunk_id in self._doc_vec_cache:
                self._doc_vec_cache.move_to_end(r.chunk_id)
                doc_vecs_by_id[r.chunk_id] = self._doc_vec_cache[r.chunk_id]
            else:
                uncached_results.append(r)

        # Encode only uncached documents
        if uncached_results:
            uncached_texts = [r.text for r in uncached_results]
            new_vecs = self._embedder.encode_colbert(uncached_texts)
            if new_vecs and len(new_vecs) == len(uncached_results):
                for r, d_vecs in zip(uncached_results, new_vecs, strict=True):
                    doc_vecs_by_id[r.chunk_id] = d_vecs
                    self._doc_vec_cache[r.chunk_id] = d_vecs
                    if len(self._doc_vec_cache) > _DOC_VEC_CACHE_MAX:
                        self._doc_vec_cache.popitem(last=False)
            elif new_vecs:
                logger.warning(
                    "ColBERT encode returned %d vectors for %d texts — skipping cache",
                    len(new_vecs),
                    len(uncached_results),
                )

        if not doc_vecs_by_id:
            return results[:top_k] if top_k else results

        scored: list[tuple[SearchResult, float]] = []
        for result in results:
            result_vecs = doc_vecs_by_id.get(result.chunk_id)
            if result_vecs is None or len(result_vecs) == 0:
                scored.append((result, 0.0))
                continue
            score = maxsim(q_vecs, result_vecs)
            scored.append((result, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        limit = top_k if top_k is not None else len(scored)

        from .retriever import SearchResult as SR

        reranked = []
        for result, score in scored[:limit]:
            # Convert score to distance (lower = more relevant)
            distance = max(0.0, 1.0 - score)
            reranked.append(
                SR(
                    chunk_id=result.chunk_id,
                    text=result.text,
                    metadata=result.metadata,
                    distance=distance,
                )
            )

        return reranked


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
