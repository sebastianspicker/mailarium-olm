"""Exercises semantic topic and cluster filters when backing metadata lookups fail.

It distinguishes an empty resolved filter from a resolution error in search diagnostics.
"""

from __future__ import annotations

from mailarium.retriever import EmailRetriever


class _FailingTopicDB:
    def emails_by_topic(self, topic_id: int, *, limit: int):
        raise RuntimeError(f"topic lookup failed: {topic_id}:{limit}")


class _FailingClusterDB:
    def emails_in_cluster(self, cluster_id: int, *, limit: int):
        raise RuntimeError(f"cluster lookup failed: {cluster_id}:{limit}")


class _EmptyTopicDB:
    def emails_by_topic(self, topic_id: int, *, limit: int):
        return []


def _bare_retriever(email_db) -> EmailRetriever:
    retriever = EmailRetriever.__new__(EmailRetriever)
    retriever._email_db = email_db
    retriever._email_db_checked = True
    return retriever


def test_topic_filter_db_failure_is_visible_in_search_debug() -> None:
    retriever = _bare_retriever(_FailingTopicDB())

    results = retriever.search_filtered(query="budget", topic_id=7)

    assert results == []
    assert retriever.last_search_debug["semantic_filter_status"] == "error"
    assert retriever.last_search_debug["semantic_filter_errors"][0]["filter"] == "topic_id"
    assert retriever.last_search_debug["semantic_filter_errors"][0]["error_type"] == "RuntimeError"


def test_cluster_filter_db_failure_is_visible_in_search_debug() -> None:
    retriever = _bare_retriever(_FailingClusterDB())

    results = retriever.search_filtered(query="budget", cluster_id=3)

    assert results == []
    assert retriever.last_search_debug["semantic_filter_status"] == "error"
    assert retriever.last_search_debug["semantic_filter_errors"][0]["filter"] == "cluster_id"


def test_empty_topic_filter_remains_distinct_from_resolution_failure() -> None:
    retriever = _bare_retriever(_EmptyTopicDB())

    results = retriever.search_filtered(query="budget", topic_id=99)

    assert results == []
    assert retriever.last_search_debug["semantic_filter_status"] == "empty"
    assert retriever.last_search_debug["semantic_filter_errors"] == []
    assert retriever.last_search_debug["semantic_filter_uid_count"] == 0
