"""Evidence lookup and rendering tests split from the RF12 catch-all."""

from __future__ import annotations

import json

import pytest

from tests._tools_evidence_cases import MockDeps, register_tools


class TestEvidenceAdd:
    @pytest.mark.asyncio
    async def test_add_evidence_happy_path(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_add"]
        from src.mcp_models import EvidenceAddInput

        params = EvidenceAddInput(
            email_uid="uid-1",
            category="bossing",
            key_quote="go with vendor A",
            summary="Decided vendor",
            relevance=4,
            notes="test",
        )
        result = await fn(params)
        data = json.loads(result)
        assert data["id"] >= 1
        assert data["category"] == "bossing"

    @pytest.mark.asyncio
    async def test_add_evidence_value_error(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_add"]
        old_db = MockDeps._email_db

        class FailDB(MockDeps._email_db.__class__):
            def add_evidence(self, **kwargs):
                raise ValueError("Quote not found in email body")

        MockDeps._email_db = FailDB()
        try:
            from src.mcp_models import EvidenceAddInput

            params = EvidenceAddInput(
                email_uid="uid-1",
                category="bossing",
                key_quote="nonexistent quote",
                summary="bad",
                relevance=3,
            )
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data
        finally:
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_add_evidence_accepts_workflow_neutral_category(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_add"]
        from src.mcp_models import EvidenceAddInput

        params = EvidenceAddInput(
            email_uid="uid-1",
            category="contradiction",
            key_quote="go with vendor A",
            summary="Tracks a contradiction anchor.",
            relevance=4,
        )
        result = await fn(params)
        data = json.loads(result)
        assert data["category"] == "contradiction"


class TestEvidenceAddBatch:
    @pytest.mark.asyncio
    async def test_batch_add_all_succeed(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_add_batch"]
        from src.mcp_models import EvidenceAddBatchInput, EvidenceAddInput

        items = [
            EvidenceAddInput(
                email_uid="uid-1",
                category="harassment",
                key_quote="quote one",
                summary="item one",
                relevance=3,
            ),
            EvidenceAddInput(
                email_uid="uid-1",
                category="bossing",
                key_quote="quote two",
                summary="item two",
                relevance=5,
            ),
        ]
        params = EvidenceAddBatchInput(items=items)
        result = await fn(params)
        data = json.loads(result)
        assert data["total_added"] == 2
        assert data["total_failed"] == 0
        assert len(data["added"]) == 2

    @pytest.mark.asyncio
    async def test_batch_add_partial_failure(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_add_batch"]
        old_db = MockDeps._email_db
        call_count = [0]

        class PartialFailDB(MockDeps._email_db.__class__):
            def add_evidence(self, **kwargs):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise ValueError("Bad quote")
                return {"id": call_count[0], **kwargs}

        MockDeps._email_db = PartialFailDB()
        try:
            from src.mcp_models import EvidenceAddBatchInput, EvidenceAddInput

            items = [
                EvidenceAddInput(
                    email_uid="uid-1",
                    category="bossing",
                    key_quote="good",
                    summary="ok",
                    relevance=3,
                ),
                EvidenceAddInput(
                    email_uid="uid-1",
                    category="bossing",
                    key_quote="bad",
                    summary="fail",
                    relevance=2,
                ),
            ]
            params = EvidenceAddBatchInput(items=items)
            result = await fn(params)
            data = json.loads(result)
            assert data["total_added"] == 1
            assert data["total_failed"] == 1
        finally:
            MockDeps._email_db = old_db


class TestEvidenceQuery:
    @pytest.mark.asyncio
    async def test_list_mode(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_query"]
        from src.mcp_models import EvidenceQueryInput

        params = EvidenceQueryInput(limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_search_mode(self):
        fake_mcp = register_tools()
        MockDeps._email_db.add_evidence(
            email_uid="uid-1",
            category="bossing",
            key_quote="unreasonable deadline",
            summary="Pressure tactics",
            relevance=4,
        )
        fn = fake_mcp._tools["evidence_query"]
        from src.mcp_models import EvidenceQueryInput

        params = EvidenceQueryInput(query="deadline", limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "items" in data

    @pytest.mark.asyncio
    async def test_timeline_mode(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_query"]
        from src.mcp_models import EvidenceQueryInput

        params = EvidenceQueryInput(sort="date", limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "items" in data

    @pytest.mark.asyncio
    async def test_compact_mode_strips_quotes(self):
        fake_mcp = register_tools()
        MockDeps._email_db.add_evidence(
            email_uid="uid-1",
            category="bossing",
            key_quote="A" * 100,
            summary="long quote",
            relevance=3,
        )
        fn = fake_mcp._tools["evidence_query"]
        from src.mcp_models import EvidenceQueryInput

        params = EvidenceQueryInput(include_quotes=False, limit=10)
        result = await fn(params)
        data = json.loads(result)
        for item in data["items"]:
            assert "quote_preview" in item
            assert "key_quote" not in item

    @pytest.mark.asyncio
    async def test_search_compact_mode(self):
        fake_mcp = register_tools()
        MockDeps._email_db.add_evidence(
            email_uid="uid-1",
            category="general",
            key_quote="B" * 100,
            summary="search compact",
            relevance=2,
        )
        fn = fake_mcp._tools["evidence_query"]
        from src.mcp_models import EvidenceQueryInput

        params = EvidenceQueryInput(query="compact", include_quotes=False, limit=10)
        result = await fn(params)
        data = json.loads(result)
        for item in data["items"]:
            assert "quote_preview" in item

    @pytest.mark.asyncio
    async def test_timeline_compact_mode(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_query"]
        from src.mcp_models import EvidenceQueryInput

        params = EvidenceQueryInput(sort="date", include_quotes=False, limit=10)
        result = await fn(params)
        data = json.loads(result)
        for item in data["items"]:
            assert "quote_preview" in item


class TestEvidenceGet:
    @pytest.mark.asyncio
    async def test_get_existing_evidence(self):
        fake_mcp = register_tools()
        item = MockDeps._email_db.add_evidence(
            email_uid="uid-1",
            category="harassment",
            key_quote="hostile remark",
            summary="Hostile",
            relevance=5,
        )
        fn = fake_mcp._tools["evidence_get"]
        from src.mcp_models import EvidenceGetInput

        params = EvidenceGetInput(evidence_id=item["id"])
        result = await fn(params)
        data = json.loads(result)
        assert data["id"] == item["id"]
        assert data["category"] == "harassment"

    @pytest.mark.asyncio
    async def test_get_nonexistent_evidence(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_get"]
        from src.mcp_models import EvidenceGetInput

        params = EvidenceGetInput(evidence_id=99999)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data


class TestEvidenceUpdate:
    @pytest.mark.asyncio
    async def test_update_existing(self):
        fake_mcp = register_tools()
        item = MockDeps._email_db.add_evidence(
            email_uid="uid-1",
            category="general",
            key_quote="test quote",
            summary="before",
            relevance=2,
        )
        fn = fake_mcp._tools["evidence_update"]
        from src.mcp_models import EvidenceUpdateInput

        params = EvidenceUpdateInput(evidence_id=item["id"], summary="after", relevance=4)
        result = await fn(params)
        data = json.loads(result)
        assert data["summary"] == "after"
        assert data["relevance"] == 4

    @pytest.mark.asyncio
    async def test_update_nonexistent(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_update"]
        from src.mcp_models import EvidenceUpdateInput

        params = EvidenceUpdateInput(evidence_id=99999, summary="nope")
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data


class TestEvidenceRemove:
    @pytest.mark.asyncio
    async def test_remove_existing(self):
        fake_mcp = register_tools()
        item = MockDeps._email_db.add_evidence(
            email_uid="uid-1",
            category="general",
            key_quote="to remove",
            summary="will delete",
            relevance=1,
        )
        fn = fake_mcp._tools["evidence_remove"]
        from src.mcp_models import EvidenceRemoveInput

        params = EvidenceRemoveInput(evidence_id=item["id"])
        result = await fn(params)
        data = json.loads(result)
        assert data["removed"] == item["id"]

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_remove"]
        from src.mcp_models import EvidenceRemoveInput

        params = EvidenceRemoveInput(evidence_id=99999)
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data


class TestEvidenceVerify:
    @pytest.mark.asyncio
    async def test_verify_returns_stats(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_verify"]
        result = await fn()
        data = json.loads(result)
        assert "total" in data
        assert "verified" in data


class TestEvidenceOverview:
    @pytest.mark.asyncio
    async def test_overview_returns_stats_and_categories(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_overview"]
        from src.mcp_models import EvidenceOverviewInput

        params = EvidenceOverviewInput()
        result = await fn(params)
        data = json.loads(result)
        assert "stats" in data
        assert "categories" in data

    @pytest.mark.asyncio
    async def test_overview_with_filter(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_overview"]
        from src.mcp_models import EvidenceOverviewInput

        params = EvidenceOverviewInput(category="bossing", min_relevance=3)
        result = await fn(params)
        data = json.loads(result)
        assert "stats" in data
