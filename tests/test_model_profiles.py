"""Tests for model-aware MCP response profiles."""

from __future__ import annotations

import json

import pytest

# ── Profile resolution ────────────────────────────────────────


class TestProfileResolution:
    def test_default_profile_is_auto(self, monkeypatch):
        from src.config import Settings, get_settings

        monkeypatch.delenv("MCP_MODEL_PROFILE", raising=False)
        get_settings.cache_clear()
        try:
            s = Settings.from_env()
            assert s.mcp_model_profile == "auto"
            # auto = balanced defaults
            assert s.mcp_max_body_chars == 500
            assert s.mcp_max_response_tokens == 8000
            assert s.mcp_max_full_body_chars == 10000
            assert s.mcp_max_json_response_chars == 32000
            assert s.mcp_max_triage_results == 50
            assert s.mcp_max_search_results == 30
        finally:
            get_settings.cache_clear()

    def test_tight_profile_sets_tight_defaults(self, monkeypatch):
        from src.config import Settings, get_settings

        monkeypatch.setenv("MCP_MODEL_PROFILE", "tight")
        # Clear any per-variable overrides
        for var in [
            "MCP_MAX_BODY_CHARS",
            "MCP_MAX_RESPONSE_TOKENS",
            "MCP_MAX_FULL_BODY_CHARS",
            "MCP_MAX_JSON_RESPONSE_CHARS",
            "MCP_MAX_TRIAGE_RESULTS",
            "MCP_MAX_SEARCH_RESULTS",
        ]:
            monkeypatch.delenv(var, raising=False)
        get_settings.cache_clear()
        try:
            s = Settings.from_env()
            assert s.mcp_model_profile == "tight"
            assert s.mcp_max_body_chars == 300
            assert s.mcp_max_response_tokens == 4000
            assert s.mcp_max_full_body_chars == 5000
            assert s.mcp_max_json_response_chars == 16000
            assert s.mcp_max_triage_results == 30
            assert s.mcp_max_search_results == 15
        finally:
            get_settings.cache_clear()

    def test_generous_profile_sets_generous_defaults(self, monkeypatch):
        from src.config import Settings, get_settings

        monkeypatch.setenv("MCP_MODEL_PROFILE", "generous")
        for var in [
            "MCP_MAX_BODY_CHARS",
            "MCP_MAX_RESPONSE_TOKENS",
            "MCP_MAX_FULL_BODY_CHARS",
            "MCP_MAX_JSON_RESPONSE_CHARS",
            "MCP_MAX_TRIAGE_RESULTS",
            "MCP_MAX_SEARCH_RESULTS",
        ]:
            monkeypatch.delenv(var, raising=False)
        get_settings.cache_clear()
        try:
            s = Settings.from_env()
            assert s.mcp_model_profile == "generous"
            assert s.mcp_max_body_chars == 800
            assert s.mcp_max_response_tokens == 16000
            assert s.mcp_max_full_body_chars == 20000
            assert s.mcp_max_json_response_chars == 64000
            assert s.mcp_max_triage_results == 100
            assert s.mcp_max_search_results == 50
        finally:
            get_settings.cache_clear()

    def test_unknown_profile_falls_back_to_auto(self, monkeypatch):
        from src.config import Settings, get_settings

        monkeypatch.setenv("MCP_MODEL_PROFILE", "gpt4")
        for var in [
            "MCP_MAX_BODY_CHARS",
            "MCP_MAX_RESPONSE_TOKENS",
            "MCP_MAX_FULL_BODY_CHARS",
            "MCP_MAX_JSON_RESPONSE_CHARS",
            "MCP_MAX_TRIAGE_RESULTS",
            "MCP_MAX_SEARCH_RESULTS",
        ]:
            monkeypatch.delenv(var, raising=False)
        get_settings.cache_clear()
        try:
            s = Settings.from_env()
            assert s.mcp_model_profile == "auto"
            # Falls back to balanced defaults
            assert s.mcp_max_body_chars == 500
            assert s.mcp_max_response_tokens == 8000
        finally:
            get_settings.cache_clear()

    def test_env_override_wins_over_profile(self, monkeypatch):
        from src.config import Settings, get_settings

        monkeypatch.setenv("MCP_MODEL_PROFILE", "tight")
        monkeypatch.setenv("MCP_MAX_BODY_CHARS", "1000")
        get_settings.cache_clear()
        try:
            s = Settings.from_env()
            assert s.mcp_model_profile == "tight"
            # Body chars overridden by env, rest from tight profile
            assert s.mcp_max_body_chars == 1000
            assert s.mcp_max_response_tokens == 4000
        finally:
            get_settings.cache_clear()

    def test_resolve_runtime_passes_through_profile(self, monkeypatch):
        from src.config import get_settings, resolve_runtime_settings

        monkeypatch.setenv("MCP_MODEL_PROFILE", "generous")
        for var in [
            "MCP_MAX_BODY_CHARS",
            "MCP_MAX_RESPONSE_TOKENS",
            "MCP_MAX_FULL_BODY_CHARS",
            "MCP_MAX_JSON_RESPONSE_CHARS",
            "MCP_MAX_TRIAGE_RESULTS",
            "MCP_MAX_SEARCH_RESULTS",
        ]:
            monkeypatch.delenv(var, raising=False)
        get_settings.cache_clear()
        try:
            s = resolve_runtime_settings()
            assert s.mcp_model_profile == "generous"
            assert s.mcp_max_triage_results == 100
            assert s.mcp_max_search_results == 50
        finally:
            get_settings.cache_clear()


