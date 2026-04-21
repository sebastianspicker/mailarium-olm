"""Tests for BM25 index and reciprocal rank fusion."""

from src.bm25_index import BM25Index, reciprocal_rank_fusion


def test_bm25_build_and_search():
    index = BM25Index()
    index.build_from_documents(
        chunk_ids=["c1", "c2", "c3"],
        documents=[
            "the quick brown fox jumps over the lazy dog",
            "machine learning and artificial intelligence",
            "the brown fox is quick and clever",
        ],
    )
    assert index.is_built

    results = index.search("quick brown fox", top_k=3)
    assert len(results) > 0
    # c1 and c3 should score higher than c2 (they contain the query terms)
    result_ids = [r[0] for r in results]
    assert "c1" in result_ids
    assert "c3" in result_ids


def test_bm25_empty_index():
    index = BM25Index()
    assert not index.is_built
    assert index.search("test", top_k=5) == []


def test_bm25_build_empty_documents():
    index = BM25Index()
    index.build_from_documents([], [])
    assert index.is_built
    assert index.search("test") == []


def test_bm25_no_match_query():
    index = BM25Index()
    index.build_from_documents(
        chunk_ids=["c1"],
        documents=["the quick brown fox"],
    )
    # Query terms not in any document
    results = index.search("zzzznowordlikethis", top_k=5)
    assert results == []


def test_bm25_top_k_limits():
    index = BM25Index()
    index.build_from_documents(
        chunk_ids=["c1", "c2", "c3", "c4", "c5"],
        documents=[
            "apple banana cherry",
            "apple cherry date",
            "banana cherry elderberry",
            "apple banana fig",
            "cherry grape apple",
        ],
    )
    results = index.search("apple", top_k=2)
    assert len(results) <= 2


def test_bm25_scores_are_positive():
    index = BM25Index()
    index.build_from_documents(
        chunk_ids=["c1", "c2"],
        documents=["hello world", "world hello"],
    )
    results = index.search("hello", top_k=5)
    for _, score in results:
        assert score > 0


def test_bm25_empty_query():
    index = BM25Index()
    index.build_from_documents(["c1"], ["hello world"])
    assert index.search("", top_k=5) == []
    assert index.search("   ", top_k=5) == []


def test_bm25_morphology_matches_german_compound_variants():
    index = BM25Index()
    index.build_from_documents(
        chunk_ids=["c1", "c2"],
        documents=[
            "Stufenvorweggewährung wurde im Vorgang erwähnt.",
            "Unrelated meeting note.",
        ],
    )
    results = index.search("stufenvorweggewaehrung", top_k=5)

    assert results
    assert results[0][0] == "c1"


def test_bm25_search_with_diagnostics_reports_morph_only_hits():
    index = BM25Index()
    index.build_from_documents(
        chunk_ids=["c1", "c2"],
        documents=[
            "Stufenvorweggewährung wurde im Vorgang erwähnt.",
            "General process update.",
        ],
    )
    results, diagnostics = index.search_with_diagnostics("stufenvorweggewaehrung", top_k=5)

    assert results
    assert diagnostics["status"] == "ok"
    assert diagnostics["morph_hit_count"] >= diagnostics["raw_hit_count"]
    assert "morph_query_tokens" in diagnostics


# --------------------------------------------------------------------------
# Reciprocal Rank Fusion tests
# --------------------------------------------------------------------------


def test_rrf_merges_two_lists():
    semantic = ["a", "b", "c"]
    bm25 = ["c", "d", "a"]
    fused = reciprocal_rank_fusion(semantic, bm25)
    # All unique IDs should be present
    assert set(fused) == {"a", "b", "c", "d"}
    # 'a' appears in both at rank 0 and rank 2, 'c' at rank 2 and rank 0
    # Both should score higher than 'b' (only in one list) and 'd' (only in one list)
    assert fused[0] in ("a", "c")
    assert fused[1] in ("a", "c")


def test_rrf_identical_lists():
    ids = ["x", "y", "z"]
    fused = reciprocal_rank_fusion(ids, ids)
    # Same order preserved
    assert fused == ["x", "y", "z"]


def test_rrf_disjoint_lists():
    fused = reciprocal_rank_fusion(["a", "b"], ["c", "d"])
    assert set(fused) == {"a", "b", "c", "d"}
    # Items at same position in their respective lists should rank similarly
    assert len(fused) == 4


def test_rrf_empty_lists():
    assert reciprocal_rank_fusion([], []) == []
    assert reciprocal_rank_fusion(["a"], []) == ["a"]
    assert reciprocal_rank_fusion([], ["b"]) == ["b"]
