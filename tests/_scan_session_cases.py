"""Shared fixtures and helpers for the RF11 scan-session test split."""

from __future__ import annotations

from contextlib import contextmanager

import pytest


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure scan sessions are clean between tests."""
    from mailarium.scan_session import _sessions

    _sessions.clear()
    yield
    _sessions.clear()


def make_search_result(uid: str = "x", text: str = "hello", distance: float = 0.25):
    from mailarium.retriever import SearchResult

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


@contextmanager
def configured_scan_retriever(monkeypatch, uids):
    """Install a deterministic scan retriever and clear cached settings around one test."""
    from mailarium import mcp_server
    from mailarium.config import get_settings

    get_settings.cache_clear()
    retriever = ScanRetriever([make_search_result(uid) for uid in uids])
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)
    try:
        yield retriever
    finally:
        get_settings.cache_clear()
