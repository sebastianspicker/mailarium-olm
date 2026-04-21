from __future__ import annotations

import pytest

from src.retriever import EmailRetriever, SearchResult


def test_search_filtered_expands_candidate_window_when_needed() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    calls = {"n": 0}

    def _search(query, top_k=10, where=None):
        calls["n"] += 1
        if top_k <= 16:
            return [
                SearchResult(
                    f"x{i}",
                    "text",
                    {"sender_email": f"user{i}@example.com", "uid": f"u{i}", "date": "2024-01-01"},
                    0.1,
                )
                for i in range(top_k)
            ]
        return [
            SearchResult("a", "text", {"sender_email": "x@example.com", "uid": "ua", "date": "2024-01-01"}, 0.1),
            SearchResult("c", "text", {"sender_email": "target@example.com", "uid": "uc", "date": "2024-01-01"}, 0.3),
        ]

    retriever.search = _search

    results = retriever.search_filtered(query="budget", sender="target", top_k=1)

    assert len(results) == 1
    assert results[0].chunk_id == "c"
    assert calls["n"] >= 2


def test_search_filtered_rejects_excessive_top_k() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    with pytest.raises(ValueError):
        retriever.search_filtered(query="budget", top_k=2000)


def test_search_filtered_allows_large_top_k_with_filters() -> None:
    retriever = EmailRetriever()
    retriever._encode_query = lambda _query: [[0.1, 0.2, 0.3]]
    retriever._merge_hybrid = lambda _query, raw_candidates, _fetch_size: raw_candidates
    retriever._apply_rerank = lambda _query, deduped, top_k: deduped[:top_k]

    size = 250
    retriever.collection.add(
        ids=[f"id-{idx}" for idx in range(size)],
        embeddings=[[0.1, 0.2, 0.3] for _ in range(size)],
        documents=[f"email {idx}" for idx in range(size)],
        metadatas=[
            {
                "uid": f"u-{idx}",
                "sender_email": "target@example.com",
                "sender_name": "Target",
                "date": "2024-01-01T00:00:00Z",
            }
            for idx in range(size)
        ],
    )

    results = retriever.search_filtered(
        query="budget",
        sender="target@example.com",
        top_k=200,
    )

    assert len(results) == 200


def test_search_filtered_treats_blank_sender_as_no_filter() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="r1",
                text="hello",
                metadata={"sender_email": "a@example.com", "date": "2024-01-01"},
                distance=0.2,
            )
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", sender="   ", top_k=1)

    assert len(results) == 1
    assert results[0].chunk_id == "r1"


def test_search_filtered_applies_subject_folder_and_min_score() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="match",
                text="hello",
                metadata={
                    "sender_email": "a@example.com",
                    "subject": "Budget Approval Request",
                    "folder": "Inbox/Finance",
                    "date": "2024-01-01",
                },
                distance=0.15,
            ),
            SearchResult(
                chunk_id="low-score",
                text="hello",
                metadata={
                    "sender_email": "a@example.com",
                    "subject": "Budget Approval Request",
                    "folder": "Inbox/Finance",
                    "date": "2024-01-01",
                },
                distance=0.30,
            ),
            SearchResult(
                chunk_id="wrong-folder",
                text="hello",
                metadata={
                    "sender_email": "a@example.com",
                    "subject": "Budget Approval Request",
                    "folder": "Archive",
                    "date": "2024-01-01",
                },
                distance=0.10,
            ),
            SearchResult(
                chunk_id="wrong-subject",
                text="hello",
                metadata={
                    "sender_email": "a@example.com",
                    "subject": "Travel Itinerary",
                    "folder": "Inbox/Finance",
                    "date": "2024-01-01",
                },
                distance=0.10,
            ),
        ]

    retriever.search = _search

    results = retriever.search_filtered(
        query="budget",
        subject="approval",
        folder="finance",
        min_score=0.8,
        top_k=5,
    )

    assert len(results) == 1
    assert results[0].chunk_id == "match"


def test_search_filtered_rejects_invalid_min_score() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    with pytest.raises(ValueError):
        retriever.search_filtered(query="budget", min_score=1.5)


def test_search_filtered_sender_filter_handles_non_string_metadata() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="r1",
                text="hello",
                metadata={"sender_email": None, "sender_name": 123, "date": "2024-01-01"},
                distance=0.2,
            )
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", sender="alice", top_k=1)

    assert results == []


def test_search_filtered_subject_filter_handles_none_metadata() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="r1",
                text="hello",
                metadata={"subject": None, "folder": "Inbox", "date": "2024-01-01"},
                distance=0.2,
            )
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", subject="none", top_k=1)

    assert results == []


def test_search_filtered_folder_filter_handles_none_metadata() -> None:
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            SearchResult(
                chunk_id="r1",
                text="hello",
                metadata={"subject": "Budget", "folder": None, "date": "2024-01-01"},
                distance=0.2,
            )
        ]

    retriever.search = _search
    results = retriever.search_filtered(query="budget", folder="none", top_k=1)

    assert results == []


class TestDateFilterNoneDate:
    """Regression: emails with None/missing date must be excluded by date filters."""

    def test_date_from_excludes_none_date(self) -> None:
        from src.result_filters import _matches_date_from

        result = SearchResult("c1", "text", {"date": None, "uid": "u1"}, 0.1)
        assert _matches_date_from(result, "2024-01-01") is False

    def test_date_to_excludes_none_date(self) -> None:
        from src.result_filters import _matches_date_to

        result = SearchResult("c1", "text", {"date": None, "uid": "u1"}, 0.1)
        assert _matches_date_to(result, "2024-12-31") is False

    def test_date_from_excludes_missing_date(self) -> None:
        from src.result_filters import _matches_date_from

        result = SearchResult("c1", "text", {"uid": "u1"}, 0.1)
        assert _matches_date_from(result, "2024-01-01") is False

    def test_date_to_excludes_missing_date(self) -> None:
        from src.result_filters import _matches_date_to

        result = SearchResult("c1", "text", {"uid": "u1"}, 0.1)
        assert _matches_date_to(result, "2024-12-31") is False

    def test_date_from_includes_valid_date(self) -> None:
        from src.result_filters import _matches_date_from

        result = SearchResult("c1", "text", {"date": "2024-06-15T10:00:00", "uid": "u1"}, 0.1)
        assert _matches_date_from(result, "2024-01-01") is True

    def test_date_to_includes_valid_date(self) -> None:
        from src.result_filters import _matches_date_to

        result = SearchResult("c1", "text", {"date": "2024-06-15T10:00:00", "uid": "u1"}, 0.1)
        assert _matches_date_to(result, "2024-12-31") is True

    def test_date_from_no_filter_passes_none(self) -> None:
        from src.result_filters import _matches_date_from

        result = SearchResult("c1", "text", {"date": None, "uid": "u1"}, 0.1)
        assert _matches_date_from(result, None) is True
