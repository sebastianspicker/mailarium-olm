"""Tests for src/tools/entities.py — covers all four tool handlers (lines 22, 28, 34, 52)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.mcp_models import (
    EntityNetworkInput,
    EntitySearchInput,
    EntityTimelineInput,
    ListEntitiesInput,
)
from src.mcp_server import _offload
from src.sanitization import sanitize_untrusted_text

# ── Test Infrastructure ──────────────────────────────────────────────


class MockEmailDB:
    """Minimal email database stub with entity-related methods."""

    def search_by_entity(self, entity, entity_type=None, limit=20):
        return [
            {"uid": "uid-1", "subject": f"Mentions {entity}", "entity": entity},
        ]

    def top_entities(self, entity_type=None, limit=20):
        return [
            {"entity": "Acme Corp", "type": "organization", "count": 42},
            {"entity": "employee@example.test", "type": "email", "count": 15},
        ]

    def entity_co_occurrences(self, entity, limit=20):
        return [
            {"entity": "Bob Smith", "co_occurrence_count": 10},
        ]

    def entity_timeline(self, entity, period="month"):
        return [
            {"period": "2025-01", "count": 5},
            {"period": "2025-02", "count": 8},
        ]


class MockDeps:
    """Dependency injection matching ToolDepsProto."""

    _email_db = MockEmailDB()

    @staticmethod
    def get_retriever():
        return MagicMock()

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


def _register():
    """Register the entities module and return the FakeMCP with captured tools."""
    from src.tools import entities

    fake_mcp = FakeMCP()
    entities.register(fake_mcp, MockDeps)
    return fake_mcp


# ── Tool Tests ───────────────────────────────────────────────────────


class TestEntitySearchByEntity:
    """Tests for email_search_by_entity (line 22)."""

    @pytest.mark.asyncio
    async def test_returns_matching_results(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_search_by_entity"]

        params = EntitySearchInput(entity="Acme Corp")
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["entity"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_with_entity_type_filter(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_search_by_entity"]

        params = EntitySearchInput(entity="Acme", entity_type="organization", limit=5)
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_db_unavailable(self):
        fake_mcp = FakeMCP()
        from src.tools import entities

        class NullDbDeps(MockDeps):
            @staticmethod
            def get_email_db():
                return None

        entities.register(fake_mcp, NullDbDeps)
        fn = fake_mcp._tools["email_search_by_entity"]

        params = EntitySearchInput(entity="test")
        result = await fn(params)
        data = json.loads(result)

        assert "error" in data


class TestListEntities:
    """Tests for email_list_entities (line 28)."""

    @pytest.mark.asyncio
    async def test_returns_entity_list(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_list_entities"]

        params = ListEntitiesInput()
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["entity"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_with_type_filter(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_list_entities"]

        params = ListEntitiesInput(entity_type="organization", limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)


class TestEntityNetwork:
    """Tests for email_entity_network (line 34)."""

    @pytest.mark.asyncio
    async def test_returns_co_occurrences(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_entity_network"]

        params = EntityNetworkInput(entity="Acme Corp")
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["entity"] == "Bob Smith"

    @pytest.mark.asyncio
    async def test_with_custom_limit(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_entity_network"]

        params = EntityNetworkInput(entity="Acme Corp", limit=5)
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)


class TestEntityTimeline:
    """Tests for email_entity_timeline (line 52)."""

    @pytest.mark.asyncio
    async def test_returns_timeline_data(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_entity_timeline"]

        params = EntityTimelineInput(entity="Acme Corp")
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["period"] == "2025-01"
        assert data[1]["count"] == 8

    @pytest.mark.asyncio
    async def test_with_custom_period(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_entity_timeline"]

        params = EntityTimelineInput(entity="Acme Corp", period="day")
        result = await fn(params)
        data = json.loads(result)

        assert isinstance(data, list)