# ── Per-tool result clamping ──────────────────────────────────


def _make_result(chunk_id="x", text="hello", distance=0.25):
    from src.retriever import SearchResult

    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={"subject": "Hi", "sender_email": "a@example.com"},
        distance=distance,
    )


class _CapturingRetriever:
    """Captures search_filtered kwargs for assertion."""

    def __init__(self):
        self.captured_kwargs = {}

    def search_filtered(self, **kwargs):
        self.captured_kwargs = kwargs
        return [_make_result()]

    def serialize_results(self, query, results):
        return {"query": query, "count": len(results), "results": []}

    def format_results_for_llm(self, results):
        return "formatted"

    def stats(self):
        return {"total_emails": 100, "date_range": {}, "unique_senders": 5}


@pytest.mark.asyncio
async def test_triage_top_k_clamped_by_profile(monkeypatch):
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailTriageInput
    from src.tools import search as search_mod

    monkeypatch.setenv("MCP_MODEL_PROFILE", "tight")
    for var in ["MCP_MAX_TRIAGE_RESULTS", "MCP_MAX_SEARCH_RESULTS"]:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()

    retriever = _CapturingRetriever()
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        # Pydantic allows up to 100; tight profile caps at 30
        params = EmailTriageInput(query="test query", top_k=80)
        result = await search_mod.email_triage(params)
        data = json.loads(result)

        assert retriever.captured_kwargs["top_k"] == 30
        assert data["_capped"]["requested"] == 80
        assert data["_capped"]["effective"] == 30
        assert data["_capped"]["profile"] == "tight"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_search_top_k_clamped_by_profile(monkeypatch):
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    monkeypatch.setenv("MCP_MODEL_PROFILE", "tight")
    for var in ["MCP_MAX_TRIAGE_RESULTS", "MCP_MAX_SEARCH_RESULTS"]:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()

    retriever = _CapturingRetriever()
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        # Pydantic allows up to 30; tight profile caps at 15
        params = EmailSearchStructuredInput(query="test query", top_k=30)
        result = await email_search_structured(params)
        data = json.loads(result)

        assert retriever.captured_kwargs["top_k"] == 15
        assert data["_capped"]["requested"] == 30
        assert data["_capped"]["effective"] == 15
        assert data["_capped"]["profile"] == "tight"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_no_capping_when_under_limit(monkeypatch):
    """When top_k <= profile limit, no _capped metadata is emitted."""
    from src import mcp_server
    from src.config import get_settings
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    monkeypatch.setenv("MCP_MODEL_PROFILE", "generous")
    for var in ["MCP_MAX_TRIAGE_RESULTS", "MCP_MAX_SEARCH_RESULTS"]:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()

    retriever = _CapturingRetriever()
    monkeypatch.setattr(mcp_server, "get_retriever", lambda: retriever)

    try:
        params = EmailSearchStructuredInput(query="test", top_k=10)
        result = await email_search_structured(params)
        data = json.loads(result)

        assert retriever.captured_kwargs["top_k"] == 10
        assert "_capped" not in data
    finally:
        get_settings.cache_clear()


# ── Diagnostics includes profile ──────────────────────────────


@pytest.mark.asyncio
async def test_diagnostics_includes_profile(monkeypatch):
    from src.config import get_settings
    from src.tools.diagnostics import email_diagnostics

    monkeypatch.setenv("MCP_MODEL_PROFILE", "tight")
    for var in [
        "MCP_MAX_BODY_CHARS",
        "MCP_MAX_RESPONSE_TOKENS",
        "MCP_MAX_FULL_BODY_CHARS",
        "MCP_MAX_JSON_RESPONSE_CHARS",
        "MCP_MAX_TRIAGE_RESULTS",
        "MCP_MAX_SEARCH_RESULTS",
    ]:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()

    class _FakeEmbedder:
        device = "cpu"
        _model = None
        has_sparse = False
        has_colbert = False

    class _FakeRetriever:
        embedder = _FakeEmbedder()

    class _FakeDeps:
        @staticmethod
        def get_retriever():
            return _FakeRetriever()

        @staticmethod
        def get_email_db():
            return None

        @staticmethod
        async def offload(fn):
            return fn()

    try:
        result = await email_diagnostics(_FakeDeps)
        data = json.loads(result)
        assert data["mcp_profile"] == "tight"
        assert data["batch_size_setting"] == 0
        assert data["embedder_device"] == "cpu"
        assert data["mcp_budget"]["max_body_chars"] == 300
        assert data["mcp_budget"]["max_response_tokens"] == 4000
        assert data["mcp_budget"]["max_full_body_chars"] == 5000
        assert data["mcp_budget"]["max_json_response_chars"] == 16000
        assert data["mcp_budget"]["max_triage_results"] == 30
        assert data["mcp_budget"]["max_search_results"] == 15
    finally:
        get_settings.cache_clear()
