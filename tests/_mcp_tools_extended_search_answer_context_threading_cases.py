# ruff: noqa: F401,I001
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

from .helpers.mcp_tool_extended_fakes import FakeMCP, MockDeps, MockEmailDB, MockRetriever, _make_result, _register_module


class TestSearchTools:
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
                        sender="employee@example.test",
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
            assert (data["_packed"]["deduplicated"]["body_candidates"] + data["_packed"]["truncated"]["body_candidates"]) >= 1
            assert data["_packed"]["estimated_chars_after"] <= data["_packed"]["estimated_chars_before"]
            assert data["count"] <= 2
        finally:
            MockDeps._retriever = old_retriever
            get_settings.cache_clear()
