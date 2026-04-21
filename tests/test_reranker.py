"""Tests for cross-encoder reranker."""

from unittest.mock import MagicMock

from src.reranker import CrossEncoderReranker
from src.retriever import SearchResult


def _result(chunk_id: str = "c1", text: str = "body", distance: float = 0.3) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={"uid": chunk_id, "date": "2024-01-01"},
        distance=distance,
    )


def test_rerank_empty_input():
    reranker = CrossEncoderReranker()
    assert reranker.rerank("test query", []) == []


def test_rerank_reorders_by_score():
    reranker = CrossEncoderReranker()
    # Mock the model to return descending scores
    mock_model = MagicMock()
    # Score c3 highest, c1 lowest
    mock_model.predict.return_value = [-1.0, 0.0, 2.0]
    reranker._model = mock_model

    results = [_result("c1"), _result("c2"), _result("c3")]
    reranked = reranker.rerank("test", results)

    assert len(reranked) == 3
    assert reranked[0].chunk_id == "c3"
    assert reranked[1].chunk_id == "c2"
    assert reranked[2].chunk_id == "c1"


def test_rerank_top_k_limits():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [3.0, 1.0, 2.0]
    reranker._model = mock_model

    results = [_result("c1"), _result("c2"), _result("c3")]
    reranked = reranker.rerank("test", results, top_k=2)

    assert len(reranked) == 2
    assert reranked[0].chunk_id == "c1"  # highest raw score
    assert reranked[1].chunk_id == "c3"


def test_rerank_preserves_metadata():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0]
    reranker._model = mock_model

    result = SearchResult(
        chunk_id="c1",
        text="important body",
        metadata={"uid": "u1", "subject": "test subject", "sender_email": "a@b.com"},
        distance=0.5,
    )
    reranked = reranker.rerank("query", [result])
    assert reranked[0].metadata == result.metadata
    assert reranked[0].text == result.text
    assert reranked[0].chunk_id == result.chunk_id


def test_rerank_score_is_valid():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [5.0]  # High logit → sigmoid ~0.99
    reranker._model = mock_model

    results = [_result("c1")]
    reranked = reranker.rerank("test", results)

    # Score should be 0-1
    assert 0.0 <= reranked[0].score <= 1.0
    # High logit should produce high score
    assert reranked[0].score > 0.9


def test_rerank_negative_score():
    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [-5.0]  # Low logit → sigmoid ~0.01
    reranker._model = mock_model

    results = [_result("c1")]
    reranked = reranker.rerank("test", results)

    assert 0.0 <= reranked[0].score <= 1.0
    assert reranked[0].score < 0.1


def test_reranker_default_model_name():
    reranker = CrossEncoderReranker()
    assert "bge-reranker" in reranker.model_name


def test_reranker_custom_model_name():
    reranker = CrossEncoderReranker(model_name="custom/model")
    assert reranker.model_name == "custom/model"
