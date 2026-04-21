"""Scan-aware search and tool tests split from the RF11 catch-all."""

from __future__ import annotations

import json

import pytest

pytest_plugins = ["tests._scan_session_cases"]


@pytest.mark.asyncio
async def test_triage_without_scan_id_unchanged(monkeypatch):
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailTriageInput
    from src.tools.search import email_triage
    from tests._scan_session_cases import ScanRetriever, make_search_result

    get_settings.cache_clear()
    retriever = ScanRetriever([make_search_result("uid1")])
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        params = EmailTriageInput(query="test")
        result = await email_triage(params)
        data = json.loads(result)
        assert "_scan" not in data
        assert data["count"] == 1
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_triage_with_scan_id_returns_scan_meta(monkeypatch):
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailTriageInput
    from src.tools.search import email_triage
    from tests._scan_session_cases import ScanRetriever, make_search_result

    get_settings.cache_clear()
    retriever = ScanRetriever([make_search_result("uid1"), make_search_result("uid2")])
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        params = EmailTriageInput(query="test", scan_id="sess1")
        result = await email_triage(params)
        data = json.loads(result)
        assert "_scan" in data
        assert data["_scan"]["scan_id"] == "sess1"
        assert data["_scan"]["new_count"] == 2
        assert data["_scan"]["excluded_count"] == 0
        assert data["_scan"]["seen_total"] == 2
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_triage_second_call_excludes_seen(monkeypatch):
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailTriageInput
    from src.tools.search import email_triage
    from tests._scan_session_cases import ScanRetriever, make_search_result

    get_settings.cache_clear()
    retriever = ScanRetriever([make_search_result("uid1"), make_search_result("uid2")])
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        params_one = EmailTriageInput(query="test", scan_id="sess1")
        await email_triage(params_one)

        retriever._results = [make_search_result("uid2"), make_search_result("uid3")]
        params_two = EmailTriageInput(query="more", scan_id="sess1")
        result_two = await email_triage(params_two)
        data_two = json.loads(result_two)
        assert data_two["_scan"]["new_count"] == 1
        assert data_two["_scan"]["excluded_count"] == 1
        assert data_two["count"] == 1
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_search_with_scan_id_excludes_seen(monkeypatch):
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured
    from tests._scan_session_cases import ScanRetriever, make_search_result

    get_settings.cache_clear()
    retriever = ScanRetriever([make_search_result("uid1"), make_search_result("uid2")])
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        params_one = EmailSearchStructuredInput(query="test", scan_id="sess1")
        result_one = await email_search_structured(params_one)
        data_one = json.loads(result_one)
        assert data_one["_scan"]["new_count"] == 2

        params_two = EmailSearchStructuredInput(query="more", scan_id="sess1")
        result_two = await email_search_structured(params_two)
        data_two = json.loads(result_two)
        assert data_two["_scan"]["excluded_count"] == 2
        assert data_two["_scan"]["new_count"] == 0
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_email_scan_status_nonexistent():
    from src.mcp_models import EmailScanInput
    from src.scan_session import session_status

    params = EmailScanInput(action="status", scan_id="nonexistent")
    status = session_status(params.scan_id)
    assert status is None


@pytest.mark.asyncio
async def test_email_scan_flag_then_candidates():
    from src import scan_session

    scan_session.flag_candidates("test", ["uid1", "uid2"], label="bossing", phase=1, score=0.8)

    candidates = scan_session.get_candidates("test", label="bossing")
    assert len(candidates) == 2
    assert candidates[0]["label"] == "bossing"
    assert candidates[0]["phase"] == 1

    status = scan_session.session_status("test")
    assert status["candidate_count"] == 2
    assert status["candidates_by_label"]["bossing"] == 2
