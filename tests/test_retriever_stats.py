import pytest

from src.retriever import EmailRetriever, SearchResult


def _build_result(sender_email: str, sender_name: str, date: str) -> SearchResult:
    return SearchResult(
        chunk_id="id",
        text="body",
        metadata={
            "sender_email": sender_email,
            "sender_name": sender_name,
            "date": date,
            "folder": "Inbox",
            "uid": f"uid-{sender_email}-{date}",
        },
        distance=0.2,
    )


def test_search_filtered_combines_sender_and_date():
    retriever = EmailRetriever.__new__(EmailRetriever)

    def _search(query, top_k=10, where=None):
        return [
            _build_result("john@example.com", "John", "2023-05-05T10:00:00Z"),
            _build_result("jane@example.com", "Jane", "2023-05-05T10:00:00Z"),
            _build_result("john@example.com", "John", "2022-01-01T10:00:00Z"),
        ]

    retriever.search = _search

    results = retriever.search_filtered(
        query="budget",
        sender="john",
        date_from="2023-01-01",
        date_to="2023-12-31",
        top_k=10,
    )

    assert len(results) == 1
    assert results[0].metadata["sender_email"] == "john@example.com"


def test_stats_aggregates_paginated_metadata():
    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyCollection:
        def count(self):
            return 3

        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {
                            "uid": "1",
                            "sender_email": "a@example.com",
                            "date": "2023-01-01T00:00:00Z",
                            "folder": "Inbox",
                        },
                        {
                            "uid": "2",
                            "sender_email": "b@example.com",
                            "date": "2023-02-01T00:00:00Z",
                            "folder": "Inbox",
                        },
                    ]
                }
            if offset == 2:
                return {
                    "metadatas": [
                        {
                            "uid": "3",
                            "sender_email": "a@example.com",
                            "date": "2023-03-01T00:00:00Z",
                            "folder": "Archive",
                        }
                    ]
                }
            return {"metadatas": []}

    retriever.collection = DummyCollection()

    stats = retriever.stats()
    assert stats["total_chunks"] == 3
    assert stats["total_emails"] == 3
    assert stats["unique_senders"] == 2
    assert stats["date_range"]["earliest"] == "2023-01-01"
    assert stats["date_range"]["latest"] == "2023-03-01"
    assert stats["folders"]["Inbox"] == 2


def test_format_results_includes_untrusted_data_warning():
    retriever = EmailRetriever.__new__(EmailRetriever)
    result = _build_result("a@example.com", "Alice", "2023-01-01T00:00:00Z")

    output = retriever.format_results_for_llm([result])

    assert "untrusted email content" in output.lower()


def test_list_senders_counts_unique_emails_not_chunks():
    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyCollection:
        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {
                            "uid": "u1",
                            "sender_email": "a@example.com",
                            "sender_name": "Alice",
                        },
                        {
                            "uid": "u1",
                            "sender_email": "a@example.com",
                            "sender_name": "Alice",
                        },
                        {
                            "uid": "u2",
                            "sender_email": "b@example.com",
                            "sender_name": "Bob",
                        },
                    ]
                }
            return {"metadatas": []}

    retriever.collection = DummyCollection()
    senders = retriever.list_senders(limit=10)

    assert senders[0]["email"] == "a@example.com"
    assert senders[0]["count"] == 1


def test_list_senders_rejects_non_positive_limit():
    retriever = EmailRetriever.__new__(EmailRetriever)

    with pytest.raises(ValueError):
        retriever.list_senders(limit=0)


def test_list_senders_deduplicates_by_message_id_when_uid_missing():
    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyCollection:
        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {
                            "message_id": "m-1",
                            "sender_email": "a@example.com",
                            "sender_name": "Alice",
                        },
                        {
                            "message_id": "m-1",
                            "sender_email": "a@example.com",
                            "sender_name": "Alice",
                        },
                    ]
                }
            return {"metadatas": []}

    retriever.collection = DummyCollection()
    senders = retriever.list_senders(limit=10)

    assert len(senders) == 1
    assert senders[0]["email"] == "a@example.com"
    assert senders[0]["count"] == 1


def test_stats_counts_emails_without_uid_using_fallback_key():
    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyCollection:
        def count(self):
            return 3

        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {
                            "message_id": "m-1",
                            "sender_email": "a@example.com",
                            "date": "2023-01-01T00:00:00Z",
                            "folder": "Inbox",
                        },
                        {
                            "message_id": "m-1",
                            "sender_email": "a@example.com",
                            "date": "2023-01-01T00:00:00Z",
                            "folder": "Inbox",
                        },
                        {
                            "message_id": "m-2",
                            "sender_email": "b@example.com",
                            "date": "2023-02-01T00:00:00Z",
                            "folder": "Archive",
                        },
                    ]
                }
            return {"metadatas": []}

    retriever.collection = DummyCollection()
    stats = retriever.stats()

    assert stats["total_chunks"] == 3
    assert stats["total_emails"] == 2


def test_stats_folder_counts_deduplicate_chunk_rows():
    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyCollection:
        def count(self):
            return 3

        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {
                            "uid": "u-1",
                            "sender_email": "a@example.com",
                            "date": "2023-01-01T00:00:00Z",
                            "folder": "Inbox",
                        },
                        {
                            "uid": "u-1",
                            "sender_email": "a@example.com",
                            "date": "2023-01-01T00:00:00Z",
                            "folder": "Inbox",
                        },
                        {
                            "uid": "u-2",
                            "sender_email": "b@example.com",
                            "date": "2023-02-01T00:00:00Z",
                            "folder": "Archive",
                        },
                    ]
                }
            return {"metadatas": []}

    retriever.collection = DummyCollection()
    stats = retriever.stats()

    assert stats["folders"]["Inbox"] == 1
    assert stats["folders"]["Archive"] == 1


def test_stats_unique_senders_ignores_blank_and_trims():
    retriever = EmailRetriever.__new__(EmailRetriever)

    class DummyCollection:
        def count(self):
            return 3

        def get(self, include, limit, offset):
            if offset == 0:
                return {
                    "metadatas": [
                        {"uid": "1", "sender_email": " Employee@Example.TEST ", "folder": "Inbox"},
                        {"uid": "2", "sender_email": "employee@example.test", "folder": "Inbox"},
                        {"uid": "3", "sender_email": "   ", "folder": "Inbox"},
                    ]
                }
            return {"metadatas": []}

    retriever.collection = DummyCollection()
    stats = retriever.stats()

    assert stats["unique_senders"] == 1


def test_search_result_score_is_clamped_to_one():
    result = SearchResult(
        chunk_id="id",
        text="body",
        metadata={},
        distance=-0.25,
    )

    assert result.score == 1.0
