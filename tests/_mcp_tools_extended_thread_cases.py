# ruff: noqa: I001
"""MCP thread summaries, action items, decisions, and lookup behavior."""

from __future__ import annotations

import json

import pytest


# ── Shared Test Infrastructure ───────────────────────────────

from .helpers.mcp_tool_extended_fakes import FakeMCP, MockDeps, MockRetriever, _register_module


class TestThreadTools:
    @pytest.mark.asyncio
    async def test_thread_summary_returns_json(self):
        from mailarium.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_thread_summary"]

        from mailarium.mcp_models import ThreadSummaryInput

        params = ThreadSummaryInput(conversation_id="conv-1", max_sentences=3)
        result = await fn(params)
        data = json.loads(result)

        assert "conversation_id" in data
        assert "summary" in data
        assert data["conversation_id"] == "conv-1"

    @pytest.mark.asyncio
    async def test_thread_summary_no_results(self):
        from mailarium.tools import threads

        class EmptyRetriever(MockRetriever):
            def search_by_thread(self, conversation_id=None, top_k=50, **_unused):
                return []

        fake_mcp = FakeMCP()
        old_retriever = MockDeps._retriever
        MockDeps._retriever = EmptyRetriever()
        try:
            threads.register(fake_mcp, MockDeps)
            fn = fake_mcp._tools["email_thread_summary"]

            from mailarium.mcp_models import ThreadSummaryInput

            params = ThreadSummaryInput(conversation_id="nonexistent")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._retriever = old_retriever

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "input_name", "input_kwargs"),
        [
            ("email_action_items", "ActionItemsInput", {"conversation_id": "conv-1", "limit": 10}),
            ("email_action_items", "ActionItemsInput", {"days": 30, "limit": 10}),
            ("email_decisions", "DecisionsInput", {"conversation_id": "conv-1", "limit": 10}),
            ("email_decisions", "DecisionsInput", {"days": 30, "limit": 10}),
        ],
    )
    async def test_thread_item_queries(self, tool_name, input_name, input_kwargs):
        from mailarium import mcp_models
        from mailarium.tools import threads

        fn = _register_module(threads)._tools[tool_name]
        params = getattr(mcp_models, input_name)(**input_kwargs)
        data = json.loads(await fn(params))

        assert "count" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_action_items_no_params_returns_error(self):
        from mailarium.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_action_items"]

        from mailarium.mcp_models import ActionItemsInput

        params = ActionItemsInput(limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_decisions_no_params_returns_error(self):
        from mailarium.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_decisions"]

        from mailarium.mcp_models import DecisionsInput

        params = DecisionsInput(limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_thread_lookup_by_conversation_id(self):
        from mailarium.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_thread_lookup"]

        from mailarium.mcp_models import EmailThreadLookupInput

        params = EmailThreadLookupInput(conversation_id="conv-1")
        result = await fn(params)
        data = json.loads(result)
        assert "conversation_id" in data
        assert data["conversation_id"] == "conv-1"
        assert "count" in data

    @pytest.mark.asyncio
    async def test_thread_lookup_by_topic(self):
        from mailarium.tools import threads

        fake_mcp = _register_module(threads)
        fn = fake_mcp._tools["email_thread_lookup"]

        from mailarium.mcp_models import EmailThreadLookupInput

        params = EmailThreadLookupInput(thread_topic="Budget Review")
        result = await fn(params)
        data = json.loads(result)
        assert "thread_topic" in data
        assert "count" in data
