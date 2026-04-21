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
