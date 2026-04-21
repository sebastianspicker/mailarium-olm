# ruff: noqa: F401
"""Targeted coverage tests for src/retriever.py uncovered lines.

Each test targets a specific branch or code path identified by coverage analysis.
All tests run without GPU, real models, or network access.
"""

import types
from unittest.mock import MagicMock, patch

import pytest

from src.retriever import EmailRetriever, SearchResult

# ── Helpers ────────────────────────────────────────────────────────


def _make_result(chunk_id="c1", text="body text", uid="u1", date="2024-01-01", distance=0.1, **extra_meta):
    meta = {"uid": uid, "date": date, **extra_meta}
    return SearchResult(chunk_id=chunk_id, text=text, metadata=meta, distance=distance)


def _bare_retriever(**attrs):
    """Create a retriever via __new__ with optional attribute overrides."""
    r = EmailRetriever.__new__(EmailRetriever)
    # Set common defaults that many methods expect
    r._email_db = None
    r._email_db_checked = True
    r.settings = None
    for k, v in attrs.items():
        setattr(r, k, v)
    return r
