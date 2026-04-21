"""Evidence provenance and custody tests split from the RF12 catch-all."""

from __future__ import annotations

import json

import pytest

from tests._tools_evidence_cases import register_tools


class TestCustodyChain:
    @pytest.mark.asyncio
    async def test_custody_chain_compact(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["custody_chain"]
        from src.mcp_models import CustodyChainInput

        params = CustodyChainInput(compact=True, limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "events" in data
        assert "count" in data
        for event in data["events"]:
            assert "details" not in event
            assert "content_hash" not in event

    @pytest.mark.asyncio
    async def test_custody_chain_full(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["custody_chain"]
        from src.mcp_models import CustodyChainInput

        params = CustodyChainInput(compact=False, limit=10)
        result = await fn(params)
        data = json.loads(result)
        assert "events" in data
        assert data["events"][0]["details"] == {"note": "added"}

    @pytest.mark.asyncio
    async def test_custody_chain_with_filters(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["custody_chain"]
        from src.mcp_models import CustodyChainInput

        params = CustodyChainInput(target_type="evidence", target_id="1", action="evidence_add")
        result = await fn(params)
        data = json.loads(result)
        assert data["count"] >= 0


class TestEmailProvenance:
    @pytest.mark.asyncio
    async def test_provenance_returns_data(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["email_provenance"]
        from src.mcp_models import EmailProvenanceInput

        params = EmailProvenanceInput(email_uid="uid-1")
        result = await fn(params)
        data = json.loads(result)
        assert data["email_uid"] == "uid-1"


class TestEvidenceProvenance:
    @pytest.mark.asyncio
    async def test_evidence_provenance_returns_data(self):
        fake_mcp = register_tools()
        fn = fake_mcp._tools["evidence_provenance"]
        from src.mcp_models import EvidenceProvenanceInput

        params = EvidenceProvenanceInput(evidence_id=1)
        result = await fn(params)
        data = json.loads(result)
        assert data["evidence_id"] == 1
