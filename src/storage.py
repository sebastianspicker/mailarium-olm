"""Shared ChromaDB storage helpers."""

from __future__ import annotations

import os
from collections.abc import Generator, Mapping
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

DEFAULT_PAGE_SIZE = 1000

# HNSW tuning for bulk ingestion.  batch_size delays graph construction until
# N elements are buffered, avoiding O(n) rebalancing on every .add() call.
# 100K threshold covers typical email archives (up to ~40K emails / ~100K chunks);
# the graph is built once at first query time instead of during ingestion.
# num_threads parallelises the index build across CPU cores.
HNSW_DEFAULTS: dict[str, object] = {
    "hnsw:space": "cosine",
    "hnsw:batch_size": 100_000,
    "hnsw:sync_threshold": 100_000,
    "hnsw:num_threads": os.cpu_count() or 4,
    "hnsw:M": 16,
    "hnsw:construction_ef": 128,
    "hnsw:search_ef": 128,  # match construction_ef for maximum recall at query time
}
IMMUTABLE_CHROMA_METADATA_KEYS = {"hnsw:space"}


def to_builtin_list(value: Any) -> list[list[float]]:
    """Convert tensor/ndarray-like values to Python lists when needed."""
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def get_chroma_client(chromadb_path: str) -> Any:
    """Create a persistent Chroma client at the given path."""
    os.makedirs(chromadb_path, exist_ok=True)
    return chromadb.PersistentClient(
        path=chromadb_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_collection(
    client: Any,
    collection_name: str,
    *,
    hnsw_overrides: dict[str, object] | None = None,
) -> Any:
    """Return the canonical email collection.

    ``hnsw_overrides`` can customise HNSW parameters for bulk-import vs. search
    workloads.  Build-time parameters (``M``, ``construction_ef``) are only
    applied when the collection is **created**.  Query-time parameters
    (``search_ef``) are applied to existing collections via ``modify()``.
    """
    metadata = dict(HNSW_DEFAULTS)
    if hnsw_overrides:
        metadata.update(hnsw_overrides)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata=metadata,
    )
    # search_ef is a query-time parameter that can be updated on existing
    # collections (unlike M and construction_ef which are locked at creation).
    search_ef = metadata.get("hnsw:search_ef")
    current_metadata = dict(getattr(collection, "metadata", {}) or {})
    if search_ef is not None and current_metadata.get("hnsw:search_ef") != search_ef:
        try:
            modify_collection_metadata(collection, {"hnsw:search_ef": search_ef})
        except Exception:
            import logging as _logging

            _logging.getLogger(__name__).debug(
                "Could not set search_ef=%s on collection %r (older ChromaDB?)",
                search_ef,
                collection_name,
                exc_info=True,
            )
    return collection


def modify_collection_metadata(collection: Any, updates: Mapping[str, object]) -> dict[str, object]:
    """Apply safe Chroma metadata updates without resubmitting immutable keys."""
    metadata = dict(getattr(collection, "metadata", {}) or {})
    metadata.update(dict(updates))
    for key in IMMUTABLE_CHROMA_METADATA_KEYS:
        metadata.pop(key, None)
    collection.modify(metadata=metadata)
    return metadata


def iter_collection_ids(collection, page_size: int = DEFAULT_PAGE_SIZE) -> Generator[str, None, None]:
    """Iterate all IDs in a collection using pagination."""
    yield from _iter_collection_rows(
        collection,
        include=[],
        field_name="ids",
        page_size=page_size,
    )


def iter_collection_metadatas(collection, page_size: int = DEFAULT_PAGE_SIZE) -> Generator[dict[str, Any], None, None]:
    """Iterate all metadata rows in a collection using pagination."""
    for metadata in _iter_collection_rows(
        collection,
        include=["metadatas"],
        field_name="metadatas",
        page_size=page_size,
    ):
        if metadata:
            yield metadata


def _iter_collection_rows(
    collection,
    include: list[str],
    field_name: str,
    page_size: int,
) -> Generator[Any, None, None]:
    """Internal paginated iterator for ChromaDB collection fields."""
    offset = 0
    while True:
        batch = collection.get(include=include, limit=page_size, offset=offset)
        rows = batch.get(field_name) or []
        if not rows:
            break

        yield from rows

        offset += len(rows)
