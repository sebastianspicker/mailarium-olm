"""Dense-query execution helpers for the retriever facade."""

from __future__ import annotations

import collections
from typing import Any

MAX_TOP_K = 1000
_QUERY_CACHE_MAX = 128


def encode_query_impl(retriever: Any, query: str) -> list[list[float]]:
    """Encode a query string, using a bounded cache to avoid re-encoding."""
    cache = getattr(retriever, "_query_cache", None)
    if cache is None:
        cache = retriever._query_cache = collections.OrderedDict()
    if query in cache:
        cache.move_to_end(query)
        return cache[query]
    embedding = retriever.embedder.encode_dense([query])
    cache[query] = embedding
    if len(cache) > _QUERY_CACHE_MAX:
        cache.popitem(last=False)
    return embedding


def query_with_embedding_impl(
    retriever: Any,
    query_embedding: list[list[float]],
    n_results: int,
    where: dict[str, Any] | None = None,
) -> list[Any]:
    """Execute a collection query from a precomputed embedding."""
    from .retriever_models import SearchResult

    total = retriever.collection.count()
    if total == 0:
        return []

    requested = max(1, min(n_results, total))
    kwargs: dict[str, Any] = {
        "query_embeddings": query_embedding,
        "n_results": requested,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = retriever.collection.query(**kwargs)
    ids = (results.get("ids") or [[]])[0]
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    if not ids:
        return []
    if not documents:
        documents = [""] * len(ids)
    if not metadatas:
        metadatas = [{} for _ in ids]
    if not distances:
        distances = [1.0] * len(ids)

    rows = min(len(ids), len(documents), len(metadatas), len(distances))
    return [
        SearchResult(
            chunk_id=ids[index],
            text=documents[index],
            metadata=metadatas[index],
            distance=distances[index],
        )
        for index in range(rows)
    ]


def search_impl(
    retriever: Any,
    query: str,
    top_k: int | None = None,
    where: dict[str, Any] | None = None,
) -> list[Any]:
    """Semantic search across all emails."""
    total = retriever.collection.count()
    if total == 0:
        return []

    if top_k is not None and top_k <= 0:
        raise ValueError("top_k must be a positive integer.")
    if top_k is not None and top_k > MAX_TOP_K:
        raise ValueError(f"top_k must be <= {MAX_TOP_K}.")

    requested = top_k if top_k is not None else retriever.settings.top_k
    if requested <= 0:
        requested = 10

    query_embedding = retriever._encode_query(query)
    return retriever._query_with_embedding(query_embedding, requested, where=where)
