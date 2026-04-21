# ruff: noqa: F401
"""Tests for src/tools/diagnostics.py — admin and diagnostic tools.

Covers: email_admin with action='diagnostics', 'reingest_bodies',
'reembed', 'reingest_metadata', 'reingest_analytics', and invalid actions.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.mcp_server import _offload
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────


class MockRetriever:
    """Minimal retriever stub with embedder attribute for diagnostics."""

    def __init__(self):
        self.embedder = MagicMock()
        self.embedder.device = "cpu"
        self.embedder._model = MagicMock()
        self.embedder.has_sparse = False
        self.embedder.has_colbert = False
        self.embedder.runtime_summary.return_value = {
            "backend": "fake",
            "device": "cpu",
            "batch_size": 16,
            "load_mode": "local_only",
            "has_sparse": False,
            "has_colbert": False,
        }


class MockEmailDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def sparse_vector_count(self):
        return 42

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class MockDeps:
    _retriever = MockRetriever()
    _email_db = MockEmailDB()

    @staticmethod
    def get_retriever():
        return MockDeps._retriever

    @staticmethod
    def get_email_db():
        return MockDeps._email_db

    offload = staticmethod(_offload)
    DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})
    sanitize = staticmethod(sanitize_untrusted_text)

    @staticmethod
    def tool_annotations(title):
        return {"title": title}

    @staticmethod
    def write_tool_annotations(title):
        return {"title": title}

    @staticmethod
    def idempotent_write_annotations(title):
        return {"title": title}


class FakeMCP:
    def __init__(self):
        self._tools = {}

    def tool(self, name=None, annotations=None):
        def decorator(fn):
            self._tools[name] = fn
            return fn

        return decorator


def _register():
    from src.tools import diagnostics

    fake_mcp = FakeMCP()
    diagnostics.register(fake_mcp, MockDeps)
    return fake_mcp
