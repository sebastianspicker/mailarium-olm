"""Cross-encoder reranking for improved search precision."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .retriever import SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


class CrossEncoderReranker:
    """Re-score search results using a cross-encoder model.

    The cross-encoder jointly encodes query + document pairs, producing
    much more accurate relevance scores than bi-encoder dot products.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or _DEFAULT_MODEL
        self._model = None

    @property
    def model(self) -> Any:
        """Lazy-load cross-encoder model."""
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """Re-rank results by cross-encoder relevance score.

        Args:
            query: The original search query.
            results: Candidate results from the initial retrieval.
            top_k: Number of top results to return (default: all).

        Returns:
            Re-ranked list of SearchResult objects, sorted by descending
            cross-encoder score. The ``distance`` field is updated to
            ``1 - sigmoid(ce_score)`` so that existing score logic works.
        """
        if not results:
            return []

        pairs = [(query, r.text) for r in results]
        scores = self.model.predict(pairs)

        # Convert raw logits to 0-1 via sigmoid, then invert to distance
        import math

        scored = []
        for result, raw_score in zip(results, scores, strict=True):
            clamped = max(-500.0, min(500.0, float(raw_score)))
            sigmoid_score = 1.0 / (1.0 + math.exp(-clamped))
            distance = 1.0 - sigmoid_score
            scored.append((result, distance))

        scored.sort(key=lambda x: x[1])  # Lower distance = more relevant

        limit = top_k if top_k is not None else len(scored)
        reranked = []
        for result, distance in scored[:limit]:
            from .retriever import SearchResult

            reranked.append(
                SearchResult(
                    chunk_id=result.chunk_id,
                    text=result.text,
                    metadata=result.metadata,
                    distance=distance,
                )
            )

        return reranked
