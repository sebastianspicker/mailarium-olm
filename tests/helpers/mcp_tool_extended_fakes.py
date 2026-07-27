"""Fake MCP registration and in-memory dependencies for MCP tool tests."""

from __future__ import annotations

import sqlite3

from mailarium.retriever import SearchResult

from .diagnostics_fakes import SqliteConnectionOwner, ToolDependencyAnnotations

# ── Shared Test Infrastructure ───────────────────────────────


def _make_result(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    uid="uid-1",
    text="Please review the budget proposal.",
    subject="Budget Review",
    sender="employee@example.test",
    date="2025-06-01",
    conversation_id="conv-1",
    distance=0.2,
):
    """Build deterministic result data without external services."""
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


def close_sqlite_connection(owner) -> None:
    """Close the optional SQLite connection held by an in-memory test double."""
    if owner.conn is not None:
        owner.conn.close()
        owner.conn = None


class MockRetriever:
    """Retriever stub supporting the methods used by thread/browse tools."""

    def search_by_thread(self, conversation_id=None, top_k=50):
        """Implement the search by thread behavior exposed by the MockRetriever test double."""
        return [
            _make_result(uid="uid-1", text="We decided to go with vendor A."),
            _make_result(uid="uid-2", text="Please send the updated report by Friday.", sender="bob@example.com"),
        ]

    def search_filtered(self, query="", top_k=10, **kwargs):
        """Implement the search filtered behavior exposed by the MockRetriever test double."""
        return [_make_result()]

    def format_results_for_llm(self, results):
        """Implement the format results for llm behavior exposed by the MockRetriever test double."""
        return "formatted results"

    def serialize_results(self, query, results):
        """Implement the serialize results behavior exposed by the MockRetriever test double."""
        return {"query": query, "count": len(results), "results": []}

    def list_senders(self, limit=30):
        """Implement the list senders behavior exposed by the MockRetriever test double."""
        return [{"name": "Alice", "email": "employee@example.test", "count": 10}]


