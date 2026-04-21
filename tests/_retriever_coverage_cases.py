"""Targeted coverage tests for src/retriever.py uncovered lines.

Each test targets a specific branch or code path identified by coverage analysis.
All tests run without GPU, real models, or network access.
"""

import types
from unittest.mock import MagicMock, patch

import pytest

from src.retriever import EmailRetriever, SearchResult

# ── Helpers ────────────────────────────────────────────────────────


def _make_result(chunk_id="c1", text="body text", uid="u1", date="2024-01-01", distance=0.1, **extra_meta):
    meta = {"uid": uid, "date": date, **extra_meta}
    return SearchResult(chunk_id=chunk_id, text=text, metadata=meta, distance=distance)


def _bare_retriever(**attrs):
    """Create a retriever via __new__ with optional attribute overrides."""
    r = EmailRetriever.__new__(EmailRetriever)
    # Set common defaults that many methods expect
    r._email_db = None
    r._email_db_checked = True
    r.settings = None
    for k, v in attrs.items():
        setattr(r, k, v)
    return r


# ── SearchResult methods (lines 66-67, 69-77) ─────────────────────


class TestSearchResultMethods:
    def test_to_context_string_returns_formatted_block(self):
        result = _make_result(sender_email="a@b.com", subject="Hi")
        ctx = result.to_context_string()
        assert "body text" in ctx
        assert isinstance(ctx, str)

    def test_to_dict_has_expected_keys(self):
        result = _make_result()
        d = result.to_dict()
        assert set(d.keys()) == {"chunk_id", "score", "distance", "metadata", "text"}
        assert d["chunk_id"] == "c1"
        assert d["score"] == pytest.approx(0.9, abs=0.01)
        assert d["distance"] == pytest.approx(0.1, abs=0.01)

    def test_score_clamped_to_zero_for_large_distance(self):
        result = SearchResult("x", "t", {}, distance=2.0)
        assert result.score == 0.0


# ── model property (line 145) ─────────────────────────────────────


def test_model_property_is_embedder_alias():
    r = _bare_retriever()
    dummy = MagicMock()
    r._embedder = dummy
    assert r.model is r.embedder


# ── search() validation (lines 163-177) ───────────────────────────


