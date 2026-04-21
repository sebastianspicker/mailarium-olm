"""Tests for per-email deduplication and thread-aware formatting."""

from src.retriever import EmailRetriever, SearchResult, _deduplicate_by_email

# ── _deduplicate_by_email ───────────────────────────────────────


def test_dedup_keeps_best_chunk_per_uid():
    results = [
        SearchResult("id1__0", "text1", {"uid": "email1"}, 0.1),  # best for email1
        SearchResult("id1__1", "text1b", {"uid": "email1"}, 0.2),  # duplicate
        SearchResult("id2__0", "text2", {"uid": "email2"}, 0.15),
        SearchResult("id1__2", "text1c", {"uid": "email1"}, 0.3),  # another dup
    ]
    deduped = _deduplicate_by_email(results)
    assert len(deduped) == 2
    assert deduped[0].chunk_id == "id1__0"
    assert deduped[1].chunk_id == "id2__0"


def test_dedup_preserves_order():
    results = [
        SearchResult("a", "t", {"uid": "u1"}, 0.05),
        SearchResult("b", "t", {"uid": "u2"}, 0.10),
        SearchResult("c", "t", {"uid": "u3"}, 0.15),
        SearchResult("d", "t", {"uid": "u1"}, 0.20),
    ]
    deduped = _deduplicate_by_email(results)
    assert [r.chunk_id for r in deduped] == ["a", "b", "c"]


def test_dedup_handles_empty_uid():
    results = [
        SearchResult("a", "t", {"uid": ""}, 0.1),
        SearchResult("b", "t", {"uid": ""}, 0.2),
        SearchResult("c", "t", {"uid": "u1"}, 0.3),
    ]
    deduped = _deduplicate_by_email(results)
    # Empty UIDs are not deduplicated
    assert len(deduped) == 3


def test_dedup_handles_missing_uid():
    results = [
        SearchResult("a", "t", {}, 0.1),
        SearchResult("b", "t", {"uid": "u1"}, 0.2),
    ]
    deduped = _deduplicate_by_email(results)
    assert len(deduped) == 2


def test_dedup_empty_list():
    assert _deduplicate_by_email([]) == []


def test_dedup_single_result():
    results = [SearchResult("a", "t", {"uid": "u1"}, 0.1)]
    assert len(_deduplicate_by_email(results)) == 1


# ── Thread-aware formatting ─────────────────────────────────────


def test_format_results_groups_threads():
    retriever = EmailRetriever.__new__(EmailRetriever)

    results = [
        SearchResult("a", "Email A", {"conversation_id": "conv1", "date": "2025-01-02"}, 0.1),
        SearchResult("b", "Email B", {"conversation_id": "conv1", "date": "2025-01-01"}, 0.2),
        SearchResult("c", "Email C", {"conversation_id": "", "date": "2025-01-01"}, 0.15),
    ]

    formatted = retriever.format_results_for_llm(results)
    assert "Conversation Thread (2 emails)" in formatted
    assert "End Thread" in formatted
    # Thread members should be sorted by date (B before A)
    b_pos = formatted.index("Email B")
    a_pos = formatted.index("Email A")
    assert b_pos < a_pos


def test_format_results_no_grouping_for_single_conversation_member():
    retriever = EmailRetriever.__new__(EmailRetriever)

    results = [
        SearchResult("a", "Email A", {"conversation_id": "conv1", "date": "2025-01-01"}, 0.1),
        SearchResult("b", "Email B", {"conversation_id": "conv2", "date": "2025-01-02"}, 0.2),
    ]

    formatted = retriever.format_results_for_llm(results)
    assert "Conversation Thread" not in formatted


def test_format_results_empty():
    retriever = EmailRetriever.__new__(EmailRetriever)
    assert retriever.format_results_for_llm([]) == "No matching emails found."


# ── Dedup integration in search_filtered ─────────────────────────


def test_search_filtered_deduplicates():
    """search_filtered returns unique emails, not duplicate chunks."""
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult("id1__0", "chunk 0", {"uid": "email1", "date": "2025-01-01"}, 0.05),
            SearchResult("id1__1", "chunk 1", {"uid": "email1", "date": "2025-01-01"}, 0.10),
            SearchResult("id1__2", "chunk 2", {"uid": "email1", "date": "2025-01-01"}, 0.15),
            SearchResult("id2__0", "chunk 0", {"uid": "email2", "date": "2025-01-01"}, 0.20),
            SearchResult("id3__0", "chunk 0", {"uid": "email3", "date": "2025-01-01"}, 0.25),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="test", top_k=3)

    uids = [r.metadata.get("uid") for r in results]
    assert uids == ["email1", "email2", "email3"]
    assert results[0].chunk_id == "id1__0"  # Best chunk for email1


# ── Query embedding cache ──────────────────────────────────────


def test_query_cache_hit():
    """_encode_query should return cached embedding on second call."""
    retriever = EmailRetriever.__new__(EmailRetriever)
    call_count = 0

    class DummyEmbedder:
        def encode_dense(self, texts):
            nonlocal call_count
            call_count += 1
            return [[0.1, 0.2, 0.3]]

    retriever._embedder = DummyEmbedder()
    # First call encodes
    e1 = retriever._encode_query("hello")
    assert call_count == 1
    # Second call hits cache
    e2 = retriever._encode_query("hello")
    assert call_count == 1  # not called again
    assert e1 is e2


def test_query_cache_eviction():
    """Cache evicts oldest entries when exceeding max size."""
    from src.retriever import _QUERY_CACHE_MAX

    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyEmbedder:
        def encode_dense(self, texts):
            return [[float(hash(texts[0]) % 100)]]

    retriever._embedder = DummyEmbedder()

    # Fill cache beyond max
    for i in range(_QUERY_CACHE_MAX + 10):
        retriever._encode_query(f"query_{i}")

    assert len(retriever._query_cache) <= _QUERY_CACHE_MAX
