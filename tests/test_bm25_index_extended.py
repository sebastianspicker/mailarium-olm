"""Extended tests for BM25Index.build_from_collection (lines 61-82)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.bm25_index import BM25Index


def _make_collection(ids: list[str], docs: list[str] | None) -> MagicMock:
    """Create a mock ChromaDB collection that returns the given data."""
    collection = MagicMock()
    collection.count.return_value = len(ids)

    def _get(limit=5000, offset=0, include=None):
        batch_ids = ids[offset : offset + limit]
        batch_docs = docs[offset : offset + limit] if docs else None
        return {"ids": batch_ids, "documents": batch_docs}

    collection.get.side_effect = _get
    return collection


class TestBuildFromCollection:
    """Cover build_from_collection (lines 61-82)."""

    def test_empty_collection(self):
        """Collection with count() == 0 should mark index as built with no docs."""
        idx = BM25Index()
        collection = MagicMock()
        collection.count.return_value = 0

        idx.build_from_collection(collection)

        assert idx.is_built
        assert idx._chunk_ids == []
        assert idx.search("anything") == []
        # get() should never be called for an empty collection
        collection.get.assert_not_called()

    def test_small_collection(self):
        """Collection smaller than batch_size fetched in one call."""
        ids = ["c1", "c2", "c3"]
        docs = [
            "the quick brown fox jumps over the lazy dog",
            "machine learning and artificial intelligence",
            "the brown fox is quick and clever",
        ]
        collection = _make_collection(ids, docs)

        idx = BM25Index()
        idx.build_from_collection(collection)

        assert idx.is_built
        assert idx._chunk_ids == ids

        results = idx.search("machine learning", top_k=5)
        result_ids = [r[0] for r in results]
        assert "c2" in result_ids

    def test_multi_batch_collection(self):
        """Collection larger than batch_size (5000) should paginate."""
        n = 5003
        ids = [f"doc-{i}" for i in range(n)]
        docs = [f"document number {i} text content" for i in range(n)]
        collection = _make_collection(ids, docs)

        idx = BM25Index()
        idx.build_from_collection(collection)

        assert idx.is_built
        assert len(idx._chunk_ids) == n
        # Should have called get() twice: batch 0..4999 and 5000..5002
        assert collection.get.call_count == 2

    def test_none_documents_uses_empty_strings_fallback(self):
        """When collection.get returns None docs, code falls back to empty strings.

        We patch build_from_documents to verify the fallback path at line 80
        passes empty strings for None document batches.
        """
        ids = ["c1", "c2"]
        collection = MagicMock()
        collection.count.return_value = 2
        collection.get.return_value = {"ids": ids, "documents": None}

        idx = BM25Index()
        # Patch build_from_documents to capture args without hitting BM25Okapi
        captured = {}

        def capture_and_delegate(chunk_ids, documents):
            captured["ids"] = chunk_ids
            captured["docs"] = documents
            # Don't call original — BM25Okapi crashes on all-empty corpora

        idx.build_from_documents = capture_and_delegate

        idx.build_from_collection(collection)

        assert captured["ids"] == ids
        assert captured["docs"] == ["", ""]

    def test_search_after_build_from_collection(self):
        """End-to-end: build from collection, then search returns ranked results."""
        ids = ["alpha", "beta", "gamma"]
        docs = [
            "the quick brown fox jumps over the lazy dog",
            "artificial intelligence and deep learning algorithms",
            "the brown fox is quick and very clever",
        ]
        collection = _make_collection(ids, docs)

        idx = BM25Index()
        idx.build_from_collection(collection)

        results = idx.search("quick brown fox", top_k=2)
        assert len(results) <= 2
        result_ids = [r[0] for r in results]
        # alpha and gamma contain the query terms
        assert "alpha" in result_ids or "gamma" in result_ids

    def test_exact_batch_boundary(self):
        """Collection with exactly batch_size items should fetch in one call."""
        n = 5000
        ids = [f"id-{i}" for i in range(n)]
        docs = [f"word{i}" for i in range(n)]
        collection = _make_collection(ids, docs)

        idx = BM25Index()
        idx.build_from_collection(collection)

        assert idx.is_built
        assert len(idx._chunk_ids) == n
        assert collection.get.call_count == 1

    def test_collection_get_missing_keys(self):
        """Collection.get returns dicts with missing keys — defaults apply."""
        collection = MagicMock()
        collection.count.return_value = 2
        # Return empty dict — ids default to [], docs default to []
        collection.get.return_value = {}

        idx = BM25Index()
        idx.build_from_collection(collection)

        # With no IDs gathered, build_from_documents is called with empty lists
        assert idx.is_built
        assert idx._chunk_ids == []
