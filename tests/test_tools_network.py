"""Tests for src/tools/network.py — network analysis tools.

Covers: email_contacts, email_network_analysis, relationship_paths,
shared_recipients, coordinated_timing, relationship_summary.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from src.mcp_server import _offload
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────


class MockEmailDB:
    """Minimal email DB stub with contact and communication methods."""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # Will be set by run_with_network via attribute assignment
        self._cached_comm_network = None

    def top_contacts(self, email_address, limit=20):
        return [
            {"email": "bob@example.com", "count": 15},
            {"email": "carol@example.com", "count": 8},
        ]

    def communication_between(self, email_a, email_b):
        return {
            "a_to_b": 10,
            "b_to_a": 5,
            "total": 15,
            "first_date": "2025-01-01",
            "last_date": "2025-06-01",
        }


class MockCommunicationNetwork:
    """Stub for CommunicationNetwork used by run_with_network."""

    def network_analysis(self, top_n=20):
        return {
            "nodes": top_n,
            "edges": 50,
            "top_centrality": [
                {"email": "alice@example.com", "centrality": 0.85},
            ],
        }

    def find_paths(self, source, target, max_hops=3, top_k=5):
        return [
            {"path": [source, "middleman@example.com", target], "weight": 10},
        ]

    def shared_recipients(self, email_addresses, min_shared=2):
        return [
            {"recipient": "shared@example.com", "shared_by": email_addresses, "count": 5},
            {"recipient": "another@example.com", "shared_by": email_addresses, "count": 3},
        ]

    def coordinated_timing(self, email_addresses, window_hours=24, min_events=3):
        return [
            {
                "window_start": "2025-06-01T09:00:00",
                "window_end": "2025-06-01T10:00:00",
                "participants": email_addresses,
                "event_count": 5,
            },
        ]

    def relationship_summary(self, email_address, limit=20):
        return {
            "email": email_address,
            "top_contacts": [{"email": "bob@example.com", "count": 15}],
            "community": "finance",
            "bridge_score": 0.3,
        }


class MockDeps:
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
    def __init__(self):
        self._tools = {}

    def tool(self, name=None, annotations=None):
        def decorator(fn):
            self._tools[name] = fn
            return fn

        return decorator


def _register():
    from src.tools import network

    fake_mcp = FakeMCP()
    # Pre-cache the mock network on the DB to skip CommunicationNetwork init
    MockDeps._email_db._cached_comm_network = MockCommunicationNetwork()
    network.register(fake_mcp, MockDeps)
    return fake_mcp


# ── email_contacts tests ─────────────────────────────────────


class TestEmailContacts:
    @pytest.mark.asyncio
    async def test_top_contacts(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_contacts"]
        from src.mcp_models import EmailContactsInput

        params = EmailContactsInput(email_address="alice@example.com", limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["email"] == "bob@example.com"

    @pytest.mark.asyncio
    async def test_compare_with_bidirectional(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_contacts"]
        from src.mcp_models import EmailContactsInput

        params = EmailContactsInput(
            email_address="alice@example.com",
            compare_with="bob@example.com",
        )
        result = await fn(params)
        data = json.loads(result)
        assert data["a_to_b"] == 10
        assert data["b_to_a"] == 5
        assert data["total"] == 15


# ── email_network_analysis tests ─────────────────────────────


class TestNetworkAnalysis:
    @pytest.mark.asyncio
    async def test_network_analysis(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_network_analysis"]
        from src.mcp_models import NetworkAnalysisInput

        params = NetworkAnalysisInput(top_n=10)
        result = await fn(params)
        data = json.loads(result)
        assert "nodes" in data
        assert "top_centrality" in data

    @pytest.mark.asyncio
    async def test_network_analysis_no_db(self):
        """Returns error when DB is unavailable."""
        fake_mcp = _register()
        fn = fake_mcp._tools["email_network_analysis"]
        old_db = MockDeps._email_db
        MockDeps._email_db = None
        try:
            from src.mcp_models import NetworkAnalysisInput

            params = NetworkAnalysisInput(top_n=10)
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._email_db = old_db


# ── relationship_paths tests ─────────────────────────────────


class TestRelationshipPaths:
    @pytest.mark.asyncio
    async def test_find_paths(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["relationship_paths"]
        from src.mcp_models import RelationshipPathsInput

        params = RelationshipPathsInput(
            source="alice@example.com",
            target="dave@example.com",
            max_hops=3,
            top_k=5,
        )
        result = await fn(params)
        data = json.loads(result)
        assert "paths" in data
        assert "count" in data
        assert data["count"] == 1
        assert "middleman@example.com" in data["paths"][0]["path"]


# ── shared_recipients tests ──────────────────────────────────


class TestSharedRecipients:
    @pytest.mark.asyncio
    async def test_shared_recipients(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["shared_recipients"]
        from src.mcp_models import SharedRecipientsInput

        params = SharedRecipientsInput(
            email_addresses=["alice@example.com", "bob@example.com"],
            min_shared=2,
            limit=10,
        )
        result = await fn(params)
        data = json.loads(result)
        assert "shared_recipients" in data
        assert "count" in data
        assert "total" in data
        assert data["count"] <= data["total"]

    @pytest.mark.asyncio
    async def test_shared_recipients_with_limit(self):
        """Limit should cap the number of returned results."""
        fake_mcp = _register()
        fn = fake_mcp._tools["shared_recipients"]
        from src.mcp_models import SharedRecipientsInput

        params = SharedRecipientsInput(
            email_addresses=["alice@example.com", "bob@example.com"],
            limit=1,
        )
        result = await fn(params)
        data = json.loads(result)
        assert data["count"] == 1
        assert data["total"] == 2


# ── coordinated_timing tests ─────────────────────────────────


class TestCoordinatedTiming:
    @pytest.mark.asyncio
    async def test_coordinated_timing(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["coordinated_timing"]
        from src.mcp_models import CoordinatedTimingInput

        params = CoordinatedTimingInput(
            email_addresses=["alice@example.com", "bob@example.com"],
            window_hours=24,
            min_events=3,
            limit=10,
        )
        result = await fn(params)
        data = json.loads(result)
        assert "windows" in data
        assert "count" in data
        assert data["count"] >= 1

    @pytest.mark.asyncio
    async def test_coordinated_timing_with_limit(self):
        """Limit caps the number of returned windows."""
        fake_mcp = _register()
        fn = fake_mcp._tools["coordinated_timing"]
        from src.mcp_models import CoordinatedTimingInput

        params = CoordinatedTimingInput(
            email_addresses=["alice@example.com", "bob@example.com"],
            limit=1,
        )
        result = await fn(params)
        data = json.loads(result)
        assert data["count"] <= 1


# ── relationship_summary tests ────────────────────────────────


class TestRelationshipSummary:
    @pytest.mark.asyncio
    async def test_relationship_summary(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["relationship_summary"]
        from src.mcp_models import RelationshipSummaryInput

        params = RelationshipSummaryInput(
            email_address="alice@example.com",
            limit=10,
        )
        result = await fn(params)
        data = json.loads(result)
        assert data["email"] == "alice@example.com"
        assert "top_contacts" in data
        assert "bridge_score" in data


# ── DB unavailable tests ─────────────────────────────────────


class TestNetworkDBUnavailable:
    @pytest.mark.asyncio
    async def test_contacts_no_db(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_contacts"]
        old_db = MockDeps._email_db
        MockDeps._email_db = None
        try:
            from src.mcp_models import EmailContactsInput

            params = EmailContactsInput(email_address="alice@example.com")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_relationship_paths_no_db(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["relationship_paths"]
        old_db = MockDeps._email_db
        MockDeps._email_db = None
        try:
            from src.mcp_models import RelationshipPathsInput

            params = RelationshipPathsInput(
                source="a@b.com",
                target="c@d.com",
            )
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._email_db = old_db
