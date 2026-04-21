from __future__ import annotations

from src.retriever import EmailRetriever, SearchResult


def test_search_filtered_combined_new_filters() -> None:
    """Multiple new filters applied together."""
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="perfect",
                text="hello",
                metadata={
                    "to": "employee@example.test",
                    "has_attachments": "True",
                    "priority": "2",
                    "date": "2024-01-01",
                },
                distance=0.1,
            ),
            SearchResult(
                chunk_id="wrong-to",
                text="hello",
                metadata={
                    "to": "bob@example.com",
                    "has_attachments": "True",
                    "priority": "2",
                    "date": "2024-01-01",
                },
                distance=0.1,
            ),
            SearchResult(
                chunk_id="no-att",
                text="hello",
                metadata={
                    "to": "employee@example.test",
                    "has_attachments": "False",
                    "priority": "2",
                    "date": "2024-01-01",
                },
                distance=0.1,
            ),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", to="employee", has_attachments=True, priority=1, top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == "perfect"
