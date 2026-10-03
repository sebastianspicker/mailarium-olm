"""Lazy text-embedder ownership and cached dense query encoding."""

from __future__ import annotations

import collections
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mailarium.platform.settings import Settings

    from .multi_vector_embedder import MultiVectorEmbedder

_QUERY_CACHE_MAX = 128


class QueryEncoder:
    """Own the lazily loaded text embedder and a bounded cache of dense query vectors."""

    def __init__(self, settings: Settings) -> None:
        """Record embedder settings without loading a model."""
        self._settings = settings
        self._embedder: MultiVectorEmbedder | None = None
        # Bounded LRU cache - evicts the oldest entry when len > _QUERY_CACHE_MAX.
        self._query_cache: collections.OrderedDict[str, list[list[float]]] = collections.OrderedDict()

    @property
    def embedder(self) -> MultiVectorEmbedder:
        """Return the multi-vector embedder, constructing it on first use."""
        if self._embedder is None:
            from .multi_vector_embedder import MultiVectorEmbedder

            settings = self._settings
            self._embedder = MultiVectorEmbedder(
                model_name=settings.embedding_model,
                device=settings.device,
                sparse_enabled=settings.sparse_enabled,
                sparse_model=settings.sparse_model,
                sparse_model_revision=settings.sparse_model_revision,
                batch_size=settings.embedding_batch_size,
                load_mode=settings.embedding_load_mode,
                model_revision=settings.embedding_model_revision,
            )
        return self._embedder

    @embedder.setter
    def embedder(self, embedder: MultiVectorEmbedder) -> None:
        """Use a caller-supplied encoder, such as a local deterministic test encoder."""
        self._embedder = embedder

    def encode(self, query: str) -> list[list[float]]:
        """Encode a query string, using a bounded cache to avoid re-encoding."""
        cache = self._query_cache
        if query in cache:
            cache.move_to_end(query)
            return cache[query]
        embedding = self.embedder.encode_dense([query])
        cache[query] = embedding
        if len(cache) > _QUERY_CACHE_MAX:
            cache.popitem(last=False)
        return embedding

    def release(self) -> list[Any]:
        """Drop the loaded embedder and return it for closing."""
        embedder, self._embedder = self._embedder, None
        return [embedder]
