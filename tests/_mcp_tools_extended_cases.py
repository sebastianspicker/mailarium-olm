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
    sender="alice@example.com",
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
        return [{"name": "Alice", "email": "alice@example.com", "count": 10}]


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
            "detected_language TEXT, sentiment_label TEXT, sentiment_score REAL, "
            "ingestion_run_id TEXT)"
        )
        self.conn.execute(
            """INSERT INTO emails VALUES (
                'uid-1', 'Budget Review', 'alice@example.com', 'Alice',
                '2025-06-01', 'We decided to go with vendor A.', 'conv-1', 'Inbox',
                'Full forensic body for uid-1.', 'forensic_body_text', 'body_text',
                'content', '', '', 1.0, '', '[]', '', '', '', 0.0,
                'en', 'positive', 0.85, 'run-1'
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
                'en', 'neutral', 0.50, 'run-1'
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
                {"uid": "uid-1", "subject": "Budget Review", "sender_email": "alice@example.com", "date": "2025-06-01"},
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
        return [{"sender_email": "alice@example.com", "count": 10}]


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


# ── threads.py tests ─────────────────────────────────────────


class TestThreadTools:
    @pytest.mark.asyncio
    async def test_thread_summary_returns_json(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_thread_summary"]

        from src.mcp_models import ThreadSummaryInput

        params = ThreadSummaryInput(conversation_id="conv-1", max_sentences=3)
        result = await fn(params)
        data = json.loads(result)

        assert "conversation_id" in data
        assert "summary" in data
        assert data["conversation_id"] == "conv-1"

    @pytest.mark.asyncio
    async def test_thread_summary_no_results(self):
        from src.tools import threads

        class EmptyRetriever(MockRetriever):
            def search_by_thread(self, **kwargs):
                return []

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = EmptyRetriever()
        try:
            threads.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_thread_summary"]

            from src.mcp_models import ThreadSummaryInput

            params = ThreadSummaryInput(conversation_id="nonexistent")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_action_items_by_conversation(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_action_items"]

        from src.mcp_models import ActionItemsInput

        params = ActionItemsInput(conversation_id="conv-1", limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_action_items_by_days(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_action_items"]

        from src.mcp_models import ActionItemsInput

        params = ActionItemsInput(days=30, limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_action_items_no_params_returns_error(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_action_items"]

        from src.mcp_models import ActionItemsInput

        params = ActionItemsInput(limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_decisions_by_conversation(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_decisions"]

        from src.mcp_models import DecisionsInput

        params = DecisionsInput(conversation_id="conv-1", limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_decisions_by_days(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_decisions"]

        from src.mcp_models import DecisionsInput

        params = DecisionsInput(days=30, limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_decisions_no_params_returns_error(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_decisions"]

        from src.mcp_models import DecisionsInput

        params = DecisionsInput(limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_thread_lookup_by_conversation_id(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_thread_lookup"]

        from src.mcp_models import EmailThreadLookupInput

        params = EmailThreadLookupInput(conversation_id="conv-1")
        result = await fn(params)
        data = json.loads(result)
        assert "conversation_id" in data
        assert data["conversation_id"] == "conv-1"
        assert "count" in data

    @pytest.mark.asyncio
    async def test_thread_lookup_by_topic(self):
        from src.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_thread_lookup"]

        from src.mcp_models import EmailThreadLookupInput

        params = EmailThreadLookupInput(thread_topic="Budget Review")
        result = await fn(params)
        data = json.loads(result)
        assert "thread_topic" in data
        assert "count" in data


# ── search.py tests ──────────────────────────────────────────


class TestSearchTools:
    @pytest.mark.asyncio
    async def test_email_answer_context_registered_and_returns_candidates(self):
        from src.tools import search

        class SegmentMatchingRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [_make_result(uid="uid-1", text="We decided to go with vendor A.")]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = SegmentMatchingRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            params = EmailAnswerContextInput(question="What was decided?", max_results=2)
            result = await fn(params)
            data = json.loads(result)

            assert data["question"] == "What was decided?"
            assert data["count"] == 1
            assert data["candidates"][0]["uid"] == "uid-1"
            assert data["candidates"][0]["follow_up"]["uid"] == "uid-1"
            assert data["evidence_mode"]["requested"] == "retrieval"
            assert data["candidates"][0]["body_render_mode"] == "retrieval"
            assert data["candidates"][0]["body_render_source"] == "body_text"
            assert data["candidates"][0]["verification_status"] == "retrieval"
            assert data["candidates"][0]["provenance"]["uid"] == "uid-1"
            assert data["candidates"][0]["provenance"]["segment_ordinal"] == 0
            assert data["candidates"][0]["provenance"]["snippet_start"] == 0
            assert data["candidates"][0]["provenance"]["snippet_end"] == 31
            assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-1:retrieval:body_text:0:31:0")
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_forensic_mode_uses_forensic_render(self):
        from src.tools import search

        class ForensicDB(MockEmailDB):
            def __init__(self):
                super().__init__()
                self.conn.execute(
                    "UPDATE emails SET forensic_body_text = ?, forensic_body_source = ? WHERE uid = ?",
                    ("Quoted header\nWe decided to go with vendor A.\nRegards", "raw_body_html", "uid-1"),
                )
                self.conn.commit()

        class SegmentMatchingRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [_make_result(uid="uid-1", text="We decided to go with vendor A.")]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        old_db = MockDeps._email_db
        MockDeps._retriever = SegmentMatchingRetriever()
        MockDeps._email_db = ForensicDB()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            params = EmailAnswerContextInput(question="What was decided?", evidence_mode="forensic")
            result = await fn(params)
            data = json.loads(result)

            assert data["evidence_mode"]["requested"] == "forensic"
            assert data["candidates"][0]["body_render_mode"] == "forensic"
            assert data["candidates"][0]["body_render_source"] == "raw_body_html"
            assert data["candidates"][0]["verification_status"] == "forensic_exact"
            assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-1:forensic:raw_body_html:")
        finally:
            MockDeps._retriever = old_retriever
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_handles_empty_results(self):
        from src.tools import search

        class EmptyRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return []

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = EmptyRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            params = EmailAnswerContextInput(question="Did anyone mention the maintenance window?")
            result = await fn(params)
            data = json.loads(result)

            assert data["count"] == 0
            assert data["candidates"] == []
            assert data["attachment_candidates"] == []
            assert data["conversation_groups"] == []
            assert "message" in data
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_separates_attachment_candidates(self):
        from src.tools import search

        class AttachmentRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    SearchResult(
                        chunk_id="uid-1__att_budget__0",
                        text='[Attachment: budget.xlsx from email "Budget Review" (2025-06-01)]\n\nBudget totals are attached.',
                        metadata={
                            "uid": "uid-1",
                            "subject": "Budget Review",
                            "sender_email": "alice@example.com",
                            "sender_name": "Alice",
                            "date": "2025-06-01",
                            "conversation_id": "conv-1",
                            "is_attachment": "True",
                            "parent_uid": "uid-1",
                            "attachment_filename": "budget.xlsx",
                        },
                        distance=0.12,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = AttachmentRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What is in the budget spreadsheet?"))
            data = json.loads(result)

            assert data["count"] == 1
            assert data["counts"] == {"body": 0, "attachments": 1, "total": 1}
            assert data["candidates"] == []
            assert len(data["attachment_candidates"]) == 1
            candidate = data["attachment_candidates"][0]
            assert candidate["uid"] == "uid-1"
            assert candidate["attachment"]["filename"] == "budget.xlsx"
            assert candidate["attachment"]["mime_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            assert candidate["attachment"]["size"] == 2048
            assert candidate["attachment"]["extraction_state"] == "text_extracted"
            assert candidate["attachment"]["text_available"] is True
            assert candidate["attachment"]["ocr_used"] is False
            assert candidate["attachment"]["failure_reason"] is None
            assert candidate["attachment"]["evidence_strength"] == "strong_text"
            assert candidate["attachment"]["is_inline"] is False
            assert candidate["follow_up"]["uid"] == "uid-1"
            assert candidate["provenance"]["evidence_handle"].startswith("attachment:uid-1:budget.xlsx:")
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_surfaces_ocr_attachment_state(self):
        from src.tools import search

        class OCRAttachmentRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    SearchResult(
                        chunk_id="uid-ocr-1__img_scan__0",
                        text='[Attachment: invoice-scan.png from email "Invoice" (2025-06-01)]\n\nInvoice total 120 EUR.',
                        metadata={
                            "uid": "uid-ocr-1",
                            "subject": "Invoice",
                            "sender_email": "alice@example.com",
                            "sender_name": "Alice",
                            "date": "2025-06-01",
                            "conversation_id": "",
                            "is_attachment": "True",
                            "attachment_filename": "invoice-scan.png",
                            "extraction_state": "ocr_text_extracted",
                        },
                        distance=0.12,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = OCRAttachmentRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What does the invoice scan say?"))
            data = json.loads(result)

            candidate = data["attachment_candidates"][0]
            assert candidate["attachment"]["extraction_state"] == "ocr_text_extracted"
            assert candidate["attachment"]["text_available"] is True
            assert candidate["attachment"]["ocr_used"] is True
            assert candidate["attachment"]["failure_reason"] is None
            assert candidate["attachment"]["evidence_strength"] == "strong_text"
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_conversation_groups(self):
        from src.tools import search

        class ThreadedRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-2",
                        text="Please send the updated report by Friday.",
                        sender="bob@example.com",
                        date="2025-06-02",
                        conversation_id="conv-1",
                        distance=0.12,
                    ),
                    _make_result(
                        uid="uid-1",
                        text="We decided to go with vendor A.",
                        sender="alice@example.com",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.2,
                    ),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = ThreadedRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What happened in the budget thread?", max_results=2))
            data = json.loads(result)

            assert len(data["conversation_groups"]) == 1
            group = data["conversation_groups"][0]
            assert group["conversation_id"] == "conv-1"
            assert group["top_uid"] == "uid-2"
            assert group["message_count"] == 2
            assert group["participants"] == ["alice@example.com", "bob@example.com"]
            assert group["date_range"] == {"first": "2025-06-01", "last": "2025-06-02"}
            assert group["matched_uids"] == ["uid-2", "uid-1"]
            assert data["candidates"][0]["conversation_context"]["conversation_id"] == "conv-1"
            assert data["candidates"][0]["conversation_context"]["message_count"] == 2
            assert data["candidates"][0]["conversation_context"]["top_uid"] == "uid-2"
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_reports_ambiguity(self):
        from src.tools import search

        class AmbiguousRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-1",
                        text="We decided to go with vendor A.",
                        sender="alice@example.com",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.10,
                    ),
                    _make_result(
                        uid="uid-2",
                        text="Please send the updated report by Friday.",
                        sender="bob@example.com",
                        date="2025-06-02",
                        conversation_id="conv-2",
                        distance=0.11,
                    ),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = AmbiguousRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="Which result is best?", max_results=2))
            data = json.loads(result)

            assert data["answer_quality"]["confidence_label"] == "ambiguous"
            assert data["answer_quality"]["ambiguity_reason"] == "close_top_scores"
            assert data["answer_quality"]["top_candidate_uid"] == "uid-1"
            assert data["answer_quality"]["alternative_candidates"] == ["uid-2"]
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_timeline(self):
        from src.tools import search

        class TemporalRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-2",
                        text="Decision made on the rollout.",
                        sender="bob@example.com",
                        date="2025-06-03",
                        conversation_id="conv-1",
                        distance=0.09,
                    ),
                    _make_result(
                        uid="uid-1",
                        text="Initial request for the rollout.",
                        sender="alice@example.com",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.12,
                    ),
                    _make_result(
                        uid="uid-3",
                        text="Follow-up confirmation after rollout.",
                        sender="carol@example.com",
                        date="2025-06-05",
                        conversation_id="conv-1",
                        distance=0.15,
                    ),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        old_db = MockDeps._email_db
        MockDeps._retriever = TemporalRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="How did the rollout evolve?", max_results=3))
            data = json.loads(result)

            assert data["timeline"]["event_count"] == 3
            assert data["timeline"]["date_range"] == {"first": "2025-06-01", "last": "2025-06-05"}
            assert data["timeline"]["first_uid"] == "uid-1"
            assert data["timeline"]["last_uid"] == "uid-3"
            assert data["timeline"]["key_transition_uid"] == "uid-2"
            assert [event["uid"] for event in data["timeline"]["events"]] == ["uid-1", "uid-2", "uid-3"]
        finally:
            MockDeps._retriever = old_retriever
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_speaker_attribution(self):
        from src.tools import search

        class SpeakerRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-1",
                        text="We decided to go with vendor A.",
                        sender="alice@example.com",
                        date="2025-06-01",
                        conversation_id="conv-1",
                        distance=0.09,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = SpeakerRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="Who said what about the vendor?", max_results=1))
            data = json.loads(result)

            attribution = data["candidates"][0]["speaker_attribution"]
            assert attribution["authored_speaker"]["email"] == "alice@example.com"
            assert attribution["quoted_blocks"][0]["speaker_email"] == "bob@example.com"
            assert attribution["quoted_blocks"][0]["source"] == "conversation_participant_exclusion"
            assert attribution["quoted_blocks"][0]["confidence"] == pytest.approx(0.5)
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_thread_graph(self):
        from src.tools import search

        class ThreadGraphRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(
                        uid="uid-2",
                        text="Please send the updated report by Friday.",
                        sender="bob@example.com",
                        date="2025-06-02",
                        conversation_id="conv-1",
                        distance=0.09,
                    )
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = ThreadGraphRetriever()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="How is this thread linked?", max_results=1))
            data = json.loads(result)

            graph = data["candidates"][0]["thread_graph"]
            assert graph["canonical"]["conversation_id"] == "conv-1"
            assert graph["canonical"]["in_reply_to"] == "budget-parent@example.com"
            assert graph["canonical"]["references"] == ["budget-root@example.com", "budget-parent@example.com"]
            assert graph["inferred"]["parent_uid"] == "uid-1"
            assert graph["inferred"]["thread_id"] == "conv-1"
            assert graph["inferred"]["reason"] == "base_subject,participants"
            assert graph["inferred"]["confidence"] == pytest.approx(0.91)
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_groups_by_inferred_thread_when_canonical_missing(self):
        from src.tools import search

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
                        sender="alice@example.com",
                        date="2025-06-04",
                        conversation_id="",
                        distance=0.09,
                    ),
                ]

        class InferredThreadDB:
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
                        "sender_email": "alice@example.com",
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

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        old_db = MockDeps._email_db
        MockDeps._retriever = InferredThreadRetriever()
        MockDeps._email_db = InferredThreadDB()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="What happened in the inferred thread?", max_results=2))
            data = json.loads(result)

            group = data["conversation_groups"][0]
            assert group["conversation_id"] == ""
            assert group["inferred_thread_id"] == "thread-inferred-1"
            assert group["thread_group_id"] == "thread-inferred-1"
            assert group["thread_group_source"] == "inferred"
            assert data["candidates"][0]["conversation_context"]["thread_group_source"] == "inferred"
            assert data["answer_quality"]["top_thread_group_id"] == "thread-inferred-1"
            assert data["answer_quality"]["top_thread_group_source"] == "inferred"
        finally:
            MockDeps._retriever = old_retriever
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_email_answer_context_registered_reports_packing(self, monkeypatch):
        from src.tools import search

        class PackedRetriever(MockRetriever):
            def search_filtered(self, query="", top_k=10, **kwargs):
                return [
                    _make_result(uid="uid-1", text="A" * 220, distance=0.05, conversation_id="conv-1", date="2025-06-01"),
                    _make_result(
                        uid="uid-2",
                        text="B" * 220,
                        sender="bob@example.com",
                        distance=0.07,
                        conversation_id="conv-1",
                        date="2025-06-02",
                    ),
                    _make_result(uid="uid-1", text="A" * 220, distance=0.08, conversation_id="conv-1", date="2025-06-01"),
                ]

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = PackedRetriever()
        monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "2600")
        get_settings.cache_clear()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from src.mcp_models import EmailAnswerContextInput

            result = await fn(EmailAnswerContextInput(question="Summarize the budget thread compactly.", max_results=3))
            data = json.loads(result)

            assert "_packed" in data
            assert data["_packed"]["applied"] is True
            assert data["_packed"]["deduplicated"]["body_candidates"] >= 1
            assert data["_packed"]["estimated_chars_after"] <= data["_packed"]["estimated_chars_before"]
            assert data["count"] <= 2
        finally:
            MockDeps._retriever = old_retriever
            get_settings.cache_clear()


# ── reporting.py tests ───────────────────────────────────────


class TestReportingTools:
    @pytest.mark.asyncio
    async def test_writing_analysis_single_sender(self):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="writing", sender="alice@example.com", limit=10)
        result = await fn(params)
        data = json.loads(result)

        # Either returns a profile or an error (no emails long enough)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_writing_analysis_no_sender_compares_top(self):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="writing", limit=5)
        result = await fn(params)
        data = json.loads(result)
        # Returns list of profiles or error
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_archive_report(self, tmp_path):
        from src.tools import reporting

        fake_mcp = _register_module(reporting)
        fn = fake_mcp._tools["email_report"]

        output_file = str(tmp_path / "report.html")

        from src.mcp_models import EmailReportInput

        params = EmailReportInput(type="archive", output_path=output_file)

        # Mock ReportGenerator since it requires full DB setup
        with patch("src.report_generator.ReportGenerator") as mock_gen_cls:
            mock_gen = MagicMock()
            mock_gen_cls.return_value = mock_gen
            result = await fn(params)
            data = json.loads(result)
            assert data.get("status") == "ok"
            assert data.get("output_path") == output_file

    @pytest.mark.asyncio
    async def test_invalid_report_type(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailReportInput

        with pytest.raises(ValidationError, match="type"):
            EmailReportInput(type="invalid_type")


# ── temporal.py tests ────────────────────────────────────────


class TestTemporalTools:
    @pytest.mark.asyncio
    async def test_volume_analysis(self):
        from src.tools import temporal

        fake_mcp = _register_module(temporal)
        fn = fake_mcp._tools["email_temporal"]

        from src.mcp_models import EmailTemporalInput

        with patch("src.temporal_analysis.TemporalAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.volume_over_time.return_value = [
                {"period": "2025-06-01", "count": 5},
                {"period": "2025-06-02", "count": 3},
            ]
            mock_cls.return_value = mock_analyzer

            params = EmailTemporalInput(analysis="volume", period="day")
            result = await fn(params)
            data = json.loads(result)

            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["period"] == "2025-06-01"

    @pytest.mark.asyncio
    async def test_activity_heatmap(self):
        from src.tools import temporal

        fake_mcp = _register_module(temporal)
        fn = fake_mcp._tools["email_temporal"]

        from src.mcp_models import EmailTemporalInput

        with patch("src.temporal_analysis.TemporalAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.activity_heatmap.return_value = {
                "Monday": {9: 5, 10: 3},
                "Tuesday": {14: 7},
            }
            mock_cls.return_value = mock_analyzer

            params = EmailTemporalInput(analysis="activity")
            result = await fn(params)
            data = json.loads(result)

            assert "Monday" in data
            assert "Tuesday" in data

    @pytest.mark.asyncio
    async def test_response_times(self):
        from src.tools import temporal

        fake_mcp = _register_module(temporal)
        fn = fake_mcp._tools["email_temporal"]

        from src.mcp_models import EmailTemporalInput

        with patch("src.temporal_analysis.TemporalAnalyzer") as mock_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.response_times.return_value = [
                {"sender": "alice@example.com", "avg_hours": 2.5},
            ]
            mock_cls.return_value = mock_analyzer

            params = EmailTemporalInput(analysis="response_times", limit=10)
            result = await fn(params)
            data = json.loads(result)

            assert isinstance(data, list)
            assert data[0]["sender"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_invalid_analysis_type(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailTemporalInput

        with pytest.raises(ValidationError, match="analysis"):
            EmailTemporalInput(analysis="invalid")


# ── data_quality.py tests ────────────────────────────────────


class TestDataQualityTools:
    @pytest.mark.asyncio
    async def test_language_stats(self):
        from src.tools import data_quality

        fake_mcp = _register_module(data_quality)
        fn = fake_mcp._tools["email_quality"]

        from src.mcp_models import EmailQualityInput

        params = EmailQualityInput(check="languages")
        result = await fn(params)
        data = json.loads(result)

        assert "languages" in data
        assert len(data["languages"]) > 0
        assert data["languages"][0]["language"] == "en"

    @pytest.mark.asyncio
    async def test_sentiment_overview(self):
        from src.tools import data_quality

        fake_mcp = _register_module(data_quality)
        fn = fake_mcp._tools["email_quality"]

        from src.mcp_models import EmailQualityInput

        params = EmailQualityInput(check="sentiment")
        result = await fn(params)
        data = json.loads(result)

        assert "sentiments" in data
        assert len(data["sentiments"]) > 0

    @pytest.mark.asyncio
    async def test_duplicate_detection(self):
        from src.tools import data_quality

        fake_mcp = _register_module(data_quality)
        fn = fake_mcp._tools["email_quality"]

        from src.mcp_models import EmailQualityInput

        with patch("src.dedup_detector.DuplicateDetector") as mock_cls:
            mock_detector = MagicMock()
            mock_detector.find_duplicates.return_value = [{"uid_a": "uid-1", "uid_b": "uid-2", "similarity": 0.92}]
            mock_cls.return_value = mock_detector

            params = EmailQualityInput(check="duplicates", threshold=0.85, limit=50)
            result = await fn(params)
            data = json.loads(result)

            assert "count" in data
            assert "duplicates" in data
            assert data["count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_check_type(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailQualityInput

        with pytest.raises(ValidationError, match="check"):
            EmailQualityInput(check="nonexistent")

    @pytest.mark.asyncio
    async def test_languages_missing_column_graceful(self):
        """When the column doesn't exist, the tool returns an instructive error."""
        from src.tools import data_quality

        class NoDB:
            """Stub DB whose conn raises OperationalError on any query."""

            class conn:
                @staticmethod
                def execute(*args):
                    raise sqlite3.OperationalError("no such column: detected_language")

        old_db = MockDeps._email_db
        MockDeps._email_db = NoDB()
        try:
            fake_mcp = _register_module(data_quality)
            fn = fake_mcp._tools["email_quality"]

            from src.mcp_models import EmailQualityInput

            params = EmailQualityInput(check="languages")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
            assert "reingest" in data["error"].lower() or "language" in data["error"].lower()
        finally:
            MockDeps._email_db = old_db


# ── browse.py tests ──────────────────────────────────────────


class TestBrowseTools:
    @pytest.mark.asyncio
    async def test_email_browse_default(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert "emails" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_email_browse_list_categories(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(list_categories=True)
        result = await fn(params)
        data = json.loads(result)

        assert "categories" in data

    @pytest.mark.asyncio
    async def test_email_browse_calendar(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(is_calendar=True, limit=5)
        result = await fn(params)
        data = json.loads(result)

        assert "emails" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_email_browse_forensic_body_mode(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(limit=10, include_body=True, render_mode="forensic")
        result = await fn(params)
        data = json.loads(result)

        assert data["emails"][0]["body_text"] == "Full forensic body for uid-1."
        assert data["emails"][0]["body_render_mode"] == "forensic"

    @pytest.mark.asyncio
    async def test_email_browse_include_body_surfaces_weak_message(self):
        from src.tools import browse

        try:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = 'source_shell_only',
                       recovery_strategy = 'source_shell_summary',
                       recovery_confidence = 0.2
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

            fake_mcp = _register_module(browse)
            fn = fake_mcp._tools["email_browse"]

            from src.mcp_models import BrowseInput

            params = BrowseInput(limit=10, include_body=True)
            result = await fn(params)
            data = json.loads(result)

            weak_message = data["emails"][0]["weak_message"]
            assert weak_message["code"] == "source_shell_only"
            assert weak_message["label"] == "Source-shell message"
        finally:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = '',
                       recovery_strategy = '',
                       recovery_confidence = 1.0
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

    @pytest.mark.asyncio
    async def test_email_deep_context_basic(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(
            uid="uid-1",
            include_thread=True,
            include_evidence=True,
            include_sender_stats=True,
        )
        result = await fn(params)
        data = json.loads(result)

        assert "email" in data
        assert data["email"]["uid"] == "uid-1"
        assert "thread" in data
        assert "evidence" in data
        assert "sender" in data

    @pytest.mark.asyncio
    async def test_email_deep_context_surfaces_weak_message(self):
        from src.tools import browse

        try:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = 'metadata_only_reply',
                       recovery_strategy = 'metadata_summary',
                       recovery_confidence = 0.2
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

            fake_mcp = _register_module(browse)
            fn = fake_mcp._tools["email_deep_context"]

            from src.mcp_models import EmailDeepContextInput

            result = await fn(EmailDeepContextInput(uid="uid-1"))
            data = json.loads(result)

            weak_message = data["email"]["weak_message"]
            assert weak_message["code"] == "metadata_only_reply"
            assert weak_message["label"] == "Metadata-only reply"
        finally:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = '',
                       recovery_strategy = '',
                       recovery_confidence = 1.0
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

    @pytest.mark.asyncio
    async def test_email_deep_context_not_found(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(uid="nonexistent-uid")
        result = await fn(params)
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_email_deep_context_no_thread(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(
            uid="uid-1",
            include_thread=False,
            include_evidence=False,
            include_sender_stats=False,
        )
        result = await fn(params)
        data = json.loads(result)

        assert "email" in data
        assert "thread" not in data
        assert "evidence" not in data
        assert "sender" not in data

    @pytest.mark.asyncio
    async def test_email_deep_context_conversation_debug(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(
            uid="uid-2",
            include_thread=False,
            include_evidence=False,
            include_sender_stats=False,
            include_conversation_debug=True,
            render_mode="forensic",
        )
        result = await fn(params)
        data = json.loads(result)

        assert data["email"]["body_text"] == "Full forensic body for uid-2."
        assert data["email"]["body_render_mode"] == "forensic"
        assert "conversation_debug" in data
        assert data["conversation_debug"]["segment_count"] == 0
        assert data["conversation_debug"]["canonical_thread"]["conversation_id"] == "conv-1"
        assert data["conversation_debug"]["canonical_thread"]["in_reply_to"] == "budget-parent@example.com"
        assert data["conversation_debug"]["canonical_thread"]["references"] == [
            "budget-root@example.com",
            "budget-parent@example.com",
        ]
        assert data["conversation_debug"]["inferred_thread"]["parent_uid"] == "uid-1"

    @pytest.mark.asyncio
    async def test_email_export_single_html(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        with patch("src.email_exporter.EmailExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_single_html.return_value = {
                "html": "<html>email</html>",
                "uid": "uid-1",
            }
            mock_cls.return_value = mock_exporter

            params = EmailExportInput(uid="uid-1")
            result = await fn(params)
            data = json.loads(result)

            assert "uid" in data or "html" in data

    @pytest.mark.asyncio
    async def test_email_export_forensic_mode(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        with patch("src.email_exporter.EmailExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_single_html.return_value = {
                "html": "<html>forensic</html>",
                "uid": "uid-1",
                "render_mode": "forensic",
            }
            mock_cls.return_value = mock_exporter

            params = EmailExportInput(uid="uid-1", render_mode="forensic")
            result = await fn(params)
            data = json.loads(result)

            mock_exporter.export_single_html.assert_called_once_with("uid-1", render_mode="forensic")
            assert data["render_mode"] == "forensic"

    @pytest.mark.asyncio
    async def test_email_export_thread_html(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        with patch("src.email_exporter.EmailExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_thread_html.return_value = {
                "html": "<html>thread</html>",
                "conversation_id": "conv-1",
                "email_count": 2,
            }
            mock_cls.return_value = mock_exporter

            params = EmailExportInput(conversation_id="conv-1")
            result = await fn(params)
            data = json.loads(result)

            assert "conversation_id" in data or "html" in data


# ── scan.py tests ────────────────────────────────────────────


class TestScanTools:
    def setup_method(self):
        """Reset scan sessions between tests."""
        from src import scan_session

        scan_session.reset_all_sessions()

    @pytest.mark.asyncio
    async def test_scan_flag_and_status(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Flag some candidates
        params = EmailScanInput(
            action="flag",
            scan_id="test_case",
            uids=["uid-1", "uid-2"],
            label="relevant",
            phase=1,
        )
        result = await fn(params)
        data = json.loads(result)

        assert data["flagged"] == 2
        assert data["total_candidates"] == 2
        assert data["scan_id"] == "test_case"

        # Check status
        params = EmailScanInput(action="status", scan_id="test_case")
        result = await fn(params)
        data = json.loads(result)

        assert data["scan_id"] == "test_case"
        assert data["candidate_count"] == 2
        assert data["seen_count"] >= 2

    @pytest.mark.asyncio
    async def test_scan_candidates(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Flag first
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="case2",
                uids=["uid-a", "uid-b"],
                label="bossing",
                phase=1,
            )
        )

        # Get candidates
        params = EmailScanInput(action="candidates", scan_id="case2")
        result = await fn(params)
        data = json.loads(result)

        assert "candidates" in data
        assert data["count"] == 2
        assert all(c["label"] == "bossing" for c in data["candidates"])

    @pytest.mark.asyncio
    async def test_scan_candidates_filtered_by_label(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        await fn(
            EmailScanInput(
                action="flag",
                scan_id="case3",
                uids=["uid-1"],
                label="bossing",
                phase=1,
            )
        )
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="case3",
                uids=["uid-2"],
                label="harassment",
                phase=2,
            )
        )

        # Filter by label
        params = EmailScanInput(
            action="candidates",
            scan_id="case3",
            label="bossing",
        )
        result = await fn(params)
        data = json.loads(result)

        assert data["count"] == 1
        assert data["candidates"][0]["label"] == "bossing"

    @pytest.mark.asyncio
    async def test_scan_reset(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Create a session
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="reset_test",
                uids=["uid-1"],
                label="test",
                phase=1,
            )
        )

        # Reset it
        params = EmailScanInput(action="reset", scan_id="reset_test")
        result = await fn(params)
        data = json.loads(result)

        assert data["reset"] == "reset_test"
        assert data["existed"] is True

        # Status should fail now
        params = EmailScanInput(action="status", scan_id="reset_test")
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_scan_reset_all(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Create sessions
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="s1",
                uids=["uid-1"],
                label="test",
                phase=1,
            )
        )
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="s2",
                uids=["uid-2"],
                label="test",
                phase=1,
            )
        )

        # Reset all
        params = EmailScanInput(action="reset", scan_id="__all__")
        result = await fn(params)
        data = json.loads(result)

        assert data["reset"] == "all"
        assert data["sessions_cleared"] >= 2

    @pytest.mark.asyncio
    async def test_scan_flag_missing_uids(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        params = EmailScanInput(
            action="flag",
            scan_id="test",
            label="test",
        )
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_scan_flag_missing_label(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        params = EmailScanInput(
            action="flag",
            scan_id="test",
            uids=["uid-1"],
        )
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    def test_scan_invalid_action(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailScanInput

        # Literal validation rejects invalid actions at parse time
        with pytest.raises(ValidationError, match="action"):
            EmailScanInput(action="destroy", scan_id="test")
