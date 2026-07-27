"""Exercises recipient, attachment-presence, and priority filters in email search results.

It treats blank or unspecified optional filters as no constraint rather than rejecting valid retrieval.
"""

from __future__ import annotations

import pytest

from mailarium.retriever import EmailRetriever, SearchResult


def test_search_filtered_applies_cc_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="match",
                text="hello",
                metadata={"cc": "finance-team@example.com, legal@example.com", "date": "2024-01-01"},
                distance=0.1,
            ),
            SearchResult(
                chunk_id="no-cc",
                text="hello",
                metadata={"cc": "", "date": "2024-01-01"},
                distance=0.2,
            ),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", cc="finance-team", top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == "match"


def test_search_filtered_applies_to_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="match",
                text="hello",
                metadata={"to": "employee@example.test, bob@example.com", "date": "2024-01-01"},
                distance=0.1,
            ),
            SearchResult(
                chunk_id="no-match",
                text="hello",
                metadata={"to": "carol@example.com", "date": "2024-01-01"},
                distance=0.2,
            ),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", to="employee", top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == "match"


def test_search_filtered_to_filter_blank_is_no_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult("r1", "text", {"to": "a@example.com", "date": "2024-01-01"}, 0.2),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", to="   ", top_k=1)

    assert len(results) == 1


def test_search_filtered_applies_bcc_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="match",
                text="hello",
                metadata={"bcc": "secret@example.com", "date": "2024-01-01"},
                distance=0.1,
            ),
            SearchResult(
                chunk_id="no-match",
                text="hello",
                metadata={"bcc": "", "date": "2024-01-01"},
                distance=0.2,
            ),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", bcc="secret", top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == "match"


@pytest.mark.parametrize(
    ("has_attachments", "expected_chunk_id"),
    [(True, "with-att"), (False, "no-att")],
)
def test_search_filtered_applies_has_attachments(has_attachments: bool, expected_chunk_id: str) -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="with-att",
                text="hello",
                metadata={"has_attachments": "True", "date": "2024-01-01"},
                distance=0.1,
            ),
            SearchResult(
                chunk_id="no-att",
                text="hello",
                metadata={"has_attachments": "False", "date": "2024-01-01"},
                distance=0.2,
            ),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", has_attachments=has_attachments, top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == expected_chunk_id


def test_search_filtered_applies_priority_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="high-pri",
                text="urgent",
                metadata={"priority": "2", "date": "2024-01-01"},
                distance=0.1,
            ),
            SearchResult(
                chunk_id="low-pri",
                text="normal",
                metadata={"priority": "0", "date": "2024-01-01"},
                distance=0.2,
            ),
            SearchResult(
                chunk_id="no-pri",
                text="normal",
                metadata={"date": "2024-01-01"},
                distance=0.3,
            ),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", priority=1, top_k=5)

    assert len(results) == 1
    assert results[0].chunk_id == "high-pri"


def test_search_filtered_priority_none_is_no_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult("r1", "text", {"priority": "0", "date": "2024-01-01"}, 0.2),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", priority=None, top_k=1)

    assert len(results) == 1


def test_search_filtered_has_attachments_none_is_no_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult("r1", "text", {"has_attachments": "True", "date": "2024-01-01"}, 0.2),
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", has_attachments=None, top_k=1)

    assert len(results) == 1
