from __future__ import annotations

from src.retriever import EmailRetriever, SearchResult


def test_search_filtered_records_query_expansion_failure_diagnostics(monkeypatch) -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def fail_import(name: str):
        raise RuntimeError(f"cannot import {name}")

    def search(query: str, top_k: int = 10, where=None):
        return [
            SearchResult(
                chunk_id="c1",
                text="budget body",
                metadata={"uid": "u1", "date": "2024-01-01T00:00:00Z"},
                distance=0.1,
            )
        ]

    monkeypatch.setattr("src.retriever_admin.import_module", fail_import)
    retriever.search = search

    results = retriever.search_filtered(query="budget", expand_query=True)

    assert len(results) == 1
    assert retriever.last_search_debug["executed_query"] == "budget"
    assert retriever.last_search_debug["used_query_expansion"] is False
    assert retriever.last_search_debug["query_expansion_status"] == "error"
    assert retriever.last_search_debug["query_expansion_error_type"] == "RuntimeError"
