"""Tests for src/sparse_index.py and sparse vector storage in email_db."""

from __future__ import annotations

from src.email_db import EmailDatabase
from src.sparse_index import SparseIndex

# ── SparseIndex ──────────────────────────────────────────────────────


def test_sparse_index_not_built():
    idx = SparseIndex()
    assert not idx.is_built
    assert idx.search({1: 0.5}, top_k=5) == []


def test_sparse_index_build_empty():
    idx = SparseIndex()
    idx.build_from_vectors({})
    assert idx.is_built
    assert idx.doc_count == 0
    assert idx.search({1: 0.5}) == []


def test_sparse_index_build_and_search():
    vectors = {
        "chunk_a": {1: 0.8, 2: 0.5},
        "chunk_b": {2: 0.3, 3: 0.9},
        "chunk_c": {1: 0.1, 3: 0.2},
    }
    idx = SparseIndex()
    idx.build_from_vectors(vectors)

    assert idx.is_built
    assert idx.doc_count == 3

    # Query with token 1 should rank chunk_a first
    results = idx.search({1: 1.0}, top_k=10)
    assert len(results) >= 2
    assert results[0][0] == "chunk_a"


def test_sparse_index_top_k():
    vectors = {f"c{i}": {1: float(i)} for i in range(10)}
    idx = SparseIndex()
    idx.build_from_vectors(vectors)

    results = idx.search({1: 1.0}, top_k=3)
    assert len(results) == 3
    # Highest weight first
    assert results[0][0] == "c9"


def test_sparse_index_multi_token_query():
    vectors = {
        "doc1": {10: 0.5, 20: 0.3},
        "doc2": {10: 0.1, 30: 0.9},
        "doc3": {20: 0.8, 30: 0.4},
    }
    idx = SparseIndex()
    idx.build_from_vectors(vectors)

    # Query both token 10 and 20 — doc1 has both
    results = idx.search({10: 1.0, 20: 1.0}, top_k=10)
    # doc1 should be first (matches both tokens)
    assert results[0][0] == "doc1"


def test_sparse_index_empty_query():
    idx = SparseIndex()
    idx.build_from_vectors({"a": {1: 0.5}})
    assert idx.search({}) == []


def test_sparse_index_zero_weight_query():
    idx = SparseIndex()
    idx.build_from_vectors({"a": {1: 0.5}})
    assert idx.search({1: 0.0}) == []


# ── SQLite sparse vector storage ──────────────────────────────────────


def test_db_insert_and_get_sparse():
    db = EmailDatabase(":memory:")
    sv = {1: 0.5, 42: 0.9, 100: 0.3}
    db.insert_sparse_batch(["chunk1"], [sv])

    result = db.get_sparse_vector("chunk1")
    assert result is not None
    assert abs(result[1] - sv[1]) < 1e-6
    assert abs(result[42] - sv[42]) < 1e-6
    assert abs(result[100] - sv[100]) < 1e-6


def test_db_insert_sparse_replaces():
    db = EmailDatabase(":memory:")
    db.insert_sparse_batch(["c1"], [{1: 0.5}])
    db.insert_sparse_batch(["c1"], [{1: 0.9, 2: 0.3}])

    result = db.get_sparse_vector("c1")
    assert result is not None
    assert abs(result[1] - 0.9) < 0.01
    assert 2 in result


def test_db_get_sparse_missing():
    db = EmailDatabase(":memory:")
    assert db.get_sparse_vector("missing") is None


def test_db_sparse_vector_count():
    db = EmailDatabase(":memory:")
    assert db.sparse_vector_count() == 0
    db.insert_sparse_batch(["a", "b"], [{1: 0.5}, {2: 0.3}])
    assert db.sparse_vector_count() == 2


def test_db_all_sparse_vectors():
    db = EmailDatabase(":memory:")
    db.insert_sparse_batch(
        ["x", "y"],
        [{10: 0.8, 20: 0.3}, {30: 0.9}],
    )
    all_vecs = db.all_sparse_vectors()
    assert len(all_vecs) == 2
    assert 10 in all_vecs["x"]
    assert 30 in all_vecs["y"]


def test_db_iter_sparse_vectors():
    db = EmailDatabase(":memory:")
    db.insert_sparse_batch(
        ["x", "y"],
        [{10: 0.8, 20: 0.3}, {30: 0.9}],
    )
    rows = dict(db.iter_sparse_vectors())
    assert len(rows) == 2
    assert 10 in rows["x"]
    assert 30 in rows["y"]


def test_db_insert_sparse_skips_empty():
    db = EmailDatabase(":memory:")
    inserted = db.insert_sparse_batch(["a", "b"], [{1: 0.5}, {}])
    assert inserted == 1


def test_db_insert_sparse_length_mismatch():
    db = EmailDatabase(":memory:")
    try:
        db.insert_sparse_batch(["a"], [{1: 0.5}, {2: 0.3}])
        raise AssertionError("Should have raised ValueError")
    except ValueError:
        pass


def test_sparse_index_build_from_db():
    """End-to-end: store in SQLite, build index, search."""
    db = EmailDatabase(":memory:")
    db.insert_sparse_batch(
        ["doc_a", "doc_b", "doc_c"],
        [{1: 0.8, 2: 0.5}, {2: 0.3, 3: 0.9}, {1: 0.1}],
    )

    idx = SparseIndex()
    idx.build_from_db(db)

    assert idx.doc_count == 3
    results = idx.search({1: 1.0}, top_k=2)
    assert results[0][0] == "doc_a"


def test_sparse_search_with_normalization():
    """A short focused doc should rank above a long diluted doc when normalize=True."""
    vectors = {
        # Short doc: focused on token 1
        "short_focused": {1: 0.9},
        # Long doc: mentions token 1 weakly among many tokens
        "long_diluted": {1: 0.5, 2: 0.8, 3: 0.7, 4: 0.6, 5: 0.5},
    }
    idx = SparseIndex()
    idx.build_from_vectors(vectors)

    # Without normalization, long_diluted has a lower raw score but still token 1
    results_raw = idx.search({1: 1.0}, top_k=10, normalize=False)
    # short_focused: 0.9, long_diluted: 0.5 — short wins in raw too
    assert results_raw[0][0] == "short_focused"

    # Now give long_diluted a higher raw dot product on query token
    vectors2 = {
        "short_focused": {1: 0.5},
        "long_diluted": {1: 0.6, 2: 0.8, 3: 0.7, 4: 0.6, 5: 0.5},
    }
    idx2 = SparseIndex()
    idx2.build_from_vectors(vectors2)

    # Without normalization, long_diluted wins (0.6 > 0.5)
    results_raw2 = idx2.search({1: 1.0}, top_k=10, normalize=False)
    assert results_raw2[0][0] == "long_diluted"

    # With normalization, short_focused should win (0.5/0.5=1.0 vs 0.6/1.3≈0.46)
    results_norm = idx2.search({1: 1.0}, top_k=10, normalize=True)
    assert results_norm[0][0] == "short_focused"


def test_schema_v5_migration():
    """Ensure schema v5 creates sparse_vectors table."""
    db = EmailDatabase(":memory:")
    # Table should exist after init
    row = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sparse_vectors'").fetchone()
    assert row is not None
