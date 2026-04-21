# ruff: noqa: F401,I001
"""Targeted coverage tests for src/retriever.py uncovered lines.

Each test targets a specific branch or code path identified by coverage analysis.
All tests run without GPU, real models, or network access.
"""

import types
from unittest.mock import MagicMock, patch

import pytest

from src.retriever import EmailRetriever, SearchResult

# ── Helpers ────────────────────────────────────────────────────────

from .helpers.retriever_cases import _bare_retriever, _make_result


class TestMergeHybrid:
    def test_merge_hybrid_no_keyword_results_returns_semantic(self):
        r = _bare_retriever()
        r._get_sparse_results = MagicMock(return_value=None)
        r._get_bm25_results = MagicMock(return_value=None)
        semantic = [_make_result("c1")]
        result = r._merge_hybrid("test", semantic, 10)
        assert result is semantic

    def test_merge_hybrid_empty_keyword_results_returns_semantic(self):
        r = _bare_retriever()
        r._get_sparse_results = MagicMock(return_value=None)
        r._get_bm25_results = MagicMock(return_value=[])
        semantic = [_make_result("c1")]
        result = r._merge_hybrid("test", semantic, 10)
        assert result is semantic

    def test_merge_hybrid_fuses_sparse_and_semantic(self):
        r = _bare_retriever()
        r._get_sparse_results = MagicMock(return_value=["c1", "c3"])
        r.collection = MagicMock()
        r.collection.get.return_value = {
            "ids": ["c3"],
            "documents": ["keyword doc"],
            "metadatas": [{"uid": "u3"}],
        }

        semantic = [
            _make_result("c1", uid="u1"),
            _make_result("c2", uid="u2"),
        ]

        # Need to make bm25_index module available
        mock_bm25 = types.ModuleType("src.bm25_index")

        def rrf(semantic_ids, keyword_ids, k=60):
            # Simple merge: keyword IDs first, then semantic
            merged = []
            seen = set()
            for cid in keyword_ids + semantic_ids:
                if cid not in seen:
                    merged.append(cid)
                    seen.add(cid)
            return merged

        mock_bm25.reciprocal_rank_fusion = rrf
        with patch.dict("sys.modules", {"src.bm25_index": mock_bm25}):
            result = r._merge_hybrid("test", semantic, 10)
            chunk_ids = [res.chunk_id for res in result]
            assert "c1" in chunk_ids
            assert "c3" in chunk_ids  # keyword-only result fetched from collection
            keyword_only = next(res for res in result if res.chunk_id == "c3")
            assert keyword_only.metadata["score_kind"] == "keyword_fused"
            assert keyword_only.metadata["score_calibration"] == "synthetic"

    def test_merge_hybrid_import_error_returns_semantic(self):
        r = _bare_retriever()
        r._get_sparse_results = MagicMock(return_value=["c99"])

        # Make the import fail
        with patch.dict("sys.modules", {"src.bm25_index": None}):
            semantic = [_make_result("c1")]
            result = r._merge_hybrid("test", semantic, 10)
            assert result is semantic

    def test_merge_hybrid_generic_exception_returns_semantic(self):
        r = _bare_retriever()
        r._get_sparse_results = MagicMock(side_effect=RuntimeError("boom"))
        semantic = [_make_result("c1")]
        result = r._merge_hybrid("test", semantic, 10)
        assert result is semantic

    def test_merge_hybrid_collection_get_failure_handled(self):
        """If collection.get fails for missing IDs, merge still works."""
        r = _bare_retriever()
        r._get_sparse_results = MagicMock(return_value=["c1", "c_missing"])
        r.collection = MagicMock()
        r.collection.get.side_effect = RuntimeError("db error")

        semantic = [_make_result("c1", uid="u1")]
        mock_bm25 = types.ModuleType("src.bm25_index")
        mock_bm25.reciprocal_rank_fusion = lambda s, k, **kw: k + [x for x in s if x not in k]
        with patch.dict("sys.modules", {"src.bm25_index": mock_bm25}):
            result = r._merge_hybrid("test", semantic, 10)
            # c1 is in semantic, c_missing failed to fetch but shouldn't crash
            assert any(res.chunk_id == "c1" for res in result)


