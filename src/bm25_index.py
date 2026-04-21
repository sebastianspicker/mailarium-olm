"""BM25 keyword index for hybrid search."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_ASCII_FALLBACK_MAP = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
    }
)

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
    """In-memory BM25 keyword index built from a ChromaDB collection.

    Provides complementary keyword-based retrieval for hybrid search.
    The index is built lazily on first query and cached in memory.
    """

    def __init__(self) -> None:
        self._index = None
        self._raw_index = None
        self._chunk_ids: list[str] = []
        self._built = False
        self._token_path_stats: dict[str, int] = {}
        self._raw_token_sets: list[set[str]] = []
        self._morph_token_sets: list[set[str]] = []

    @staticmethod
    def _rank_indices(
        *,
        scores: Any,
        token_sets: list[set[str]],
        query_tokens: list[str],
        top_k: int,
    ) -> list[tuple[int, float]]:
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
        return self._built

    def build_from_documents(self, chunk_ids: list[str], documents: list[str]) -> None:
        """Build the BM25 index from pre-fetched documents.

        Args:
            chunk_ids: Parallel list of chunk IDs.
            documents: Parallel list of document texts.
        """
        if not chunk_ids:
            self._index = None
            self._raw_index = None
            self._chunk_ids = []
            self._token_path_stats = {}
            self._raw_token_sets = []
            self._morph_token_sets = []
            self._built = True
            return

        from rank_bm25 import BM25Okapi

        tokenized_raw = [_tokenize(doc) for doc in documents]
        tokenized_morph = [_tokenize_with_morphology(doc) for doc in documents]
        self._raw_index = BM25Okapi(tokenized_raw)
        self._index = BM25Okapi(tokenized_morph)
        self._raw_token_sets = [set(tokens) for tokens in tokenized_raw]
        self._morph_token_sets = [set(tokens) for tokens in tokenized_morph]
        self._chunk_ids = list(chunk_ids)
        self._built = True
        self._token_path_stats = {
            "raw_token_count": int(sum(len(tokens) for tokens in tokenized_raw)),
            "morph_token_count": int(sum(len(tokens) for tokens in tokenized_morph)),
            "doc_count": len(chunk_ids),
        }
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

        tokens = _tokenize_with_morphology(query)
        if not tokens:
            return []

        scores = self._index.get_scores(tokens)
        ranked_scores = self._rank_indices(
            scores=scores,
            token_sets=self._morph_token_sets,
            query_tokens=tokens,
            top_k=top_k,
        )

        results = []
        for idx, score in ranked_scores:
            results.append((self._chunk_ids[idx], score))

        return results

    def search_with_diagnostics(self, query: str, top_k: int = 10) -> tuple[list[tuple[str, float]], dict[str, Any]]:
        """Search BM25 and report raw-vs-morphology retrieval diagnostics."""
        if not self._built or self._index is None or self._raw_index is None or not self._chunk_ids:
            return [], {"status": "empty_index"}
        if top_k <= 0:
            return [], {"status": "invalid_top_k"}

        raw_tokens = _tokenize(query)
        morph_tokens = _tokenize_with_morphology(query)
        if not morph_tokens:
            return [], {"status": "empty_query"}

        raw_scores = self._raw_index.get_scores(raw_tokens) if raw_tokens else []
        morph_scores = self._index.get_scores(morph_tokens)

        raw_ranked = self._rank_indices(
            scores=raw_scores,
            token_sets=self._raw_token_sets,
            query_tokens=raw_tokens,
            top_k=top_k,
        )
        morph_ranked = self._rank_indices(
            scores=morph_scores,
            token_sets=self._morph_token_sets,
            query_tokens=morph_tokens,
            top_k=top_k,
        )

        raw_ids = [self._chunk_ids[index] for index, _score in raw_ranked]
        morph_ids = [self._chunk_ids[index] for index, _score in morph_ranked]
        rows = [(self._chunk_ids[index], score) for index, score in morph_ranked]
        diagnostics = {
            "status": "ok",
            "raw_query_tokens": raw_tokens,
            "morph_query_tokens": morph_tokens,
            "raw_hit_count": len(raw_ids),
            "morph_hit_count": len(morph_ids),
            "morph_only_hit_count": len([chunk_id for chunk_id in morph_ids if chunk_id not in set(raw_ids)]),
            "token_path_stats": dict(self._token_path_stats),
        }
        return rows, diagnostics


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
