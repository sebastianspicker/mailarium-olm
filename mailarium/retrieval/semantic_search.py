"""Validated semantic search over text and image spaces with mailbox visibility."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .limits import FILTER_OVERFETCH, MAX_FETCH_SIZE, MAX_TOP_K

if TYPE_CHECKING:
    from mailarium.platform.settings import Settings

    from .dense import DenseRetriever
    from .image_search import ImageSearch
    from .models import SearchResult
    from .query_encoding import QueryEncoder
    from .visibility import ResultVisibility

_MAX_FETCH_ATTEMPTS = 13


class SemanticSearch:
    """Fill a requested result count from dense and image candidates that remain visible."""

    def __init__(
        self,
        *,
        dense: DenseRetriever,
        encoder: QueryEncoder,
        image_search: ImageSearch,
        visibility: ResultVisibility,
        settings: Settings,
    ) -> None:
        """Compose the candidate sources and the visibility policy used by every batch."""
        self._dense = dense
        self._encoder = encoder
        self._image_search = image_search
        self._visibility = visibility
        self._settings = settings

    def search(self, query: str, top_k: int | None = None, where: dict[str, Any] | None = None) -> list[SearchResult]:
        """Run filtered semantic search and merge eligible image results.

        Raises:
            ValueError: If ``top_k`` is non-positive or exceeds the supported
                retrieval limit.
        """
        requested = self._requested_limit(top_k)
        fetch_size = self._initial_fetch_size(requested)
        query_embedding: list[list[float]] | None = None
        for _ in range(_MAX_FETCH_ATTEMPTS):
            results, query_embedding = self._text_batch(query, fetch_size, where, query_embedding)
            merged = self._image_search.merge(query, results, fetch_size, where=where)
            active = self._visibility.visible(merged)
            if _is_complete(active, merged, requested, fetch_size):
                return active[:requested]
            fetch_size = min(MAX_FETCH_SIZE, fetch_size * 2)
        return active[:requested]

    def _requested_limit(self, top_k: int | None) -> int:
        """Validate and resolve the public semantic-search result limit."""
        if top_k is not None and top_k <= 0:
            raise ValueError("top_k must be a positive integer.")
        if top_k is not None and top_k > MAX_TOP_K:
            raise ValueError(f"top_k must be <= {MAX_TOP_K}.")
        requested = top_k if top_k is not None else self._settings.top_k
        return requested if requested > 0 else 10

    def _initial_fetch_size(self, requested: int) -> int:
        """Overfetch only when mailbox tombstones may hide retrieved rows."""
        if not self._visibility.may_hide_results():
            return requested
        return min(MAX_FETCH_SIZE, max(requested, requested * FILTER_OVERFETCH))

    def _text_batch(
        self,
        query: str,
        fetch_size: int,
        where: dict[str, Any] | None,
        query_embedding: list[list[float]] | None,
    ) -> tuple[list[SearchResult], list[list[float]] | None]:
        """Fetch one text-search batch, reusing an embedding above the public limit."""
        if fetch_size <= MAX_TOP_K:
            return self._dense.search(query, top_k=fetch_size, where=where), query_embedding
        if query_embedding is None:
            query_embedding = self._encoder.encode(query)
        return self._dense.query_with_embedding(query_embedding, fetch_size, where=where), query_embedding


def _is_complete(active: list[SearchResult], merged: list[SearchResult], requested: int, fetch_size: int) -> bool:
    """Stop when the requested rows are filled or no larger batch can help."""
    return len(active) >= requested or len(merged) < fetch_size or fetch_size >= MAX_FETCH_SIZE