class MockEmailDB(SqliteConnectionOwner):
    """Minimal email database stub with an in-memory SQLite connection."""

    def __init__(self):
        """Implement the init behavior exposed by the MockEmailDB test double."""
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
        """Implement the get email full behavior exposed by the MockEmailDB test double."""
        row = self.conn.execute("SELECT * FROM emails WHERE uid = ?", (uid,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_thread_emails(self, conversation_id):
        """Implement the get thread emails behavior exposed by the MockEmailDB test double."""
        rows = self.conn.execute(
            "SELECT * FROM emails WHERE conversation_id = ? ORDER BY date",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_emails_paginated(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, offset=0, limit=10, folder=None, sender=None, category=None, sort_order="DESC", date_from=None, date_to=None
    ):
        """Implement the list emails paginated behavior exposed by the MockEmailDB test double."""
        return {
            "emails": [
                {"uid": "uid-1", "subject": "Budget Review", "sender_email": "employee@example.test", "date": "2025-06-01"},
            ],
            "total": 1,
            "offset": offset,
            "limit": limit,
        }

    def get_emails_full_batch(self, uids):
        """Implement the get emails full batch behavior exposed by the MockEmailDB test double."""
        result = {}
        for uid in uids:
            full = self.get_email_full(uid)
            if full:
                result[uid] = full
        return result

    def attachments_for_email(self, uid):
        """Implement the attachments for email behavior exposed by the MockEmailDB test double."""
        rows = self.conn.execute(
            "SELECT name, mime_type, size, content_id, is_inline FROM attachments WHERE email_uid = ?",
            (uid,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_evidence(self, email_uid=None, limit=50):
        """Implement the list evidence behavior exposed by the MockEmailDB test double."""
        return {"items": []}

    def top_contacts(self, email, limit=5):
        """Implement the top contacts behavior exposed by the MockEmailDB test double."""
        return [{"email": "bob@example.com", "count": 5}]

    def category_counts(self):
        """Implement the category counts behavior exposed by the MockEmailDB test double."""
        return [{"category": "Meeting", "count": 3}]

    def calendar_emails(self, date_from=None, date_to=None, limit=10):
        """Implement the calendar emails behavior exposed by the MockEmailDB test double."""
        return [{"uid": "uid-1", "subject": "Calendar Invite", "date": "2025-06-01"}]

    def thread_by_topic(self, topic, limit=50):
        """Implement the thread by topic behavior exposed by the MockEmailDB test double."""
        return [{"uid": "uid-1", "subject": "Budget Review", "date": "2025-06-01"}]

    def top_senders(self, limit=10):
        """Implement the top senders behavior exposed by the MockEmailDB test double."""
        return [{"sender_email": "employee@example.test", "count": 10}]


class MockDeps(ToolDependencyAnnotations):
    """Dependency injection for tool modules matching ToolDepsProto."""

    _retriever = MockRetriever()
    _email_db = MockEmailDB()

    @classmethod
    def get_retriever(cls):
        """Implement the get retriever behavior exposed by the MockDeps test double."""
        return cls._retriever

    @classmethod
    def get_email_db(cls):
        """Implement the get email db behavior exposed by the MockDeps test double."""
        return cls._email_db


class FakeMCP:
    """Minimal MCP stub that captures tool registrations."""

    def __init__(self):
        """Implement the init behavior exposed by the FakeMCP test double."""
        self._tools = {}

    def tool(self, name=None, annotations=None):
        """Implement the tool behavior exposed by the FakeMCP test double."""

        def decorator(fn):
            self._tools[name] = fn
            return fn

        return decorator


def _register_module(module):
    """Register a tool module with a FakeMCP and MockDeps, returning the FakeMCP."""
    fake_mcp = FakeMCP()
    module.register(fake_mcp, MockDeps)
    return fake_mcp


def _inferred_thread_dependencies():
    """Build retriever/database doubles for a canonical-missing inferred thread."""

    class InferredThreadRetriever(MockRetriever):
        def search_filtered(self, query="", top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-inferred-2",
                    text="Follow-up from the inferred-only thread.",
                    sender="bob@example.com",
                    date="2025-06-05",
                    conversation_id="",
                    distance=0.07,
                ),
                _make_result(
                    uid="uid-inferred-1",
                    text="Original inferred-only message.",
                    sender="employee@example.test",
                    date="2025-06-04",
                    conversation_id="",
                    distance=0.09,
                ),
            ]

    class InferredThreadDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-inferred-1": {
                    "uid": "uid-inferred-1",
                    "body_text": "Original inferred-only message.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                    "inferred_parent_uid": "",
                },
                "uid-inferred-2": {
                    "uid": "uid-inferred-2",
                    "body_text": "Follow-up from the inferred-only thread.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                    "inferred_parent_uid": "uid-inferred-1",
                    "inferred_match_reason": "base_subject,participants",
                    "inferred_match_confidence": 0.87,
                },
            }

        def get_inferred_thread_emails(self, inferred_thread_id):
            assert inferred_thread_id == "thread-inferred-1"
            return [
                {
                    "uid": "uid-inferred-1",
                    "subject": "Budget Review",
                    "sender_email": "employee@example.test",
                    "sender_name": "Alice",
                    "date": "2025-06-04",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                },
                {
                    "uid": "uid-inferred-2",
                    "subject": "Budget Review",
                    "sender_email": "bob@example.com",
                    "sender_name": "Bob",
                    "date": "2025-06-05",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                },
            ]

    return InferredThreadRetriever(), InferredThreadDB()


def _assert_strong_attachment_candidate(candidate, *, uid, filename):
    """Assert the stable evidence fields for a text-extracted attachment candidate."""
    assert candidate["uid"] == uid
    assert candidate["attachment"]["filename"] == filename
    assert candidate["attachment"]["size"] == 2048
    assert candidate["attachment"]["extraction_state"] == "text_extracted"
    assert candidate["attachment"]["text_available"] is True
    assert candidate["attachment"]["ocr_used"] is False
    assert candidate["attachment"]["failure_reason"] is None
    assert candidate["attachment"]["evidence_strength"] == "strong_text"
    assert candidate["attachment"]["is_inline"] is False
