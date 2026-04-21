"""Tests for src/storage.py — shared ChromaDB storage helpers."""

from __future__ import annotations

import numpy as np

from src.storage import (
    _iter_collection_rows,
    get_chroma_client,
    get_collection,
    iter_collection_ids,
    iter_collection_metadatas,
    to_builtin_list,
)

# ── to_builtin_list ─────────────────────────────────────────────────


def test_to_builtin_list_converts_numpy_array():
    arr = np.array([1, 2, 3])
    result = to_builtin_list(arr)
    assert result == [1, 2, 3]
    assert isinstance(result, list)


def test_to_builtin_list_converts_nested_numpy():
    arr = np.array([[0.1, 0.2], [0.3, 0.4]])
    result = to_builtin_list(arr)
    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert isinstance(result, list)
    assert isinstance(result[0], list)


def test_to_builtin_list_plain_list_unchanged():
    original = [1, 2, 3]
    result = to_builtin_list(original)
    assert result is original  # same object reference


def test_to_builtin_list_empty_list():
    assert to_builtin_list([]) == []


def test_to_builtin_list_non_iterable():
    assert to_builtin_list(42) == 42
    assert to_builtin_list("hello") == "hello"
    assert to_builtin_list(None) is None


# ── get_chroma_client ────────────────────────────────────────────────


def test_get_chroma_client_creates_directory(tmp_path):
    db_path = str(tmp_path / "new_subdir" / "chromadb")
    client = get_chroma_client(db_path)
    assert (tmp_path / "new_subdir" / "chromadb").is_dir()
    # The client stub just needs to be truthy
    assert client is not None


def test_get_chroma_client_returns_client(tmp_path):
    client = get_chroma_client(str(tmp_path / "db"))
    # Should have get_or_create_collection method
    assert hasattr(client, "get_or_create_collection")


# ── get_collection ───────────────────────────────────────────────────


def test_get_collection_creates_collection(tmp_path):
    client = get_chroma_client(str(tmp_path / "db"))
    collection = get_collection(client, "test_emails")
    assert collection is not None
    assert collection.count() == 0


def test_get_collection_idempotent(tmp_path):
    client = get_chroma_client(str(tmp_path / "db"))
    coll1 = get_collection(client, "test_emails")
    coll2 = get_collection(client, "test_emails")
    # Both calls return the same collection
    assert coll1 is coll2


def test_get_collection_applies_search_ef(tmp_path):
    """search_ef should be propagated to existing collections via modify()."""
    client = get_chroma_client(str(tmp_path / "db"))
    collection = get_collection(client, "test_emails")
    metadata = collection.metadata or {}
    assert metadata.get("hnsw:search_ef") == 128


# ── iter_collection_ids ──────────────────────────────────────────────


class _FakeCollection:
    """Minimal collection fake for testing pagination."""

    def __init__(self, items: list[dict]):
        self._items = items

    def get(self, include=None, limit=None, offset=0):
        include = include or []
        limit = len(self._items) if limit is None else limit
        batch = self._items[offset : offset + limit]
        out = {"ids": [item["id"] for item in batch]}
        if "metadatas" in include:
            out["metadatas"] = [item.get("metadata") for item in batch]
        return out

    def count(self):
        return len(self._items)


def test_iter_collection_ids_empty():
    coll = _FakeCollection([])
    assert list(iter_collection_ids(coll)) == []


def test_iter_collection_ids_populated():
    items = [{"id": f"id_{i}"} for i in range(5)]
    coll = _FakeCollection(items)
    ids = list(iter_collection_ids(coll))
    assert ids == [f"id_{i}" for i in range(5)]


# ── iter_collection_metadatas ────────────────────────────────────────


def test_iter_collection_metadatas_empty():
    coll = _FakeCollection([])
    assert list(iter_collection_metadatas(coll)) == []


def test_iter_collection_metadatas_populated():
    items = [
        {"id": "a", "metadata": {"sender": "alice"}},
        {"id": "b", "metadata": {"sender": "bob"}},
    ]
    coll = _FakeCollection(items)
    metadatas = list(iter_collection_metadatas(coll))
    assert len(metadatas) == 2
    assert metadatas[0] == {"sender": "alice"}
    assert metadatas[1] == {"sender": "bob"}


def test_iter_collection_metadatas_skips_none():
    """None metadata values should be filtered out."""
    items = [
        {"id": "a", "metadata": {"sender": "alice"}},
        {"id": "b", "metadata": None},
        {"id": "c", "metadata": {"sender": "carol"}},
    ]
    coll = _FakeCollection(items)
    metadatas = list(iter_collection_metadatas(coll))
    assert len(metadatas) == 2
    assert metadatas[0] == {"sender": "alice"}
    assert metadatas[1] == {"sender": "carol"}


# ── _iter_collection_rows pagination ─────────────────────────────────


def test_iter_collection_rows_pagination():
    """Pagination with page_size=2 across 5 items."""
    items = [{"id": f"id_{i}"} for i in range(5)]
    coll = _FakeCollection(items)
    ids = list(_iter_collection_rows(coll, include=[], field_name="ids", page_size=2))
    assert ids == [f"id_{i}" for i in range(5)]


def test_iter_collection_rows_exact_page_boundary():
    """Items exactly fill pages (4 items, page_size=2)."""
    items = [{"id": f"id_{i}"} for i in range(4)]
    coll = _FakeCollection(items)
    ids = list(_iter_collection_rows(coll, include=[], field_name="ids", page_size=2))
    assert ids == [f"id_{i}" for i in range(4)]


def test_iter_collection_rows_single_page():
    """All items fit in one page."""
    items = [{"id": f"id_{i}"} for i in range(3)]
    coll = _FakeCollection(items)
    ids = list(_iter_collection_rows(coll, include=[], field_name="ids", page_size=100))
    assert ids == [f"id_{i}" for i in range(3)]
