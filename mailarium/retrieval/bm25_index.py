"""BM25 keyword index for hybrid search."""

from __future__ import annotations

import logging
import math
import re
import threading
from typing import Any

from .query_planning import _ASCII_FALLBACK_MAP

logger = logging.getLogger(__name__)

_GERMAN_COMPOUND_MAP: dict[str, tuple[str, ...]] = {
    "stufenvorweggewährung": ("stufen", "vorweg", "gewaehrung"),
    "stufenvorweggewaehrung": ("stufen", "vorweg", "gewaehrung"),
    "schwerbehindertenvertretung": ("schwerbehinderten", "vertretung", "sbv"),
    "wiedereingliederung": ("wieder", "eingliederung"),
    "leidensgerechter": ("leidens", "gerechter"),
}


def _tokenize(text: str) -> list[str]:
    """Unicode-aware whitespace + punctuation tokenizer with lowercasing."""
    if not text:
        return []
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def _morph_variants(token: str) -> list[str]:
    """Return conservative lemma/decompound variants for German retrieval."""
    lowered = str(token or "").strip().lower()
    if not lowered:
        return []
    variants: list[str] = []
    ascii_variant = lowered.translate(_ASCII_FALLBACK_MAP)
    if ascii_variant != lowered:
        variants.append(ascii_variant)

    compound_parts = _GERMAN_COMPOUND_MAP.get(lowered) or _GERMAN_COMPOUND_MAP.get(ascii_variant)
    if compound_parts:
        variants.extend(compound_parts)

    for suffix in ("ungen", "ung", "ern", "ern", "en", "er", "es", "e", "n"):
        if len(lowered) > len(suffix) + 4 and lowered.endswith(suffix):
            variants.append(lowered[: -len(suffix)])
            break
    return [item for item in variants if item and item != lowered]


def _tokenize_with_morphology(text: str) -> list[str]:
    """Tokenize and append morphology-aware sparse variants."""
    base_tokens = _tokenize(text)
    if not base_tokens:
        return []
    merged: list[str] = []
    seen: set[str] = set()
    for token in base_tokens:
        if token not in seen:
            merged.append(token)
            seen.add(token)
        for variant in _morph_variants(token):
            if variant in seen:
                continue
            merged.append(variant)
            seen.add(variant)
    return merged


