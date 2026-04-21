"""BM25 keyword index for hybrid search."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """Unicode-aware whitespace + punctuation tokenizer with lowercasing."""
    if not text:
        return []
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


class BM25Index:
    """In-memory BM25 keyword index built from a ChromaDB collection.

    Provides complementary keyword-based retrieval for hybrid search.
    The index is built lazily on first query and cached in memory.
    """

    def __init__(self) -> None:
        self._index = None
        self._chunk_ids: list[str] = []
        self._built = False

    @property
    def is_built(self) -> bool:
        return self._built

    def build_from_documents(self, chunk_ids: list[str], documents: list[str]) -> None:
        """Build the BM25 index from pre-fetched documents.

        Args:
            chunk_ids: Parallel list of chunk IDs.
            documents: Parallel list of document texts.
        """
        if not chunk_ids:
            self._chunk_ids = []
            self._built = True
            return

        from rank_bm25 import BM25Okapi

        tokenized = [_tokenize(doc) for doc in documents]
        self._index = BM25Okapi(tokenized)
        self._chunk_ids = list(chunk_ids)
        self._built = True
        logger.info("BM25 index built with %d documents", len(chunk_ids))

    def build_from_collection(self, collection: Any) -> None:
        """Build the BM25 index from a ChromaDB collection.

        Fetches all documents from the collection and tokenizes them.
        """
        total = collection.count()
        if total == 0:
            self._chunk_ids = []
            self._built = True
            return

        batch_size = 5000
        all_ids: list[str] = []
        all_docs: list[str] = []

        for offset in range(0, total, batch_size):
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents"],
            )
            ids = result.get("ids", [])
            docs = result.get("documents", [])
            all_ids.extend(ids)
            all_docs.extend([d or "" for d in docs] if docs else [""] * len(ids))

        self.build_from_documents(all_ids, all_docs)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search the BM25 index.

        Args:
            query: Text query to search for.
            top_k: Number of results to return.

        Returns:
            List of (chunk_id, bm25_score) tuples, highest score first.
        """
        if not self._built or self._index is None or not self._chunk_ids:
            return []

        if top_k <= 0:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self._index.get_scores(tokens)

        # Get top-k indices by score
        indexed_scores = [(i, float(s)) for i, s in enumerate(scores) if s > 0]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in indexed_scores[:top_k]:
            results.append((self._chunk_ids[idx], score))

        return results


def reciprocal_rank_fusion(
    semantic_ids: list[str],
    bm25_ids: list[str],
    k: int = 60,
) -> list[str]:
    """Merge two ranked lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum(1 / (k + rank)) across all lists where the item appears.
    Higher k values smooth out the contribution of lower-ranked items.

    Args:
        semantic_ids: Chunk IDs from semantic search (best first).
        bm25_ids: Chunk IDs from BM25 search (best first).
        k: RRF constant (default: 60, standard value).

    Returns:
        Merged list of chunk IDs sorted by fused score (best first).
    """
    if k < 1:
        k = 60

    scores: dict[str, float] = {}

    for rank, chunk_id in enumerate(semantic_ids):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, chunk_id in enumerate(bm25_ids):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank + 1)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_id for chunk_id, _ in fused]
