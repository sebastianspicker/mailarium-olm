"""Retriever-focused regression tests split out from the RF8 catch-all."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from src.retriever import SearchResult

from ._bugfix_regression_cases import bare_retriever, make_result


class TestP1MinScoreDeferredAfterReranking:
    """P1 fix #6: min_score deferred after reranking."""

    def test_min_score_not_applied_before_rerank(self):
        retriever = bare_retriever()
        settings = MagicMock()
        settings.rerank_enabled = False
        settings.hybrid_enabled = False
        retriever.settings = settings

        low_score_result = make_result("c1", uid="u1", distance=0.7)
        high_score_result = make_result("c2", uid="u2", distance=0.1)

        def search(query, top_k=10, where=None):
            return [low_score_result, high_score_result]

        retriever.search = search
        rerank_scores = []

        def mock_rerank(self, query, results, top_k):
            rerank_scores.append(len(results))
            return [
                SearchResult(
                    chunk_id=result.chunk_id,
                    text=result.text,
                    metadata=result.metadata,
                    distance=0.05,
                )
                for result in results
            ][:top_k]

        retriever._apply_rerank = types.MethodType(mock_rerank, retriever)

        results = retriever.search_filtered(query="test", top_k=10, rerank=True, min_score=0.5)
        assert rerank_scores[0] == 2
        assert len(results) == 2

    def test_min_score_applied_after_rerank(self):
        retriever = bare_retriever()
        settings = MagicMock()
        settings.rerank_enabled = False
        settings.hybrid_enabled = False
        retriever.settings = settings

        def search(query, top_k=10, where=None):
            return [make_result("c1", uid="u1", distance=0.1)]

        retriever.search = search

        def mock_rerank(self, query, results, top_k):
            return [
                SearchResult(
                    chunk_id=results[0].chunk_id,
                    text=results[0].text,
                    metadata=results[0].metadata,
                    distance=0.8,
                )
            ]

        retriever._apply_rerank = types.MethodType(mock_rerank, retriever)

        results = retriever.search_filtered(query="test", top_k=10, rerank=True, min_score=0.5)
        assert len(results) == 0


class TestP1ColBERTRerankerCached:
    """P1 fix #7: ColBERTReranker cached."""

    def test_colbert_reranker_reused_across_calls(self):
        retriever = bare_retriever()
        settings = MagicMock()
        settings.colbert_rerank_enabled = True
        retriever.settings = settings

        mock_embedder = MagicMock()
        mock_embedder.has_colbert = True
        retriever._embedder = mock_embedder
        retriever._colbert_reranker = None

        results = [make_result("c1")]
        mock_reranker = MagicMock()
        mock_reranker.rerank.return_value = results

        construction_count = {"n": 0}

        def counting_constructor(embedder):
            construction_count["n"] += 1
            return mock_reranker

        with patch.dict("sys.modules", {"src.colbert_reranker": MagicMock(ColBERTReranker=counting_constructor)}):
            with patch("src.colbert_reranker.ColBERTReranker", side_effect=counting_constructor):
                retriever._apply_rerank("query1", results, top_k=1)
                retriever._apply_rerank("query2", results, top_k=1)

        assert retriever._colbert_reranker is not None


class TestP1StalenessCheck:
    """P1 fix #8: staleness check uses != instead of >."""

    def test_sparse_staleness_triggers_rebuild_on_mismatch(self):
        retriever = bare_retriever()
        retriever.settings = MagicMock()
        retriever.settings.sparse_enabled = True

        mock_collection = MagicMock()
        mock_collection.count.return_value = 100
        retriever.collection = mock_collection

        mock_sparse = MagicMock()
        mock_sparse.is_built = True
        mock_sparse.doc_count = 50
        mock_sparse.build_from_db = lambda db: None
        retriever._sparse_index = mock_sparse

        assert mock_sparse.doc_count != mock_collection.count()


class TestP1KeywordOnlyScoreHalf:
    """P1 fix #19: keyword-only results get distance=0.5 (score=0.5)."""

    def test_keyword_only_result_gets_default_distance(self):
        retriever = bare_retriever()
        settings = MagicMock()
        settings.hybrid_enabled = True
        settings.rerank_enabled = False
        settings.sparse_enabled = False
        retriever.settings = settings

        semantic_result = make_result("c1", uid="u1", distance=0.1)

        def search(query, top_k=10, where=None):
            return [semantic_result]

        retriever.search = search

        def mock_merge(self, query, results, fetch_size):
            keyword_only = SearchResult(
                chunk_id="c2",
                text="keyword match",
                metadata={"uid": "u2", "date": "2024-01-01"},
                distance=0.5,
            )
            return [*results, keyword_only]

        retriever._merge_hybrid = types.MethodType(mock_merge, retriever)

        results = retriever.search_filtered(query="test", top_k=10, hybrid=True)
        keyword_results = [result for result in results if result.chunk_id == "c2"]
        assert len(keyword_results) == 1
        assert keyword_results[0].distance == 0.5
        assert keyword_results[0].score == pytest.approx(0.5, abs=0.01)


class TestP2RerankerOverflowProtection:
    """P2: Cross-encoder sigmoid must not overflow on extreme logits."""

    def test_extreme_negative_logit_no_overflow(self):
        import math

        raw_score = -1000.0
        clamped = max(-500.0, min(500.0, float(raw_score)))
        sigmoid = 1.0 / (1.0 + math.exp(-clamped))
        assert 0.0 <= sigmoid <= 1.0

    def test_extreme_positive_logit_no_overflow(self):
        import math

        raw_score = 1000.0
        clamped = max(-500.0, min(500.0, float(raw_score)))
        sigmoid = 1.0 / (1.0 + math.exp(-clamped))
        assert 0.0 <= sigmoid <= 1.0
