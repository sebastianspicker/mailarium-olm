"""Tests for src/tools/topics.py — clusters, topics, similarity, discovery tools.

Covers: email_clusters, email_find_similar, email_topics, email_discovery.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.mcp_server import _offload
from src.retriever import SearchResult
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────


def _make_result(
    uid="uid-1",
    text="Budget proposal review.",
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
    def search(self, query, top_k=10, where=None):
        return [
            _make_result(uid="uid-1"),
            _make_result(uid="uid-2", text="Vendor comparison.", sender="bob@example.com"),
        ]

    def search_filtered(self, query, top_k=10, **kwargs):
        return self.search(query, top_k=top_k)

    def serialize_results(self, query, results, **kwargs):
        return {
            "query": query,
            "count": len(results),
            "results": [{"uid": r.metadata.get("uid"), "subject": r.metadata.get("subject")} for r in results],
        }


class MockEmailDB:
    def __init__(self):
        self._clusters = [
            {"cluster_id": 0, "size": 10, "label": "budget"},
            {"cluster_id": 1, "size": 5, "label": "meeting"},
        ]
        self._topics = [
            {"topic_id": 0, "label": "finance", "top_words": ["budget", "cost"]},
            {"topic_id": 1, "label": "scheduling", "top_words": ["meeting", "calendar"]},
        ]
        self._keywords = [
            {"keyword": "budget", "count": 15},
            {"keyword": "meeting", "count": 10},
        ]

    def get_email_full(self, uid):
        if uid == "uid-1":
            return {"uid": "uid-1", "body_text": "Budget proposal review.", "subject": "Budget"}
        return None

    def cluster_summary(self):
        return self._clusters

    def emails_in_cluster(self, cluster_id, limit=30):
        return [{"uid": "uid-1", "subject": "Budget", "cluster_id": cluster_id}]

    def topic_distribution(self):
        return self._topics

    def emails_by_topic(self, topic_id, limit=20):
        return [{"uid": "uid-1", "subject": "Finance Report", "topic_id": topic_id}]

    def top_keywords(self, sender=None, folder=None, limit=30):
        return self._keywords

    def top_contacts(self, email, limit=5):
        return [{"email": "bob@example.com", "count": 5}]


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
    from src.tools import topics

    fake_mcp = FakeMCP()
    topics.register(fake_mcp, MockDeps)
    return fake_mcp


# ── email_clusters tests ─────────────────────────────────────


class TestEmailClusters:
    @pytest.mark.asyncio
    async def test_list_all_clusters(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_clusters"]
        from src.mcp_models import EmailClustersInput

        params = EmailClustersInput()
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["cluster_id"] == 0

    @pytest.mark.asyncio
    async def test_emails_in_cluster(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_clusters"]
        from src.mcp_models import EmailClustersInput

        params = EmailClustersInput(cluster_id=0, limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["cluster_id"] == 0

    @pytest.mark.asyncio
    async def test_no_clusters_available(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_clusters"]
        old_db = MockDeps._email_db

        class NoClusters(MockEmailDB):
            def cluster_summary(self):
                return []

        MockDeps._email_db = NoClusters()
        try:
            from src.mcp_models import EmailClustersInput

            params = EmailClustersInput()
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._email_db = old_db


# ── email_find_similar tests ─────────────────────────────────


class TestEmailFindSimilar:
    @pytest.mark.asyncio
    async def test_find_similar_by_uid(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_find_similar"]
        from src.mcp_models import FindSimilarInput

        params = FindSimilarInput(uid="uid-1", top_k=5)
        result = await fn(params)
        data = json.loads(result)
        assert "count" in data
        assert "results" in data

    @pytest.mark.asyncio
    async def test_find_similar_by_query(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_find_similar"]
        from src.mcp_models import FindSimilarInput

        params = FindSimilarInput(query="budget review", top_k=5)
        result = await fn(params)
        data = json.loads(result)
        assert "count" in data

    @pytest.mark.asyncio
    async def test_find_similar_no_params_error(self):
        from pydantic import ValidationError

        from src.mcp_models import FindSimilarInput

        with pytest.raises(ValidationError):
            FindSimilarInput(top_k=5)

    @pytest.mark.asyncio
    async def test_find_similar_uid_not_found(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_find_similar"]
        from src.mcp_models import FindSimilarInput

        params = FindSimilarInput(uid="nonexistent", top_k=5)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_find_similar_excludes_self(self):
        """Results should not include the source email UID."""
        fake_mcp = _register()
        fn = fake_mcp._tools["email_find_similar"]
        from src.mcp_models import FindSimilarInput

        params = FindSimilarInput(uid="uid-1", top_k=5)
        result = await fn(params)
        data = json.loads(result)
        for r in data.get("results", []):
            assert r["uid"] != "uid-1"

    @pytest.mark.asyncio
    async def test_find_similar_with_scan_id(self):
        from src import scan_session

        scan_session.reset_all_sessions()

        fake_mcp = _register()
        fn = fake_mcp._tools["email_find_similar"]
        from src.mcp_models import FindSimilarInput

        params = FindSimilarInput(query="budget", top_k=10, scan_id="test_scan")
        result = await fn(params)
        data = json.loads(result)
        assert "_scan" in data

        scan_session.reset_all_sessions()


# ── email_topics tests ────────────────────────────────────────


class TestEmailTopics:
    @pytest.mark.asyncio
    async def test_list_all_topics(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_topics"]
        from src.mcp_models import EmailTopicsInput

        params = EmailTopicsInput()
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_emails_by_topic(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_topics"]
        from src.mcp_models import EmailTopicsInput

        params = EmailTopicsInput(topic_id=0, limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["topic_id"] == 0

    @pytest.mark.asyncio
    async def test_no_topics_available(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_topics"]
        old_db = MockDeps._email_db

        class NoTopics(MockEmailDB):
            def topic_distribution(self):
                return []

        MockDeps._email_db = NoTopics()
        try:
            from src.mcp_models import EmailTopicsInput

            params = EmailTopicsInput()
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
            assert "default ingest pipeline" in data["error"]
        finally:
            MockDeps._email_db = old_db


# ── email_discovery tests ────────────────────────────────────


class TestEmailDiscovery:
    @pytest.mark.asyncio
    async def test_keywords_mode(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_discovery"]
        from src.mcp_models import EmailDiscoveryInput

        params = EmailDiscoveryInput(mode="keywords", limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert data[0]["keyword"] == "budget"

    @pytest.mark.asyncio
    async def test_keywords_with_sender_filter(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_discovery"]
        from src.mcp_models import EmailDiscoveryInput

        params = EmailDiscoveryInput(mode="keywords", sender="alice@example.com", limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_keywords_no_results(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_discovery"]
        old_db = MockDeps._email_db

        class NoKeywords(MockEmailDB):
            def top_keywords(self, **kwargs):
                return []

        MockDeps._email_db = NoKeywords()
        try:
            from src.mcp_models import EmailDiscoveryInput

            params = EmailDiscoveryInput(mode="keywords", limit=10)
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_suggestions_mode(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_discovery"]
        from unittest.mock import patch

        from src.mcp_models import EmailDiscoveryInput

        with patch("src.query_suggestions.QuerySuggester") as mock_cls:
            mock_sug = MagicMock()
            mock_sug.suggest.return_value = [
                {"category": "people", "suggestions": ["alice", "bob"]},
            ]
            mock_cls.return_value = mock_sug

            params = EmailDiscoveryInput(mode="suggestions", limit=10)
            result = await fn(params)
            data = json.loads(result)
            assert isinstance(data, list)
            assert data[0]["category"] == "people"

    @pytest.mark.asyncio
    async def test_invalid_mode(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailDiscoveryInput

        with pytest.raises(ValidationError, match="mode"):
            EmailDiscoveryInput(mode="nonexistent", limit=10)
