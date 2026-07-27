"""Fake retriever and search-result builders used by CLI behavior tests."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from unittest.mock import MagicMock

# ── Fake SearchResult ────────────────────────────────────────────────


@dataclass
class _FakeSearchResult:
    """Mimics retriever.SearchResult for testing."""

    chunk_id: str
    text: str
    metadata: dict
    distance: float

    @property
    def score(self) -> float:
        """Implement the score behavior exposed by the _FakeSearchResult test double."""
        return min(1.0, max(0.0, 1.0 - self.distance))

    def to_context_string(self) -> str:
        """Implement the to context string behavior exposed by the _FakeSearchResult test double."""
        subject = self.metadata.get("subject", "(no subject)")
        sender = self.metadata.get("sender_email", "?")
        return f"Subject: {subject}\nFrom: {sender}\n{self.text}"

    def to_dict(self) -> dict:
        """Implement the to dict behavior exposed by the _FakeSearchResult test double."""
        return {
            "chunk_id": self.chunk_id,
            "score": self.score,
            "distance": self.distance,
            "metadata": self.metadata,
            "text": self.text,
        }


def _make_result(uid="uid-001", subject="Test Email", sender="employee@example.test", text="Hello world", distance=0.2):
    """Build deterministic result data without external services."""
    return _FakeSearchResult(
        chunk_id=f"{uid}_0",
        text=text,
        metadata={
            "subject": subject,
            "sender_email": sender,
            "sender_name": sender.split("@")[0],
            "date": "2024-06-15T10:00:00",
            "uid": uid,
        },
        distance=distance,
    )


def _make_retriever(results=None, stats_data=None, senders=None):
    """Create a mock EmailRetriever."""
    retriever = MagicMock()
    retriever.search_filtered.return_value = results or []
    retriever.stats.return_value = stats_data or {
        "total_emails": 100,
        "total_chunks": 500,
        "unique_senders": 20,
        "date_range": {"earliest": "2023-01-01", "latest": "2024-12-31"},
    }
    retriever.list_senders.return_value = senders or [
        {"name": "Alice", "email": "employee@example.test", "count": 50},
        {"name": "Bob", "email": "bob@example.com", "count": 30},
    ]
    retriever.serialize_results.return_value = {
        "query": "test",
        "count": len(results or []),
        "results": [r.to_dict() for r in (results or [])],
    }
    return retriever


def _search_args(**overrides):
    """Build the complete search-command namespace with explicit overrides."""
    defaults = {
        "subcommand": "search",
        "log_level": None,
        "vector_index_path": None,
        "sqlite_path": None,
        "query": "test",
        "format": None,
        "json": False,
        "top_k": 10,
        "sender": None,
        "subject": None,
        "folder": None,
        "cc": None,
        "to": None,
        "bcc": None,
        "has_attachments": None,
        "priority": None,
        "email_type": None,
        "date_from": None,
        "date_to": None,
        "min_score": None,
        "rerank": False,
        "hybrid": False,
        "topic": None,
        "cluster_id": None,
        "expand_query": False,
    }
    unknown = sorted(set(overrides) - set(defaults))
    if unknown:
        raise TypeError(f"_search_args() got unexpected option(s): {', '.join(unknown)}")
    return argparse.Namespace(**(defaults | overrides))
