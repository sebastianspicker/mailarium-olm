"""Shared fixtures and helpers for the RF11 scan-session test split."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure scan sessions are clean between tests."""
    from src.scan_session import _sessions

    _sessions.clear()
    yield
    _sessions.clear()


def make_search_result(uid: str = "x", text: str = "hello", distance: float = 0.25):
    from src.retriever import SearchResult

    return SearchResult(
        chunk_id=f"chunk_{uid}",
        text=text,
        metadata={"uid": uid, "subject": "Hi", "sender_email": "a@example.com"},
        distance=distance,
    )


class ScanRetriever:
    """Retriever that returns configurable results for scan testing."""

    def __init__(self, results):
        self._results = results
        self.captured_kwargs = {}

    def search_filtered(self, **kwargs):
        self.captured_kwargs = kwargs
        return list(self._results)

    def search(self, query, top_k=10):
        return list(self._results)

    def serialize_results(self, query, results):
        return {"query": query, "count": len(results), "results": []}

    def format_results_for_llm(self, results):
        return "formatted"

    def stats(self):
        return {"total_emails": 100, "date_range": {}, "unique_senders": 5}
