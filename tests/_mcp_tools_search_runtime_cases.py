# ruff: noqa: F401
import json
import sqlite3
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import get_settings

from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result, _patch_search_deps


@pytest.mark.asyncio
async def test_email_search_structured_forwards_new_filters(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(
        query="hello",
        top_k=5,
        subject="approval",
        folder="inbox",
        cc="finance",
        min_score=0.8,
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["subject"] == "approval"
    assert captured["folder"] == "inbox"
    assert captured["cc"] == "finance"
    assert captured["min_score"] == 0.8
    assert data["filters"]["subject"] == "approval"
    assert data["filters"]["folder"] == "inbox"
    assert data["filters"]["cc"] == "finance"
    assert data["filters"]["min_score"] == 0.8


@pytest.mark.asyncio
async def test_email_search_structured_accepts_legacy_aliases(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput.model_validate(
        {
            "query": "hello",
            "max_results": 7,
            "query_expansion": True,
        }
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["top_k"] == 7
    assert captured["expand_query"] is True
    assert data["top_k"] == 7
    assert data["filters"]["expand_query"] is True


@pytest.mark.asyncio
async def test_email_search_structured_emits_strict_json(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [_make_result(distance=float("nan"))]

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(query="hello", top_k=5)
    payload = await email_search_structured(params)

    assert "NaN" not in payload
    assert "Infinity" not in payload


@pytest.mark.asyncio
async def test_email_search_structured_exposes_retrieval_diagnostics(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    class DummyRetriever(_BasicRetriever):
        @property
        def last_search_debug(self):
            return {
                "original_query": "student.case@example.test",
                "executed_query": "student.case@example.test sbv timeline",
                "expand_query_requested": True,
                "used_query_expansion": True,
                "query_expansion_suffix": "sbv timeline",
            }

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(query="student.case@example.test", expand_query=True)
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert data["retrieval_diagnostics"]["original_query"] == "student.case@example.test"
    assert data["retrieval_diagnostics"]["executed_query"].endswith("sbv timeline")
    assert data["retrieval_diagnostics"]["expand_query_requested"] is True
    assert data["retrieval_diagnostics"]["used_query_expansion"] is True


@pytest.mark.asyncio
async def test_email_list_senders_returns_json(monkeypatch):
    from src.mcp_models import ListSendersInput
    from src.tools.search import email_list_senders

    class DummyRetriever:
        def list_senders(self, limit=30):
            return [
                {
                    "name": "Alice",
                    "email": "employee@example.test",
                    "count": 3,
                }
            ]

    _patch_search_deps(monkeypatch, DummyRetriever())
    output = await email_list_senders(ListSendersInput(limit=10))
    data = json.loads(output)

    assert data["count"] == 1
    assert data["senders"][0]["name"] == "Alice"
    assert data["senders"][0]["count"] == 3


@pytest.mark.asyncio
async def test_email_list_folders_returns_json(monkeypatch):
    from src.tools.search import email_list_folders

    class DummyRetriever:
        def list_folders(self):
            return [
                {"folder": "Inbox", "count": 42},
                {"folder": "Archive", "count": 7},
            ]

    _patch_search_deps(monkeypatch, DummyRetriever())
    output = await email_list_folders()
    data = json.loads(output)

    assert data["count"] == 2
    assert data["folders"][0]["folder"] == "Inbox"
    assert data["folders"][0]["count"] == 42
    assert data["folders"][1]["folder"] == "Archive"


@pytest.mark.asyncio
async def test_email_list_folders_empty_archive(monkeypatch):
    from src.tools.search import email_list_folders

    class DummyRetriever:
        def list_folders(self):
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())
    output = await email_list_folders()
    data = json.loads(output)

    assert data["count"] == 0
    assert data["folders"] == []


@pytest.mark.asyncio
async def test_email_ingest_returns_stats_json(monkeypatch, tmp_path):
    from src.mcp_models import EmailIngestInput
    from src.tools.search import email_ingest

    fake_stats = {
        "emails_parsed": 10,
        "chunks_created": 15,
        "chunks_added": 15,
        "chunks_skipped": 0,
        "batches_written": 1,
        "total_in_db": 15,
        "dry_run": False,
        "elapsed_seconds": 1.2,
    }

    monkeypatch.setattr("src.ingest.ingest", lambda **kwargs: fake_stats)

    olm_path = tmp_path / "test.olm"
    olm_path.write_text("olm", encoding="utf-8")
    params = EmailIngestInput(olm_path=str(olm_path))
    output = await email_ingest(params)
    data = json.loads(output)

    assert data["emails_parsed"] == 10
    assert data["chunks_added"] == 15


@pytest.mark.asyncio
async def test_email_ingest_does_not_mutate_runtime_archive_paths(monkeypatch, tmp_path):
    from src.mcp_models import EmailIngestInput
    from src.tools.search import email_ingest

    monkeypatch.setattr(
        "src.ingest.ingest",
        lambda **kwargs: {
            "emails_parsed": 1,
            "chunks_created": 1,
            "chunks_added": 1,
            "chunks_skipped": 0,
            "batches_written": 1,
            "total_in_db": 1,
            "dry_run": False,
            "elapsed_seconds": 0.1,
        },
    )

    olm_path = tmp_path / "test.olm"
    olm_path.write_text("olm", encoding="utf-8")

    with (
        patch("src.mcp_server.set_runtime_archive_paths") as mock_set_paths,
        patch("src.mcp_server._resolved_runtime_paths", return_value=("/tmp/active-chroma", "/tmp/active.db")),
        patch("src.tools.search.invalidate_mcp_singletons") as mock_invalidate,
    ):
        params = EmailIngestInput(
            olm_path=str(olm_path),
            chromadb_path="/tmp/custom-chroma",
            sqlite_path="/tmp/custom-email.db",
        )
        output = await email_ingest(params)

    data = json.loads(output)
    assert data["emails_parsed"] == 1
    assert data["runtime_archive_unchanged"] is True
    assert data["active_archive_switch_required"] is True
    assert data["active_archive"]["sqlite_path"] == "/tmp/active.db"
    mock_set_paths.assert_not_called()
    mock_invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_email_ingest_invalidates_cache_when_target_matches_active_runtime(monkeypatch, tmp_path):
    from src.mcp_models import EmailIngestInput
    from src.tools.search import email_ingest

    monkeypatch.setattr(
        "src.ingest.ingest",
        lambda **kwargs: {
            "emails_parsed": 1,
            "chunks_created": 1,
            "chunks_added": 1,
            "chunks_skipped": 0,
            "batches_written": 1,
            "total_in_db": 1,
            "dry_run": False,
            "elapsed_seconds": 0.1,
        },
    )

    olm_path = tmp_path / "test.olm"
    olm_path.write_text("olm", encoding="utf-8")

    with (
        patch("src.mcp_server._resolved_runtime_paths", return_value=("/tmp/active-chroma", "/tmp/active.db")),
        patch("src.tools.search.invalidate_mcp_singletons") as mock_invalidate,
    ):
        params = EmailIngestInput(
            olm_path=str(olm_path),
            chromadb_path="/tmp/active-chroma",
            sqlite_path="/tmp/active.db",
        )
        output = await email_ingest(params)

    data = json.loads(output)
    assert data["emails_parsed"] == 1
    assert "runtime_archive_unchanged" not in data
    mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_email_ingest_handles_file_not_found(monkeypatch, tmp_path):
    from src.mcp_models import EmailIngestInput
    from src.tools.search import email_ingest

    def _raise(**kwargs):
        raise FileNotFoundError("not found")

    monkeypatch.setattr("src.ingest.ingest", _raise)

    olm_path = tmp_path / "missing-at-ingest.olm"
    olm_path.write_text("fixture", encoding="utf-8")

    params = EmailIngestInput(olm_path=str(olm_path))
    output = await email_ingest(params)
    data = json.loads(output)

    assert "error" in data


@pytest.mark.asyncio
async def test_email_search_structured_forwards_email_type(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(
        query="hello",
        email_type="reply",
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["email_type"] == "reply"
    assert data["filters"]["email_type"] == "reply"


@pytest.mark.asyncio
async def test_email_diagnostics_returns_json(monkeypatch):
    from src.mcp_server import _offload
    from src.tools import diagnostics

    class DummyEmbedder:
        device = "cpu"
        _model = type("Model", (), {"__name__": "StubModel"})()
        has_sparse = False
        has_colbert = False

    class DummyRetriever:
        embedder = DummyEmbedder()
        _sparse_index = None

    class MockDeps:
        get_retriever = staticmethod(lambda: DummyRetriever())
        get_email_db = staticmethod(lambda: None)
        offload = staticmethod(_offload)

    monkeypatch.setattr(diagnostics, "_deps", MockDeps)
    monkeypatch.setenv("DEVICE", "auto")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "0")
    get_settings.cache_clear()

    try:
        output = await diagnostics.email_diagnostics(MockDeps)
        data = json.loads(output)

        assert "embedding_model" in data
        assert "resolved_device" in data
        assert "resolved_batch_size" in data
        assert "batch_size_setting" in data
        assert "embedder_device" in data
        assert "embedder_batch_size" in data
        assert "embedder_backend" in data
        assert "sparse_enabled" in data
        assert "colbert_rerank_enabled" in data
        assert "sparse_vector_count" in data
        assert "sparse_index_built" in data
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_offload_runs_sync_in_thread():
    """_offload should run a sync function without blocking the event loop."""
    from src.mcp_server import _offload

    result = await _offload(lambda: 42)
    assert result == 42


@pytest.mark.asyncio
async def test_email_search_structured_forwards_attachment_filters(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(
        query="hello",
        attachment_name="report",
        attachment_type="pdf",
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["attachment_name"] == "report"
    assert captured["attachment_type"] == "pdf"
    assert data["filters"]["attachment_name"] == "report"
    assert data["filters"]["attachment_type"] == "pdf"


@pytest.mark.asyncio
async def test_offload_with_args():
    """_offload passes positional and keyword arguments through."""
    from src.mcp_server import _offload

    result = await _offload(lambda x, y=0: x + y, 10, y=5)
    assert result == 15
