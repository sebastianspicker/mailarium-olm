# ruff: noqa: F401
"""Extended tests for low-coverage MCP tool modules.

Tests cover: threads.py, reporting.py, temporal.py, data_quality.py,
browse.py, and scan.py. Each test mocks deps (retriever + email_db),
calls the async tool function, and asserts valid JSON with expected keys.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.config import get_settings
from src.mcp_server import _offload
from src.retriever import SearchResult
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────


def _make_result(
    uid="uid-1",
    text="Please review the budget proposal.",
    subject="Budget Review",
    sender="employee@example.test",
    date="2025-06-01",
    conversation_id="conv-1",
    distance=0.2,
):
    return SearchResult(
        chunk_id=f"chunk_{uid}",
        text=text,
        metadata={
            "uid": uid,
            "subject": subject,
            "sender_email": sender,
            "sender_name": sender.split("@")[0].title(),
            "date": date,
            "conversation_id": conversation_id,
        },
        distance=distance,
    )


class MockRetriever:
    """Retriever stub supporting the methods used by thread/browse tools."""

    def search_by_thread(self, conversation_id=None, top_k=50):
        return [
            _make_result(uid="uid-1", text="We decided to go with vendor A."),
            _make_result(uid="uid-2", text="Please send the updated report by Friday.", sender="bob@example.com"),
        ]

    def search_filtered(self, query="", top_k=10, **kwargs):
        return [_make_result()]

    def format_results_for_llm(self, results):
        return "formatted results"

    def serialize_results(self, query, results):
        return {"query": query, "count": len(results), "results": []}

    def list_senders(self, limit=30):
        return [{"name": "Alice", "email": "employee@example.test", "count": 10}]


class MockEmailDB:
    """Minimal email database stub with an in-memory SQLite connection."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE emails ("
            "uid TEXT PRIMARY KEY, subject TEXT, sender_email TEXT, "
            "sender_name TEXT, date TEXT, body_text TEXT, "
            "conversation_id TEXT, folder TEXT, forensic_body_text TEXT, "
            "forensic_body_source TEXT, "
            "normalized_body_source TEXT, "
            "body_kind TEXT, body_empty_reason TEXT, recovery_strategy TEXT, recovery_confidence REAL, "
            "in_reply_to TEXT, references_json TEXT, "
            "inferred_parent_uid TEXT, inferred_thread_id TEXT, "
            "inferred_match_reason TEXT, inferred_match_confidence REAL, "
            "detected_language TEXT, detected_language_confidence TEXT, "
            "detected_language_reason TEXT, detected_language_token_count INTEGER, "
            "detected_language_source TEXT, sentiment_label TEXT, sentiment_score REAL, "
            "ingestion_run_id TEXT)"
        )
        self.conn.execute(
            """INSERT INTO emails VALUES (
                'uid-1', 'Budget Review', 'employee@example.test', 'Alice',
                '2025-06-01', 'We decided to go with vendor A.', 'conv-1', 'Inbox',
                'Full forensic body for uid-1.', 'forensic_body_text', 'body_text',
                'content', '', '', 1.0, '', '[]', '', '', '', 0.0,
                'en', 'high', 'stopword_overlap', 8, 'forensic_body_text', 'positive', 0.85, 'run-1'
            )"""
        )
        self.conn.execute(
            """INSERT INTO emails VALUES (
                'uid-2', 'Budget Review', 'bob@example.com', 'Bob',
                '2025-06-02', 'Please send the updated report by Friday.', 'conv-1', 'Inbox',
                'Full forensic body for uid-2.', 'forensic_body_text',
                'body_text_html', 'content', '', '', 1.0,
                'budget-parent@example.com', '["budget-root@example.com", "budget-parent@example.com"]',
                'uid-1', 'conv-1', 'base_subject,participants', 0.91,
                'en', 'medium', 'stopword_overlap', 7, 'forensic_body_text', 'neutral', 0.50, 'run-1'
            )"""
        )
        self.conn.execute(
            "CREATE TABLE message_segments ("
            "email_uid TEXT, ordinal INTEGER, segment_type TEXT, depth INTEGER, "
            "text TEXT, source_surface TEXT, provenance_json TEXT)"
        )
        self.conn.execute(
            "CREATE TABLE attachments ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, email_uid TEXT, name TEXT, "
            "mime_type TEXT, size INTEGER, content_id TEXT, is_inline INTEGER)"
        )
        self.conn.execute(
            "INSERT INTO message_segments VALUES "
            "('uid-1', 0, 'authored_body', 0, 'We decided to go with vendor A.', 'body_text', '{}')"
        )
        self.conn.execute(
            "INSERT INTO message_segments VALUES "
            "('uid-1', 1, 'quoted_reply', 1, 'Can you send the updated report?', 'body_text', '{}')"
        )
        self.conn.execute(
            "INSERT INTO attachments (email_uid, name, mime_type, size, content_id, is_inline) VALUES "
            "('uid-1', 'budget.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 2048, '', 0)"
        )
        self.conn.commit()

    def get_email_full(self, uid):
        row = self.conn.execute("SELECT * FROM emails WHERE uid = ?", (uid,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_thread_emails(self, conversation_id):
        rows = self.conn.execute(
            "SELECT * FROM emails WHERE conversation_id = ? ORDER BY date",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_emails_paginated(
        self, offset=0, limit=10, folder=None, sender=None, category=None, sort_order="DESC", date_from=None, date_to=None
    ):
        return {
            "emails": [
                {"uid": "uid-1", "subject": "Budget Review", "sender_email": "employee@example.test", "date": "2025-06-01"},
            ],
            "total": 1,
            "offset": offset,
            "limit": limit,
        }

    def get_emails_full_batch(self, uids):
        result = {}
        for uid in uids:
            full = self.get_email_full(uid)
            if full:
                result[uid] = full
        return result

    def attachments_for_email(self, uid):
        rows = self.conn.execute(
            "SELECT name, mime_type, size, content_id, is_inline FROM attachments WHERE email_uid = ?",
            (uid,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_evidence(self, email_uid=None, limit=50):
        return {"items": []}

    def top_contacts(self, email, limit=5):
        return [{"email": "bob@example.com", "count": 5}]

    def category_counts(self):
        return [{"category": "Meeting", "count": 3}]

    def calendar_emails(self, date_from=None, date_to=None, limit=10):
        return [{"uid": "uid-1", "subject": "Calendar Invite", "date": "2025-06-01"}]

    def thread_by_topic(self, topic, limit=50):
        return [{"uid": "uid-1", "subject": "Budget Review", "date": "2025-06-01"}]

    def top_senders(self, limit=10):
        return [{"sender_email": "employee@example.test", "count": 10}]

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
    """Dependency injection for tool modules matching ToolDepsProto."""

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
    """Minimal MCP stub that captures tool registrations."""

    def __init__(self):
        self._tools = {}

    def tool(self, name=None, annotations=None):
        def decorator(fn):
            self._tools[name] = fn
            return fn

        return decorator


def _register_module(module):
    """Register a tool module with a FakeMCP and MockDeps, returning the FakeMCP."""
    fake_mcp = FakeMCP()
    module.register(fake_mcp, MockDeps)
    return fake_mcp