class BM25Index:
    """In-memory BM25 keyword index built from a USearch vector index collection.

    Provides complementary keyword-based retrieval for hybrid search.
    The index is built lazily on first query and cached in memory.
    Rebuilds tokenize into locals and publish the snapshot in one swap under a
    lock, so concurrent searches never see an index from one corpus with ids
    from another.
    """

    def __init__(self) -> None:
        self._index = None
        self._chunk_ids: list[str] = []
        self._built = False
        self._token_path_stats: dict[str, int] = {}
        self._morph_token_sets: list[set[str]] = []
        self._lock = threading.Lock()

    @staticmethod
    def _rank_indices(
        *,
        scores: Any,
        token_sets: list[set[str]],
        query_tokens: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
        """Rank indices in the normalized form consumed by the sparse index."""
        indexed_scores = [(i, float(score)) for i, score in enumerate(scores) if float(score) > 0]
        indexed_scores.sort(key=lambda item: item[1], reverse=True)
        if indexed_scores:
            return indexed_scores[:top_k]

        query_set = {token for token in query_tokens if token}
        if not query_set or not token_sets:
            return []
        overlap_scores: list[tuple[int, float]] = []
        for i, doc_tokens in enumerate(token_sets):
            overlap = len(query_set.intersection(doc_tokens))
            if overlap <= 0:
                continue
            overlap_scores.append((i, overlap * 1e-6))
        overlap_scores.sort(key=lambda item: item[1], reverse=True)
        return overlap_scores[:top_k]

    @property
    def is_built(self) -> bool:
        """Return whether BM25 statistics have been built for the indexed corpus."""
        return self._built

    def build_from_documents(self, chunk_ids: list[str], documents: list[str]) -> None:
        """Build the BM25 index from pre-fetched documents.

        Args:
            chunk_ids: Parallel list of chunk IDs.
            documents: Parallel list of document texts.
        """
        index = None
        token_sets: list[set[str]] = []
        stats: dict[str, int] = {}
        if chunk_ids:
            from rank_bm25 import BM25Okapi

            tokenized = [_tokenize_with_morphology(doc) for doc in documents]
            index = BM25Okapi(tokenized)
            token_sets = [set(tokens) for tokens in tokenized]
            stats = {"morph_token_count": int(sum(len(tokens) for tokens in tokenized)), "doc_count": len(chunk_ids)}
        with self._lock:
            self._index = index
            self._chunk_ids = list(chunk_ids)
            self._morph_token_sets = token_sets
            self._token_path_stats = stats
            self._built = True
        logger.info("BM25 index built with %d documents", len(chunk_ids))

    def build_from_collection(self, collection: Any) -> None:
        """Build the BM25 index from a USearch vector index collection.

        Fetches all documents from the collection and tokenizes them.
        """
        total = collection.count()
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

    def _snapshot(self) -> tuple[Any, list[str], list[set[str]], dict[str, int]]:
        with self._lock:
            return self._index, self._chunk_ids, self._morph_token_sets, self._token_path_stats

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Search the BM25 index.

        Args:
            query: Text query to search for.
            top_k: Number of results to return.

        Returns:
            List of (chunk_id, bm25_score) tuples, highest score first.
        """
        rows, _diagnostics = self.search_with_diagnostics(query, top_k=top_k)
        return rows

    def search_with_diagnostics(self, query: str, top_k: int = 10) -> tuple[list[tuple[str, float]], dict[str, Any]]:
        """Search BM25 and report raw-vs-morphology diagnostics for the returned hits."""
        index, chunk_ids, token_sets, stats = self._snapshot()
        if index is None or not chunk_ids:
            return [], {"status": "empty_index"}
        if top_k <= 0:
            return [], {"status": "invalid_top_k"}

        raw_tokens = _tokenize(query)
        morph_tokens = _tokenize_with_morphology(query)
        if not morph_tokens:
            return [], {"status": "empty_query"}
        ranked = self._rank_indices(
            scores=index.get_scores(morph_tokens), token_sets=token_sets, query_tokens=morph_tokens, top_k=top_k
        )
        # Raw tokens are a subset of each document's morph tokens, so raw matches are checked on the hits only.
        raw_set = set(raw_tokens)
        raw_hit_count = sum(1 for i, _score in ranked if raw_set & token_sets[i])
        diagnostics = {
            "status": "ok",
            "raw_query_tokens": raw_tokens,
            "morph_query_tokens": morph_tokens,
            "raw_hit_count": raw_hit_count,
            "morph_hit_count": len(ranked),
            "morph_only_hit_count": len(ranked) - raw_hit_count,
            "token_path_stats": dict(stats),
        }
        return [(chunk_ids[i], score) for i, score in ranked], diagnostics


def reciprocal_rank_fusion(
    semantic_ids: list[str],
    bm25_ids: list[str],
    k: int = 60,
    *,
    semantic_weight: float = 1.0,
    keyword_weight: float = 1.0,
) -> list[str]:
    """Merge two ranked lists using weighted Reciprocal Rank Fusion (RRF).

    RRF score = sum(weight / (k + rank)) across ranked lists.
    Higher k values smooth out the contribution of lower-ranked items.

    Args:
        semantic_ids: Chunk IDs from semantic search (best first).
        bm25_ids: Chunk IDs from BM25 search (best first).
        k: RRF constant (default: 60, standard value).
        semantic_weight: Relative contribution of dense semantic ranking.
        keyword_weight: Relative contribution of sparse/BM25 ranking.

    Returns:
        Merged list of chunk IDs sorted by fused score (best first).
    """
    if k < 1:
        k = 60
    if not math.isfinite(semantic_weight) or semantic_weight < 0:
        raise ValueError("semantic_weight must be a finite non-negative number")
    if not math.isfinite(keyword_weight) or keyword_weight < 0:
        raise ValueError("keyword_weight must be a finite non-negative number")
    if semantic_weight == 0 and keyword_weight == 0:
        raise ValueError("at least one fusion weight must be positive")

    scores: dict[str, float] = {}

    for rank, chunk_id in enumerate(semantic_ids):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + semantic_weight / (k + rank + 1)

    for rank, chunk_id in enumerate(bm25_ids):
        scores[chunk_id] = scores.get(chunk_id, 0.0) + keyword_weight / (k + rank + 1)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_id for chunk_id, _ in fused]
