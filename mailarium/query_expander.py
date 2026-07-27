"""Embedding-based query expansion for improved recall."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)
_ASCII_FALLBACK_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})


def _append_new_terms(added: list[str], terms: list[str], query_lower: str, limit: int, *, min_length: int = 0) -> None:
    """Append distinct terms that do not merely repeat the user's query."""
    for term in terms:
        if len(added) >= limit:
            return
        if len(term) >= min_length and term not in added and not re.search(r"\b" + re.escape(term.lower()) + r"\b", query_lower):
            added.append(term)


def _distinct_lanes(lanes: list[str], max_lanes: int) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for lane in lanes:
        compact = " ".join(str(lane or "").split()).strip()
        lowered = compact.casefold()
        if compact and lowered not in seen:
            seen.add(lowered)
            normalized.append(compact)
            if len(normalized) >= max_lanes:
                break
    return normalized


class QueryExpander:
    """Expand queries with related corpus terms using the embedding model."""

    def __init__(self, model: Any = None, vocabulary: list[str] | None = None):
        """Initialize the optional embedding model and its lazy vocabulary cache."""
        self._model = model
        self._vocabulary = vocabulary or []
        self._vocab_embeddings = None

    def set_vocabulary(self, vocabulary: list[str]) -> None:
        """Set or update the keyword vocabulary."""
        self._vocabulary = vocabulary
        self._vocab_embeddings = None

    def _compute_similarities(self, query: str):
        import numpy as np

        if not self._vocabulary:
            return None
        if self._vocab_embeddings is None:
            self._vocab_embeddings = np.array(self._model.encode_dense(self._vocabulary))
        query_embedding = np.array(self._model.encode_dense([query]))
        similarities = np.dot(self._vocab_embeddings, query_embedding.T).flatten()
        return similarities, similarities.argsort()[::-1]

    def expand(self, query: str, n_terms: int = 3, *, scope: str = "general") -> str:
        """Append semantically related corpus terms to a query.

        ``scope`` remains part of the call contract for callers that carry
        scope metadata, but expansion itself stays corpus-derived.
        """
        del scope
        if not query or not query.strip() or n_terms <= 0 or not self._vocabulary or not self._model:
            return query
        try:
            query_lower = query.lower()
            added: list[str] = []
            sim_result = self._compute_similarities(query)
            if sim_result is None:
                return query
            _similarities, top_indices = sim_result
            _append_new_terms(added, [self._vocabulary[idx] for idx in top_indices], query_lower, n_terms, min_length=3)
            if not added:
                return query
            expanded = f"{query} {' '.join(added)}"
            logger.debug("Query expanded: '%s' → '%s'", query, expanded)
            return expanded
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Query expansion failed", exc_info=True)
            return query

    def expand_lanes(
        self,
        query: str,
        n_terms: int = 3,
        max_lanes: int = 4,
        *,
        scope: str = "general",
    ) -> list[str]:
        """Produce deduplicated semantic query lanes while retaining the caller's base query."""
        del scope
        base_query = " ".join(str(query or "").split()).strip()
        if not base_query:
            return []
        if max_lanes <= 1:
            return [base_query]
        lanes: list[str] = [base_query]
        ascii_lane = base_query.translate(_ASCII_FALLBACK_MAP)
        if ascii_lane != base_query:
            lanes.append(ascii_lane)
        try:
            if self._vocabulary and self._model:
                related_terms = [term for term, _score in self.get_related_terms(base_query, n_terms=max(1, n_terms * 2))]
                if related_terms:
                    lanes.append(f"{base_query} {' '.join(related_terms[:n_terms])}".strip())
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Query lane expansion failed", exc_info=True)
        return _distinct_lanes(lanes, max_lanes)

    def get_related_terms(self, query: str, n_terms: int = 5) -> list[tuple[str, float]]:
        """Get related terms and their similarity scores."""
        if not query or not self._vocabulary or not self._model or n_terms <= 0:
            return []
        try:
            sim_result = self._compute_similarities(query)
            if sim_result is None:
                return []
            similarities, top_indices = sim_result
            query_lower = query.lower()
            results: list[tuple[str, float]] = []
            for idx in top_indices:
                if len(results) >= n_terms:
                    break
                term = self._vocabulary[idx]
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", query_lower) or len(term) < 3:
                    continue
                results.append((term, round(float(similarities[idx]), 4)))
            return results
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("get_related_terms failed", exc_info=True)
            return []
