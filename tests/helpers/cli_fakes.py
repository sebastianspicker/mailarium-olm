# ruff: noqa: F401
"""Tests for CLI command handler functions (_cmd_* and helpers).

These tests exercise the uncovered handler logic in src/cli.py by:
- Constructing argparse.Namespace objects directly
- Mocking EmailRetriever and EmailDatabase
- Capturing stdout/stderr with capsys
- Verifying that the correct branches execute and produce output
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.cli import (
    _cmd_admin,
    _cmd_analytics,
    _cmd_browse,
    _cmd_evidence,
    _cmd_export,
    _cmd_search,
    _cmd_training,
    _interactive_action,
    _print_sender_lines,
    _render_interactive_intro,
    _render_results_table,
    _render_senders,
    _render_stats,
    _run_browse,
    _run_custody_chain,
    _run_dossier,
    _run_evidence_export,
    _run_evidence_list,
    _run_evidence_stats,
    _run_evidence_verify,
    _run_export_email,
    _run_export_thread,
    _run_fine_tune,
    _run_generate_training_data,
    _run_provenance,
    resolve_output_format,
    run_single_query,
)

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
        return min(1.0, max(0.0, 1.0 - self.distance))

    def to_context_string(self) -> str:
        subject = self.metadata.get("subject", "(no subject)")
        sender = self.metadata.get("sender_email", "?")
        return f"Subject: {subject}\nFrom: {sender}\n{self.text}"

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "score": self.score,
            "distance": self.distance,
            "metadata": self.metadata,
            "text": self.text,
        }


def _make_result(uid="uid-001", subject="Test Email", sender="employee@example.test", text="Hello world", distance=0.2):
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
