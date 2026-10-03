"""Dense vector-collection queries from encoded query text."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .limits import MAX_TOP_K
from .models import SearchResult

if TYPE_CHECKING:
    from mailarium.platform.settings import Settings

    from .query_encoding import QueryEncoder


class DenseRetriever:
    """Query the text vector collection with cached query embeddings."""

    def __init__(self, collection: Any, encoder: QueryEncoder, settings: Settings) -> None:
        """Bind the text collection, the shared query encoder, and the default result limit."""
        self._collection = collection
        self._encoder = encoder
        self._settings = settings

    def search(self, query: str, top_k: int | None = None, where: dict[str, Any] | None = None) -> list[SearchResult]:
        """Run dense search within an optional metadata filter.

        Raises:
            ValueError: If ``top_k`` is non-positive or exceeds ``MAX_TOP_K``.
        """
        total = self._collection.count()
        if total == 0:
            return []

        if top_k is not None and top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if top_k is not None and top_k > MAX_TOP_K:
            raise ValueError(f"top_k must be <= {MAX_TOP_K}.")

        requested = top_k if top_k is not None else self._settings.top_k
        if requested <= 0:
            requested = 10

        return self.query_with_embedding(self._encoder.encode(query), requested, where=where)

    def query_with_embedding(
        self,
        query_embedding: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Execute a collection query from a precomputed embedding."""
        total = self._collection.count()
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

        ids, documents, metadatas, distances = _query_rows(self._collection.query(**kwargs))
        return [
            SearchResult(
                chunk_id=ids[index],
                text=documents[index],
                metadata=metadatas[index],
                distance=distances[index],
            )
            for index in range(min(len(ids), len(documents), len(metadatas), len(distances)))
        ]


def _query_rows(results: dict[str, Any]) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Normalize optional vector-store fields into parallel row sequences."""
    ids = (results.get("ids") or [[]])[0]
    if not ids:
        return [], [], [], []
    documents = (results.get("documents") or [[]])[0] or [""] * len(ids)
    metadatas = (results.get("metadatas") or [[]])[0] or [{} for _ in ids]
    distances = (results.get("distances") or [[]])[0] or [1.0] * len(ids)
    return ids, documents, metadatas, distances
