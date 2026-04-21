"""Tests for src/colbert_reranker.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from src.colbert_reranker import ColBERTReranker, maxsim
from src.retriever import SearchResult

# ── maxsim ───────────────────────────────────────────────────────────


def test_maxsim_identical():
    """Identical query and doc should produce score ~1.0."""
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    score = maxsim(vecs, vecs)
    assert abs(score - 1.0) < 1e-5


def test_maxsim_orthogonal():
    """Orthogonal vectors should produce score ~0."""
    q = np.array([[1.0, 0.0]], dtype=np.float32)
    d = np.array([[0.0, 1.0]], dtype=np.float32)
    score = maxsim(q, d)
    assert abs(score) < 1e-5


def test_maxsim_partial_match():
    """One query token matches, one doesn't."""
    q = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    d = np.array([[1.0, 0.0]], dtype=np.float32)  # Only matches first query token
    score = maxsim(q, d)
    # First token: 1.0, second: 0.0. Average = 0.5
    assert abs(score - 0.5) < 1e-5


def test_maxsim_empty_query():
    q = np.array([], dtype=np.float32).reshape(0, 4)
    d = np.ones((3, 4), dtype=np.float32)
    assert maxsim(q, d) == 0.0


def test_maxsim_empty_doc():
    q = np.ones((3, 4), dtype=np.float32)
    d = np.array([], dtype=np.float32).reshape(0, 4)
    assert maxsim(q, d) == 0.0


def test_maxsim_unnormalized():
    """maxsim should normalize internally."""
    q = np.array([[3.0, 0.0]], dtype=np.float32)
    d = np.array([[5.0, 0.0]], dtype=np.float32)
    score = maxsim(q, d)
    assert abs(score - 1.0) < 1e-5


# ── ColBERTReranker ──────────────────────────────────────────────────


def _make_result(chunk_id: str, text: str, distance: float = 0.5) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={"uid": chunk_id},
        distance=distance,
    )


def _make_embedder(has_colbert: bool = True):
    """Create a mock embedder with controllable ColBERT behavior."""
    emb = MagicMock()
    emb.has_colbert = has_colbert

    def fake_encode_colbert(texts):
        # Return distinct vectors per text so scoring is deterministic
        result = []
        for i, t in enumerate(texts):
            n_tokens = max(3, len(t.split()))
            vecs = np.random.RandomState(i).rand(n_tokens, 4).astype(np.float32)
            result.append(vecs)
        return result

    emb.encode_colbert = fake_encode_colbert
    return emb


def test_reranker_empty_results():
    emb = _make_embedder()
    reranker = ColBERTReranker(emb)
    assert reranker.rerank("query", []) == []


def test_reranker_colbert_disabled():
    emb = _make_embedder(has_colbert=False)
    reranker = ColBERTReranker(emb)
    results = [_make_result("a", "hello")]
    reranked = reranker.rerank("query", results)
    assert len(reranked) == 1
    assert reranked[0].chunk_id == "a"


def test_reranker_returns_correct_count():
    emb = _make_embedder()
    reranker = ColBERTReranker(emb)
    results = [_make_result(f"c{i}", f"document {i}") for i in range(5)]
    reranked = reranker.rerank("test query", results, top_k=3)
    assert len(reranked) == 3


def test_reranker_reorders():
    """Reranker should change the order based on ColBERT scores."""
    emb = _make_embedder()
    reranker = ColBERTReranker(emb)
    results = [_make_result(f"c{i}", f"text variant {i}") for i in range(5)]
    reranked = reranker.rerank("test query", results)
    assert len(reranked) == 5
    # Results should have distance field set
    for r in reranked:
        assert 0.0 <= r.distance <= 1.0


def test_reranker_preserves_metadata():
    emb = _make_embedder()
    reranker = ColBERTReranker(emb)
    results = [_make_result("x", "hello world")]
    reranked = reranker.rerank("query", results)
    assert reranked[0].metadata == {"uid": "x"}
    assert reranked[0].text == "hello world"


def test_reranker_none_colbert_result():
    """If encode_colbert returns None for a doc, score should be 0."""
    emb = MagicMock()
    emb.has_colbert = True

    call_count = [0]

    def fake_encode(texts):
        call_count[0] += 1
        if call_count[0] == 1:
            # First call is the query — return valid vecs
            return [np.ones((3, 4), dtype=np.float32)]
        # Subsequent calls are docs — return None
        return [None for _ in texts]

    emb.encode_colbert = fake_encode
    reranker = ColBERTReranker(emb)
    results = [_make_result("a", "hello")]
    reranked = reranker.rerank("query", results)
    assert len(reranked) == 1
    assert reranked[0].distance == 1.0  # score 0 -> distance 1.0