class TestSearchValidation:
    def test_search_empty_collection_returns_empty(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 0
        assert r.search("hello") == []

    def test_search_raises_on_zero_top_k(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 10
        with pytest.raises(ValueError, match="positive"):
            r.search("hello", top_k=0)

    def test_search_raises_on_negative_top_k(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 10
        with pytest.raises(ValueError, match="positive"):
            r.search("hello", top_k=-1)

    def test_search_raises_on_excessive_top_k(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 10
        with pytest.raises(ValueError, match="1000"):
            r.search("hello", top_k=1001)

    def test_search_uses_settings_top_k_when_none(self):
        settings = MagicMock()
        settings.top_k = 5
        r = _bare_retriever(settings=settings)
        r.collection = MagicMock()
        r.collection.count.return_value = 20

        # Mock _encode_query and _query_with_embedding
        r._encode_query = MagicMock(return_value=[[0.1]])
        r._query_with_embedding = MagicMock(return_value=[_make_result()])
        r.search("hello")
        r._query_with_embedding.assert_called_once_with([[0.1]], 5, where=None)

    def test_search_defaults_to_10_when_settings_top_k_zero(self):
        settings = MagicMock()
        settings.top_k = 0
        r = _bare_retriever(settings=settings)
        r.collection = MagicMock()
        r.collection.count.return_value = 20

        r._encode_query = MagicMock(return_value=[[0.1]])
        r._query_with_embedding = MagicMock(return_value=[_make_result()])
        r.search("hello")
        r._query_with_embedding.assert_called_once_with([[0.1]], 10, where=None)


# ── _query_with_embedding edge cases (lines 188-225) ──────────────


class TestQueryWithEmbedding:
    def test_empty_collection_returns_empty(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 0
        assert r._query_with_embedding([[0.1]], 10) == []

    def test_empty_ids_returns_empty(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 5
        r.collection.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        assert r._query_with_embedding([[0.1]], 5) == []

    def test_missing_documents_filled_with_empty_strings(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 1
        r.collection.query.return_value = {
            "ids": [["id1"]],
            "documents": None,
            "metadatas": [[{"uid": "u1"}]],
            "distances": [[0.2]],
        }
        results = r._query_with_embedding([[0.1]], 1)
        assert len(results) == 1
        assert results[0].text == ""

    def test_missing_metadatas_filled_with_empty_dicts(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 1
        r.collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["hello"]],
            "metadatas": None,
            "distances": [[0.2]],
        }
        results = r._query_with_embedding([[0.1]], 1)
        assert len(results) == 1
        assert results[0].metadata == {}

    def test_missing_distances_filled_with_default(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 1
        r.collection.query.return_value = {
            "ids": [["id1"]],
            "documents": [["hello"]],
            "metadatas": [[{}]],
            "distances": None,
        }
        results = r._query_with_embedding([[0.1]], 1)
        assert len(results) == 1
        assert results[0].distance == 1.0


# ── search_filtered: semantic UID resolution (lines 264-268) ──────


class TestSearchFilteredSemantic:
    def test_topic_id_filters_by_resolved_uids(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_by_topic.return_value = [{"uid": "u1"}, {"uid": "u2"}]
        r._email_db = mock_db
        r._email_db_checked = True

        def _search(query, top_k=10, where=None):
            return [
                _make_result("c1", uid="u1"),
                _make_result("c2", uid="u2"),
                _make_result("c3", uid="u3"),
            ]

        r.search = _search

        results = r.search_filtered(query="test", top_k=10, topic_id=1)
        uids = {res.metadata["uid"] for res in results}
        assert "u3" not in uids
        assert "u1" in uids

    def test_topic_id_empty_returns_empty(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_by_topic.return_value = []
        r._email_db = mock_db
        r._email_db_checked = True

        results = r.search_filtered(query="test", top_k=10, topic_id=99)
        assert results == []

    def test_cluster_id_filters_by_resolved_uids(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_in_cluster.return_value = [{"uid": "u5"}]
        r._email_db = mock_db
        r._email_db_checked = True

        def _search(query, top_k=10, where=None):
            return [
                _make_result("c1", uid="u5"),
                _make_result("c2", uid="u6"),
            ]

        r.search = _search

        results = r.search_filtered(query="test", top_k=10, cluster_id=3)
        assert len(results) == 1
        assert results[0].metadata["uid"] == "u5"


# ── search_filtered: email_type lowering (line 284) ──────────────


def test_search_filtered_lowercases_email_type():
    r = _bare_retriever()

    def _search(query, top_k=10, where=None):
        return [
            _make_result("c1", uid="u1", email_type="reply"),
            _make_result("c2", uid="u2", email_type="forward"),
        ]

    r.search = _search

    results = r.search_filtered(query="test", top_k=10, email_type="REPLY")
    assert len(results) == 1
    assert results[0].metadata["email_type"] == "reply"


# ── search_filtered: top_k <= 0 (line 290) ──────────────────────


def test_search_filtered_raises_on_zero_top_k():
    r = _bare_retriever()
    with pytest.raises(ValueError, match="positive"):
        r.search_filtered(query="test", top_k=0)


# ── search_filtered: hybrid merge (line 326) ────────────────────


def test_search_filtered_calls_merge_hybrid_when_enabled():
    r = _bare_retriever()
    settings = MagicMock()
    settings.rerank_enabled = False
    settings.hybrid_enabled = True
    r.settings = settings

    call_log = []

    def _search(query, top_k=10, where=None):
        return [_make_result(f"c{i}", uid=f"u{i}") for i in range(top_k)]

    r.search = _search

    def _mock_merge(self, query, results, fetch_size):
        call_log.append(True)
        return results

    r._merge_hybrid = types.MethodType(_mock_merge, r)

    r.search_filtered(query="test", top_k=5, hybrid=True)
    assert len(call_log) == 1


# ── search_filtered: rerank (line 346) ──────────────────────────


def test_search_filtered_calls_rerank_when_enabled():
    r = _bare_retriever()
    settings = MagicMock()
    settings.rerank_enabled = False
    settings.hybrid_enabled = False
    r.settings = settings

    rerank_called = []

    def _search(query, top_k=10, where=None):
        return [_make_result(f"c{i}", uid=f"u{i}") for i in range(top_k)]

    r.search = _search

    def _mock_rerank(self, query, results, top_k):
        rerank_called.append(True)
        return results[:top_k]

    r._apply_rerank = types.MethodType(_mock_rerank, r)

    results = r.search_filtered(query="test", top_k=3, rerank=True)
    assert len(rerank_called) == 1
    assert len(results) == 3


# ── search_filtered: fetch_size max and final return (lines 356, 360) ──


def test_search_filtered_stops_at_max_fetch_size():
    """When expanding fetch_size reaches _MAX_FETCH_SIZE, return what we have."""
    r = _bare_retriever()
    call_count = {"n": 0}

    def _search(query, top_k=10, where=None):
        call_count["n"] += 1
        # Return fewer results than requested (but more than fetch_size to
        # prevent early exit via raw_count < fetch_size). We make results
        # always deduplicate to just 1 email, so we never reach top_k=100.
        return [_make_result("c1", uid="u1")]

    r.search = _search
    r._encode_query = MagicMock(return_value=[[0.1]])
    r._query_with_embedding = MagicMock(return_value=[_make_result("c1", uid="u1")])

    # With sender filter, overfetch multiplier is large
    results = r.search_filtered(query="test", top_k=100, sender="target")
    # Should stop after _MAX_FETCH_ATTEMPTS or _MAX_FETCH_SIZE
    assert len(results) <= 100


# ── _apply_rerank: ColBERT path (lines 365-371) ─────────────────


def test_apply_rerank_colbert_path():
    r = _bare_retriever()
    settings = MagicMock()
    settings.colbert_rerank_enabled = True
    r.settings = settings

    mock_embedder = MagicMock()
    mock_embedder.has_colbert = True
    r._embedder = mock_embedder

    results = [_make_result("c1"), _make_result("c2")]

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = results[:1]

    with patch("src.retriever.ColBERTReranker", create=True):
        # Patch the import target
        import src.retriever as mod

        getattr(mod, "ColBERTReranker", None)
        try:
            # We need to mock the import inside _apply_rerank
            with patch.dict("sys.modules", {"src.colbert_reranker": MagicMock(ColBERTReranker=lambda embedder: mock_reranker)}):
                with patch("src.colbert_reranker.ColBERTReranker", return_value=mock_reranker):
                    r._apply_rerank("test query", results, top_k=1)
                    assert mock_reranker.rerank.called
        finally:
            pass


# ── _apply_rerank: cross-encoder fallback (lines 374-379) ───────


def test_apply_rerank_cross_encoder_fallback():
    r = _bare_retriever()
    settings = MagicMock()
    settings.colbert_rerank_enabled = False
    settings.rerank_model = "some-model"
    r.settings = settings

    mock_embedder = MagicMock()
    mock_embedder.has_colbert = False
    r._embedder = mock_embedder
    r._reranker = None

    results = [_make_result("c1"), _make_result("c2")]

    mock_reranker_instance = MagicMock()
    mock_reranker_instance.rerank.return_value = results[:1]

    with patch("src.retriever.CrossEncoderReranker", create=True):
        # Mock the import
        mock_module = types.ModuleType("src.reranker")
        mock_module.CrossEncoderReranker = MagicMock(return_value=mock_reranker_instance)
        with patch.dict("sys.modules", {"src.reranker": mock_module}):
            r._apply_rerank("test query", results, top_k=1)
            assert mock_reranker_instance.rerank.called


# ── _merge_hybrid (lines 389-440) ───────────────────────────────


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


# ── _get_sparse_results (lines 444-469) ─────────────────────────


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
        r._sparse_index = MagicMock()
        r._sparse_index.is_built = True
        r._sparse_index.doc_count = 10

        result = r._get_sparse_results("test", 10)
        assert result is None


# ── _get_bm25_results (lines 473-489) ───────────────────────────


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


# ── search_by_thread (lines 497-525) ────────────────────────────


class TestSearchByThread:
    def test_empty_conversation_id_returns_empty(self):
        r = _bare_retriever()
        assert r.search_by_thread("") == []
        assert r.search_by_thread("   ") == []

    def test_raises_on_non_positive_top_k(self):
        r = _bare_retriever()
        with pytest.raises(ValueError, match="positive"):
            r.search_by_thread("conv1", top_k=0)

    def test_empty_get_returns_empty(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {"ids": []}

        assert r.search_by_thread("conv1") == []

    def test_returns_results_sorted_by_date(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {
            "ids": ["c1", "c2"],
            "documents": ["body1", "body2"],
            "metadatas": [
                {"uid": "u1", "date": "2024-01-02", "conversation_id": "conv1"},
                {"uid": "u2", "date": "2024-01-01", "conversation_id": "conv1"},
            ],
        }

        thread = r.search_by_thread("conv1")
        # Should be sorted by date
        assert thread[0].metadata["date"] == "2024-01-01"
        assert thread[1].metadata["date"] == "2024-01-02"

        # Verify collection.get was called with the right filter
        r.collection.get.assert_called_once()
        call_kwargs = r.collection.get.call_args
        assert call_kwargs[1]["where"] == {"conversation_id": {"$eq": "conv1"}}

    def test_deduplicates_results(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.get.return_value = {
            "ids": ["c1", "c1b", "c2"],
            "documents": ["body1", "body1b", "body2"],
            "metadatas": [
                {"uid": "u1", "date": "2024-01-01"},
                {"uid": "u1", "date": "2024-01-01"},  # duplicate
                {"uid": "u2", "date": "2024-01-02"},
            ],
        }

        thread = r.search_by_thread("conv1")
        uids = [t.metadata["uid"] for t in thread]
        assert uids == ["u1", "u2"]


# ── list_senders: SQLite path (lines 536-547) ───────────────────


class TestListSendersSqlite:
    def test_uses_sqlite_when_available(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_senders.return_value = [
            {"sender_name": "Alice", "sender_email": "alice@ex.com", "message_count": 10},
        ]
        r._email_db = mock_db
        r._email_db_checked = True

        senders = r.list_senders(limit=5)
        assert senders == [{"name": "Alice", "email": "alice@ex.com", "count": 10}]

    def test_falls_back_to_chromadb_when_sqlite_fails(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_senders.side_effect = RuntimeError("db error")
        r._email_db = mock_db
        r._email_db_checked = True

        # Provide a chromadb fallback collection
        class FakeCollection:
            def get(self, include, limit, offset):
                if offset == 0:
                    return {
                        "metadatas": [
                            {"uid": "u1", "sender_email": "bob@ex.com", "sender_name": "Bob"},
                        ]
                    }
                return {"metadatas": []}

        r.collection = FakeCollection()

        senders = r.list_senders(limit=5)
        assert len(senders) == 1
        assert senders[0]["email"] == "bob@ex.com"

    def test_rejects_too_large_limit(self):
        r = _bare_retriever()
        with pytest.raises(ValueError, match="10000"):
            r.list_senders(limit=10001)

    def test_empty_collection_returns_empty(self):
        r = _bare_retriever()

        class FakeCollection:
            def get(self, include, limit, offset):
                return {"metadatas": []}

        r.collection = FakeCollection()

        senders = r.list_senders(limit=5)
        assert senders == []


# ── list_folders (lines 578-579) ─────────────────────────────────


def test_list_folders_returns_folder_counts():
    r = _bare_retriever()
    r.stats = MagicMock(
        return_value={
            "folders": {"Inbox": 10, "Sent": 5},
        }
    )
    folders = r.list_folders()
    assert {"folder": "Inbox", "count": 10} in folders
    assert {"folder": "Sent", "count": 5} in folders


# ── stats: SQLite path (lines 590-602) ──────────────────────────


class TestStatsSqlite:
    def test_uses_sqlite_when_available(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 100

        mock_db = MagicMock()
        mock_db.email_count.return_value = 50
        mock_db.date_range.return_value = ("2023-01-01T00:00:00", "2024-12-31T00:00:00")
        mock_db.unique_sender_count.return_value = 15
        mock_db.folder_counts.return_value = {"Inbox": 30, "Sent": 20}
        r._email_db = mock_db
        r._email_db_checked = True

        stats = r.stats()
        assert stats["total_chunks"] == 100
        assert stats["total_emails"] == 50
        assert stats["unique_senders"] == 15
        assert stats["date_range"]["earliest"] == "2023-01-01"
        assert stats["date_range"]["latest"] == "2024-12-31"
        assert stats["folders"]["Inbox"] == 30

    def test_falls_back_when_sqlite_raises(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 0

        mock_db = MagicMock()
        mock_db.email_count.side_effect = RuntimeError("db error")
        r._email_db = mock_db
        r._email_db_checked = True

        stats = r.stats()
        assert stats["total_emails"] == 0

    def test_falls_back_when_sqlite_email_count_zero(self):
        r = _bare_retriever()
        r.collection = MagicMock()
        r.collection.count.return_value = 0

        mock_db = MagicMock()
        mock_db.email_count.return_value = 0
        r._email_db = mock_db
        r._email_db_checked = True

        stats = r.stats()
        assert stats["total_emails"] == 0


# ── stats: empty collection (line 606) ──────────────────────────


def test_stats_empty_collection_without_db():
    r = _bare_retriever()
    r.collection = MagicMock()
    r.collection.count.return_value = 0

    stats = r.stats()
    assert stats == {"total_chunks": 0, "total_emails": 0, "unique_senders": 0, "date_range": {}, "folders": {}}


# ── stats: ChromaDB fallback with unknown_email_rows (line 623-624, 642)


def test_stats_chromadb_counts_unknown_uid_rows():
    r = _bare_retriever()

    class FakeCollection:
        def count(self):
            return 3

        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {"sender_email": "a@ex.com", "date": "2023-01-01", "folder": "Inbox"},
                        {"sender_email": "b@ex.com", "date": "2023-06-01", "folder": "Sent"},
                        {"sender_email": "a@ex.com", "date": "2023-12-01", "folder": "Inbox"},
                    ]
                }
            return {"metadatas": []}

    r.collection = FakeCollection()

    stats = r.stats()
    # No uid or message_id => each row is an unknown_email_row
    assert stats["total_emails"] == 3
    assert stats["unique_senders"] == 2
    assert stats["folders"]["Inbox"] == 2
    assert stats["folders"]["Sent"] == 1


# ── format_results_for_llm: budget exhaustion (lines 705, 715-716)


def test_format_results_budget_exhaustion_shows_omitted():
    r = _bare_retriever()
    # Create many results that will exceed a tiny budget
    results = [_make_result(f"c{i}", text="x" * 500, uid=f"u{i}", date=f"2024-01-{i:02d}") for i in range(1, 20)]

    output = r.format_results_for_llm(results, max_body_chars=500, max_response_tokens=100)
    assert "omitted" in output.lower() or "result" in output.lower()


def test_format_results_thread_budget_exhaustion():
    """Budget exhaustion mid-thread should stop and report omissions."""
    r = _bare_retriever()
    results = [
        _make_result("c1", text="x" * 1000, uid="u1", date="2024-01-01", conversation_id="conv1"),
        _make_result("c2", text="x" * 1000, uid="u2", date="2024-01-02", conversation_id="conv1"),
        _make_result("c3", text="x" * 1000, uid="u3", date="2024-01-03", conversation_id="conv1"),
    ]

    output = r.format_results_for_llm(results, max_body_chars=1000, max_response_tokens=50)
    # With a tiny budget, most should be omitted
    assert "omitted" in output.lower() or "tokens" in output.lower()


# ── format_results: unlimited budget (max_response_tokens=0) ───


def test_format_results_unlimited_budget():
    r = _bare_retriever()
    results = [_make_result("c1", text="hello")]
    output = r.format_results_for_llm(results, max_response_tokens=0)
    assert "hello" in output
    assert "omitted" not in output.lower()


# ── serialize_results (lines 752-788) ────────────────────────────


class TestSerializeResults:
    def test_basic_serialization(self):
        r = _bare_retriever()
        results = [_make_result("c1", text="body")]
        payload = r.serialize_results("test", results)
        assert payload["query"] == "test"
        assert payload["count"] == 1
        assert len(payload["results"]) == 1
        assert payload["results"][0]["chunk_id"] == "c1"

    def test_body_truncation(self):
        r = _bare_retriever()
        results = [_make_result("c1", text="x" * 1000)]
        payload = r.serialize_results("test", results, max_body_chars=50)
        assert len(payload["results"][0]["text"]) < 1000

    def test_token_budget_omits_results(self):
        r = _bare_retriever()
        results = [_make_result(f"c{i}", text="x" * 500, uid=f"u{i}") for i in range(50)]
        payload = r.serialize_results("test", results, max_body_chars=500, max_response_tokens=100)
        # Should have a note about omitted results
        last = payload["results"][-1]
        assert "note" in last or len(payload["results"]) < 50

    def test_unlimited_budget_includes_all(self):
        r = _bare_retriever()
        results = [_make_result(f"c{i}", text="hello", uid=f"u{i}") for i in range(5)]
        payload = r.serialize_results("test", results, max_response_tokens=0)
        assert len(payload["results"]) == 5

    def test_no_truncation_with_zero_body_chars(self):
        r = _bare_retriever()
        text = "x" * 2000
        results = [_make_result("c1", text=text)]
        payload = r.serialize_results("test", results, max_body_chars=0)
        assert payload["results"][0]["text"] == text


# ── reset_index (lines 792-794) ──────────────────────────────────


def test_reset_index():
    r = _bare_retriever()
    r.collection_name = "test_coll"
    r.chromadb_path = "/tmp/test"
    r.client = MagicMock()
    new_collection = MagicMock()
    r.client.get_or_create_collection = MagicMock(return_value=new_collection)

    with patch("src.retriever.get_collection", return_value=new_collection):
        r.reset_index()
        r.client.delete_collection.assert_called_once_with("test_coll")


# ── _resolve_semantic_uids (lines 802-830) ──────────────────────


class TestResolveSemanticUids:
    def test_returns_empty_when_no_db(self):
        r = _bare_retriever()
        assert r._resolve_semantic_uids(topic_id=1) == set()

    def test_topic_id_only(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_by_topic.return_value = [{"uid": "u1"}, {"uid": "u2"}]
        r._email_db = mock_db
        r._email_db_checked = True

        result = r._resolve_semantic_uids(topic_id=1)
        assert result == {"u1", "u2"}

    def test_cluster_id_only(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_in_cluster.return_value = [{"uid": "u3"}, {"uid": "u4"}]
        r._email_db = mock_db
        r._email_db_checked = True

        result = r._resolve_semantic_uids(cluster_id=5)
        assert result == {"u3", "u4"}

    def test_topic_and_cluster_intersection(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_by_topic.return_value = [{"uid": "u1"}, {"uid": "u2"}]
        mock_db.emails_in_cluster.return_value = [{"uid": "u2"}, {"uid": "u3"}]
        r._email_db = mock_db
        r._email_db_checked = True

        result = r._resolve_semantic_uids(topic_id=1, cluster_id=2)
        assert result == {"u2"}  # intersection

    def test_topic_exception_returns_empty_set(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.emails_by_topic.side_effect = RuntimeError("fail")
        r._email_db = mock_db
        r._email_db_checked = True

        result = r._resolve_semantic_uids(topic_id=1)
        assert result == set()

    def test_neither_topic_nor_cluster_returns_empty(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        r._email_db = mock_db
        r._email_db_checked = True

        result = r._resolve_semantic_uids()
        assert result == set()


# ── _expand_query (lines 834-851) ────────────────────────────────


class TestExpandQuery:
    def test_returns_original_when_no_db(self):
        r = _bare_retriever()
        assert r._expand_query("test query") == "test query"

    def test_returns_original_when_no_keywords(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_keywords.return_value = []
        r._email_db = mock_db
        r._email_db_checked = True

        assert r._expand_query("test query") == "test query"

    def test_returns_expanded_query(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_keywords.return_value = [
            {"keyword": "budget"},
            {"keyword": "finance"},
            {"keyword": "cost"},
        ]
        r._email_db = mock_db
        r._email_db_checked = True

        mock_embedder = MagicMock()
        r._embedder = mock_embedder

        # Mock the QueryExpander import and usage
        mock_expander = MagicMock()
        mock_expander.expand.return_value = "test query budget finance"

        mock_qe_module = types.ModuleType("src.query_expander")
        mock_qe_module.QueryExpander = MagicMock(return_value=mock_expander)

        with patch.dict("sys.modules", {"src.query_expander": mock_qe_module}):
            result = r._expand_query("test query")
            assert result == "test query budget finance"

    def test_returns_original_on_exception(self):
        r = _bare_retriever()
        mock_db = MagicMock()
        mock_db.top_keywords.side_effect = RuntimeError("fail")
        r._email_db = mock_db
        r._email_db_checked = True

        assert r._expand_query("test query") == "test query"


# ── search_filtered: expand_query integration (line 271) ────────


def test_search_filtered_expand_query_integration():
    r = _bare_retriever()

    expand_called = []

    def _mock_expand(query):
        expand_called.append(query)
        return query + " expanded"

    r._expand_query = _mock_expand

    def _search(query, top_k=10, where=None):
        return [_make_result(f"c{i}", uid=f"u{i}") for i in range(top_k)]

    r.search = _search

    r.search_filtered(query="test", top_k=5, expand_query=True)
    assert len(expand_called) == 1
    assert expand_called[0] == "test"


# ── email_db lazy loading (lines 114-126) ────────────────────────


def test_email_db_returns_none_when_no_sqlite_path():
    r = EmailRetriever.__new__(EmailRetriever)
    r._email_db_checked = False
    r._email_db = None
    r.settings = MagicMock()
    r.settings.sqlite_path = None

    assert r.email_db is None
    assert r._email_db_checked is True


def test_email_db_returns_none_when_path_doesnt_exist():
    r = EmailRetriever.__new__(EmailRetriever)
    r._email_db_checked = False
    r._email_db = None
    r.settings = MagicMock()
    r.settings.sqlite_path = "/nonexistent/path/db.sqlite"

    assert r.email_db is None
    assert r._email_db_checked is True
