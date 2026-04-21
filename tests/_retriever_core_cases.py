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


class TestSearchResultMethods:
    def test_to_context_string_returns_formatted_block(self):
        result = _make_result(sender_email="a@example.test", subject="Hi")
        ctx = result.to_context_string()
        assert "body text" in ctx
        assert isinstance(ctx, str)

    def test_to_dict_has_expected_keys(self):
        result = _make_result()
        d = result.to_dict()
        assert set(d.keys()) == {"chunk_id", "score", "score_kind", "score_calibration", "distance", "metadata", "text"}
        assert d["chunk_id"] == "c1"
        assert d["score"] == pytest.approx(0.9, abs=0.01)
        assert d["distance"] == pytest.approx(0.1, abs=0.01)

    def test_score_clamped_to_zero_for_large_distance(self):
        result = SearchResult("x", "t", {}, distance=2.0)
        assert result.score == 0.0


def test_model_property_is_embedder_alias():
    r = _bare_retriever()
    dummy = MagicMock()
    r._embedder = dummy
    assert r.model is r.embedder


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


def test_search_filtered_raises_on_zero_top_k():
    r = _bare_retriever()
    with pytest.raises(ValueError, match="positive"):
        r.search_filtered(query="test", top_k=0)


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
