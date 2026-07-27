# ruff: noqa: I001
"""MCP answer-context thread grouping, graph output, and response packing behavior."""

from __future__ import annotations

import json

import pytest

from mailarium.config import get_settings

# ── Shared Test Infrastructure ───────────────────────────────

from .helpers.mcp_tool_extended_fakes import FakeMCP, MockDeps, MockRetriever, _inferred_thread_dependencies, _make_result


class TestSearchTools:
    @pytest.mark.asyncio
    async def test_email_answer_context_registered_adds_thread_graph(self):
        from mailarium.tools import search

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

            from mailarium.mcp_models import EmailAnswerContextInput

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
        from mailarium.tools import search

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        old_db = MockDeps._email_db
        MockDeps._retriever, MockDeps._email_db = _inferred_thread_dependencies()
        try:
            search.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_answer_context"]

            from mailarium.mcp_models import EmailAnswerContextInput

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
        from mailarium.tools import search

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

            from mailarium.mcp_models import EmailAnswerContextInput

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
