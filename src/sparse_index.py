"""In-memory inverted index for BGE-M3 learned sparse vectors.

Replaces BM25 with higher-quality sparse retrieval from the same BGE-M3
model that produces dense embeddings — one model, two retrieval modes.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .email_db import EmailDatabase

logger = logging.getLogger(__name__)


class SparseIndex:
    """In-memory inverted index built from SQLite-stored sparse vectors.

    Designed for < 100k chunks (~50 MB memory).  Supports dot-product
    scoring against query sparse vectors from BGE-M3.

    Thread-safe: concurrent MCP calls may trigger searches while a rebuild
    is in progress.  A read-write lock ensures that ``build_from_*`` swaps
    the index atomically and searches never see a half-built index.
    """

    def __init__(self) -> None:
        self._inverted: dict[int, list[tuple[str, float]]] = {}
        self._doc_norms: dict[str, float] = {}
        self._built = False
        self._doc_count = 0
        self._lock = threading.Lock()

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def doc_count(self) -> int:
        return self._doc_count

    def build_from_db(self, db: EmailDatabase) -> None:
        """Build the inverted index from all sparse vectors in SQLite."""
        # Stream directly from SQLite to avoid materializing the sparse corpus
        # and the inverted index in memory at the same time.
        self.build_from_iterable(db.iter_sparse_vectors())

    def build_from_vectors(self, vectors: dict[str, dict[int, float]]) -> None:
        """Build the inverted index from a dict of {chunk_id: {token_id: weight}}.

        Args:
            vectors: Mapping from chunk ID to sparse vector.
        """
        # Build into temporaries, then swap atomically under the lock so
        # concurrent searches never see a half-built index.
        new_inverted: dict[int, list[tuple[str, float]]] = {}
        new_norms: dict[str, float] = {}

        for chunk_id, sv in vectors.items():
            norm = 0.0
            for token_id, weight in sv.items():
                if weight <= 0:
                    continue
                new_inverted.setdefault(token_id, []).append((chunk_id, weight))
                norm += weight * weight
            new_norms[chunk_id] = math.sqrt(norm) if norm > 0 else 0.0

        with self._lock:
            self._inverted = new_inverted
            self._doc_norms = new_norms
            self._doc_count = len(vectors)
            self._built = True

        logger.info(
            "Sparse index built: %d documents, %d unique tokens",
            self._doc_count,
            len(new_inverted),
        )

    def build_from_iterable(self, vectors) -> None:
        """Build the inverted index from an iterable of sparse vectors."""
        new_inverted: dict[int, list[tuple[str, float]]] = {}
        new_norms: dict[str, float] = {}
        doc_count = 0

        for chunk_id, sv in vectors:
            doc_count += 1
            norm = 0.0
            for token_id, weight in sv.items():
                if weight <= 0:
                    continue
                new_inverted.setdefault(token_id, []).append((chunk_id, weight))
                norm += weight * weight
            new_norms[chunk_id] = math.sqrt(norm) if norm > 0 else 0.0

        with self._lock:
            self._inverted = new_inverted
            self._doc_norms = new_norms
            self._doc_count = doc_count
            self._built = True

        logger.info(
            "Sparse index built: %d documents, %d unique tokens",
            self._doc_count,
            len(new_inverted),
        )

    def search(
        self,
        query_sparse: dict[int, float],
        top_k: int = 10,
        normalize: bool = False,
    ) -> list[tuple[str, float]]:
        """Search using dot-product scoring against query sparse vector.

        Args:
            query_sparse: Query sparse vector {token_id: weight}.
            top_k: Number of results to return.
            normalize: If True, divide each document score by its L2 norm
                to reduce bias toward longer documents. Default False
                because BGE-M3 learned sparse vectors are designed for
                raw dot-product scoring.

        Returns:
            List of (chunk_id, score) tuples, highest score first.
        """
        if not self._built or not query_sparse or top_k <= 0:
            return []

        # Snapshot references under the lock — the actual scoring runs
        # lock-free since the data structures are swapped atomically
        # during build and never mutated in-place.
        with self._lock:
            inverted = self._inverted
            doc_norms = self._doc_norms

        scores: dict[str, float] = {}

        for token_id, q_weight in query_sparse.items():
            if q_weight <= 0:
                continue
            postings = inverted.get(token_id)
            if not postings:
                continue
            for chunk_id, d_weight in postings:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + q_weight * d_weight

        if not scores:
            return []

        if normalize:
            for chunk_id in scores:
                norm = doc_norms.get(chunk_id, 0.0)
                if norm > 0:
                    scores[chunk_id] /= norm

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]
