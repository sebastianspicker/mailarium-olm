"""Structural seam tests for the R5 retriever refactor."""

from __future__ import annotations

from src.retriever import EmailRetriever


def _bare_retriever() -> EmailRetriever:
    """Create a retriever instance without running expensive initialization."""
    return EmailRetriever.__new__(EmailRetriever)


def test_search_filtered_delegates_to_extracted_helpers(monkeypatch):
    """search_filtered should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    prepare_calls: list[tuple[str, int, str | None]] = []
    execute_calls: list[tuple[str, int]] = []

    def fake_prepare(instance, **kwargs):
        prepare_calls.append((kwargs["query"], kwargs["top_k"], kwargs["sender"]))
        return ("plan", "filters")

    def fake_execute(instance, plan, filters):
        execute_calls.append((plan, filters))
        return ["ok"]

    monkeypatch.setattr("src.retriever.prepare_filtered_search_impl", fake_prepare)
    monkeypatch.setattr("src.retriever.execute_filtered_search_impl", fake_execute)

    results = retriever.search_filtered(query="budget", top_k=3, sender="alice")

    assert results == ["ok"]
    assert prepare_calls == [("budget", 3, "alice")]
    assert execute_calls == [("plan", "filters")]


def test_search_delegates_to_extracted_helper(monkeypatch):
    """Dense search should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[str, int | None, dict | None]] = []

    def fake_search(instance, query, top_k=None, where=None):
        calls.append((query, top_k, where))
        return ["search"]

    monkeypatch.setattr("src.retriever.search_impl", fake_search)

    results = retriever.search("budget", top_k=5, where={"folder": "Inbox"})

    assert results == ["search"]
    assert calls == [("budget", 5, {"folder": "Inbox"})]


def test_query_with_embedding_delegates_to_extracted_helper(monkeypatch):
    """Precomputed-embedding search should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[list[list[float]], int, dict | None]] = []

    def fake_query(instance, query_embedding, n_results, where=None):
        calls.append((query_embedding, n_results, where))
        return ["query"]

    monkeypatch.setattr("src.retriever.query_with_embedding_impl", fake_query)

    results = retriever._query_with_embedding([[0.1, 0.2]], 7, where={"folder": "Inbox"})

    assert results == ["query"]
    assert calls == [([[0.1, 0.2]], 7, {"folder": "Inbox"})]


def test_search_by_thread_delegates_to_extracted_helper(monkeypatch):
    """search_by_thread should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[str, int]] = []

    def fake_search_by_thread(instance, conversation_id, top_k):
        calls.append((conversation_id, top_k))
        return ["thread"]

    monkeypatch.setattr("src.retriever.search_by_thread_impl", fake_search_by_thread)

    results = retriever.search_by_thread("conv-1", top_k=7)

    assert results == ["thread"]
    assert calls == [("conv-1", 7)]


def test_list_senders_and_stats_delegate_to_extracted_helpers(monkeypatch):
    """Administrative metadata surfaces should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    sender_calls: list[int] = []
    stats_calls: list[str] = []

    def fake_list_senders(instance, limit=50):
        sender_calls.append(limit)
        return [{"email": "alice@example.com", "count": 1}]

    def fake_stats(instance):
        stats_calls.append("stats")
        return {"folders": {"Inbox": 1}}

    monkeypatch.setattr("src.retriever.list_senders_impl", fake_list_senders)
    monkeypatch.setattr("src.retriever.stats_impl", fake_stats)

    senders = retriever.list_senders(limit=3)
    stats = retriever.stats()
    folders = retriever.list_folders()

    assert senders == [{"email": "alice@example.com", "count": 1}]
    assert stats == {"folders": {"Inbox": 1}}
    assert folders == [{"folder": "Inbox", "count": 1}]
    assert sender_calls == [3]
    assert stats_calls == ["stats", "stats"]


def test_format_results_for_llm_delegates_to_extracted_helper(monkeypatch):
    """LLM formatting should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[list[str], int | None, int | None]] = []

    def fake_format(instance, results, max_body_chars, max_response_tokens):
        calls.append((results, max_body_chars, max_response_tokens))
        return "formatted"

    monkeypatch.setattr("src.retriever.format_results_for_llm_impl", fake_format)

    output = retriever.format_results_for_llm(["r1"], max_body_chars=123, max_response_tokens=456)

    assert output == "formatted"
    assert calls == [(["r1"], 123, 456)]


def test_serialize_results_delegates_to_extracted_helper(monkeypatch):
    """Result serialization should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[str, list[str], int | None, int | None]] = []

    def fake_serialize(instance, query, results, max_body_chars, max_response_tokens):
        calls.append((query, results, max_body_chars, max_response_tokens))
        return {"query": query, "results": results}

    monkeypatch.setattr("src.retriever.serialize_results_impl", fake_serialize)

    payload = retriever.serialize_results("budget", ["r1"], max_body_chars=50, max_response_tokens=80)

    assert payload == {"query": "budget", "results": ["r1"]}
    assert calls == [("budget", ["r1"], 50, 80)]


def test_merge_hybrid_delegates_to_extracted_helper(monkeypatch):
    """Hybrid merge should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[str, list[str], int]] = []

    def fake_merge(instance, query, semantic_results, fetch_size):
        calls.append((query, semantic_results, fetch_size))
        return ["merged"]

    monkeypatch.setattr("src.retriever.merge_hybrid_impl", fake_merge)

    results = retriever._merge_hybrid("budget", ["semantic"], 25)

    assert results == ["merged"]
    assert calls == [("budget", ["semantic"], 25)]


def test_get_sparse_results_delegates_to_extracted_helper(monkeypatch):
    """Sparse retrieval helper should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[str, int]] = []

    def fake_sparse(instance, query, top_k):
        calls.append((query, top_k))
        return ["c1"]

    monkeypatch.setattr("src.retriever.get_sparse_results_impl", fake_sparse)

    results = retriever._get_sparse_results("budget", 7)

    assert results == ["c1"]
    assert calls == [("budget", 7)]


def test_get_bm25_results_delegates_to_extracted_helper(monkeypatch):
    """BM25 fallback helper should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    calls: list[tuple[str, int]] = []

    def fake_bm25(instance, query, top_k):
        calls.append((query, top_k))
        return ["c2"]

    monkeypatch.setattr("src.retriever.get_bm25_results_impl", fake_bm25)

    results = retriever._get_bm25_results("budget", 9)

    assert results == ["c2"]
    assert calls == [("budget", 9)]


def test_semantic_uid_resolution_and_query_expansion_delegate_to_extracted_helpers(monkeypatch):
    """Semantic UID resolution and expansion should keep delegating through the stable seam."""
    retriever = _bare_retriever()
    uid_calls: list[tuple[int | None, int | None]] = []
    expand_calls: list[str] = []

    def fake_resolve(instance, topic_id=None, cluster_id=None):
        uid_calls.append((topic_id, cluster_id))
        return {"uid-1"}

    def fake_expand(instance, query):
        expand_calls.append(query)
        return f"expanded:{query}"

    monkeypatch.setattr("src.retriever.resolve_semantic_uids_impl", fake_resolve)
    monkeypatch.setattr("src.retriever.expand_query_impl", fake_expand)

    resolved = retriever._resolve_semantic_uids(topic_id=4, cluster_id=9)
    expanded = retriever._expand_query("budget")

    assert resolved == {"uid-1"}
    assert expanded == "expanded:budget"
    assert uid_calls == [(4, 9)]
    assert expand_calls == ["budget"]