class TestGetSparseResults:
    def test_returns_none_when_embedder_has_no_sparse(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = False
        r._embedder = mock_embedder
        assert r._get_sparse_results("test", 10) is None

    def test_returns_none_when_no_email_db(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        r._embedder = mock_embedder
        r._email_db = None
        r._email_db_checked = True
        assert r._get_sparse_results("test", 10) is None

    def test_returns_none_when_sparse_index_not_built(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        r._embedder = mock_embedder
        r._email_db = MagicMock()
        r._email_db_checked = True

        mock_sparse = MagicMock()
        mock_sparse.is_built = False
        mock_sparse.doc_count = 0

        mock_sparse_module = types.ModuleType("src.sparse_index")
        mock_sparse_module.SparseIndex = MagicMock(return_value=mock_sparse)
        with patch.dict("sys.modules", {"src.sparse_index": mock_sparse_module}):
            r._sparse_index = None
            result = r._get_sparse_results("test", 10)
            assert result is None

    def test_returns_none_when_empty_query_sparse(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        mock_embedder.encode_sparse.return_value = [{}]  # empty sparse vector
        r._embedder = mock_embedder
        r._email_db = MagicMock()
        r._email_db_checked = True

        mock_sparse = MagicMock()
        mock_sparse.is_built = True
        mock_sparse.doc_count = 100
        r._sparse_index = mock_sparse

        # Empty sparse vector should return None
        mock_embedder.encode_sparse.return_value = [{}]
        result = r._get_sparse_results("test", 10)
        assert result is None

    def test_returns_chunk_ids_on_success(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        mock_embedder.encode_sparse.return_value = [{1: 0.5, 2: 0.3}]
        r._embedder = mock_embedder
        r._email_db = MagicMock()
        r._email_db_checked = True
        r.collection = MagicMock()
        r.collection.count.return_value = 100
        r.collection.metadata = {"index_revision": "rev-1"}

        mock_sparse = MagicMock()
        mock_sparse.is_built = True
        mock_sparse.doc_count = 100
        mock_sparse.search.return_value = [("c1", 0.9), ("c2", 0.8)]
        r._sparse_index = mock_sparse

        result = r._get_sparse_results("test", 10)
        assert result == ["c1", "c2"]

    def test_returns_none_on_exception(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        mock_embedder.encode_sparse.side_effect = RuntimeError("boom")
        r._embedder = mock_embedder
        r._email_db = MagicMock()
        r._email_db_checked = True
        r.collection = MagicMock()
        r.collection.count.return_value = 10
        r.collection.metadata = {"index_revision": "rev-1"}
        r._sparse_index = MagicMock()
        r._sparse_index.is_built = True
        r._sparse_index.doc_count = 10

        result = r._get_sparse_results("test", 10)
        assert result is None

    def test_partial_sparse_coverage_still_returns_sparse_results(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        mock_embedder.encode_sparse.return_value = [{1: 0.9}]
        r._embedder = mock_embedder
        r._email_db = MagicMock()
        r._email_db_checked = True
        r.collection = MagicMock()
        r.collection.count.return_value = 100
        r.collection.metadata = {"index_revision": "rev-1"}

        mock_sparse = MagicMock()
        mock_sparse.is_built = True
        mock_sparse.doc_count = 80
        mock_sparse.search.return_value = [("c5", 0.7)]
        r._sparse_index = mock_sparse
        r._set_last_search_debug({})

        assert r._get_sparse_results("test", 10) == ["c5"]
        assert r.last_search_debug["sparse_diagnostics"]["coverage"]["status"] == "partial"

    def test_sparse_rebuilds_when_revision_changes_with_same_count(self):
        r = _bare_retriever()
        mock_embedder = MagicMock()
        mock_embedder.has_sparse = True
        mock_embedder.encode_sparse.return_value = [{1: 0.5}]
        r._embedder = mock_embedder
        r._email_db = MagicMock()
        r._email_db_checked = True
        r.collection = MagicMock()
        r.collection.count.return_value = 100
        r.collection.metadata = {"index_revision": "rev-2"}

        mock_sparse = MagicMock()
        mock_sparse.is_built = True
        mock_sparse.doc_count = 100
        mock_sparse.search.return_value = [("c1", 0.9)]
        r._sparse_index = mock_sparse
        r._sparse_build_count = (100, "rev-1")

        result = r._get_sparse_results("test", 10)
        assert result == ["c1"]
        mock_sparse.build_from_db.assert_called_once_with(r._email_db)


class TestGetBM25Results:
    def test_returns_chunk_ids_on_success(self):
        r = _bare_retriever()
        mock_bm25 = MagicMock()
        mock_bm25.is_built = True
        mock_bm25.search.return_value = [("c1", 0.5), ("c2", 0.3)]
        r._bm25_index = mock_bm25

        result = r._get_bm25_results("test", 10)
        assert result == ["c1", "c2"]

    def test_returns_none_when_not_built(self):
        r = _bare_retriever()
        mock_bm25 = MagicMock()
        mock_bm25.is_built = False
        r._bm25_index = mock_bm25

        result = r._get_bm25_results("test", 10)
        assert result is None

    def test_builds_from_collection_on_first_call(self):
        r = _bare_retriever()
        r._bm25_index = None
        r.collection = MagicMock()

        mock_bm25_instance = MagicMock()
        mock_bm25_instance.is_built = True
        mock_bm25_instance.search.return_value = [("c1", 0.5)]

        mock_bm25_module = types.ModuleType("src.bm25_index")
        mock_bm25_module.BM25Index = MagicMock(return_value=mock_bm25_instance)
        with patch.dict("sys.modules", {"src.bm25_index": mock_bm25_module}):
            result = r._get_bm25_results("test", 10)
            assert result == ["c1"]
            mock_bm25_instance.build_from_collection.assert_called_once()

    def test_returns_none_on_import_error(self):
        r = _bare_retriever()
        r._bm25_index = None
        r.collection = MagicMock()

        with patch.dict("sys.modules", {"src.bm25_index": None}):
            result = r._get_bm25_results("test", 10)
            assert result is None

    def test_returns_none_on_generic_exception(self):
        r = _bare_retriever()
        mock_bm25 = MagicMock()
        mock_bm25.is_built = True
        mock_bm25.search.side_effect = RuntimeError("boom")
        r._bm25_index = mock_bm25

        result = r._get_bm25_results("test", 10)
        assert result is None

    def test_rebuilds_when_revision_changes_with_same_count(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 50
        r.collection.metadata = {"index_revision": "rev-2"}
        mock_bm25 = MagicMock()
        mock_bm25.is_built = True
        mock_bm25.search.return_value = [("c1", 0.5)]
        mock_bm25._chunk_ids = ["c1"] * 50
        r._bm25_index = mock_bm25
        r._bm25_build_revision = (50, "rev-1")

        result = r._get_bm25_results("test", 10)
        assert result == ["c1"]
        mock_bm25.build_from_collection.assert_called_once_with(r.collection)
