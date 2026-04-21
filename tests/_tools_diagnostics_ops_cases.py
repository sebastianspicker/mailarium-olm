# ruff: noqa: F401,I001
"""Tests for src/tools/diagnostics.py — admin and diagnostic tools.

Covers: email_admin with action='diagnostics', 'reingest_bodies',
'reembed', 'reingest_metadata', 'reingest_analytics', and invalid actions.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.mcp_server import _offload
from src.sanitization import sanitize_untrusted_text

# ── Shared Test Infrastructure ───────────────────────────────

from .helpers.diagnostics_fakes import FakeMCP, MockDeps, MockEmailDB, MockRetriever, _register


class TestReingestBodies:
    @pytest.mark.asyncio
    async def test_reingest_bodies_happy_path(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src import mcp_server
        from src.mcp_models import EmailAdminInput

        original_retriever = mcp_server._retriever
        original_email_db = mcp_server._email_db
        original_retriever_lock = mcp_server._retriever_lock
        original_email_db_lock = mcp_server._email_db_lock
        try:
            mcp_server._retriever = object()
            mcp_server._email_db = object()
            mcp_server._retriever_lock = threading.Lock()
            mcp_server._email_db_lock = threading.Lock()

            with patch("src.ingest.reingest_bodies") as mock_fn:
                mock_fn.return_value = {"updated": 10, "skipped": 5}
                params = EmailAdminInput(
                    action="reingest_bodies",
                    olm_path="/tmp/test.olm",
                )
                result = await fn(params)
                data = json.loads(result)
                assert data["updated"] == 10
                assert mcp_server._retriever is None
                assert mcp_server._email_db is None
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._email_db = original_email_db
            mcp_server._retriever_lock = original_retriever_lock
            mcp_server._email_db_lock = original_email_db_lock

    @pytest.mark.asyncio
    async def test_reingest_bodies_missing_olm_path(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        params = EmailAdminInput(action="reingest_bodies")
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data
        assert "olm_path" in data["error"]

    @pytest.mark.asyncio
    async def test_reingest_bodies_file_not_found(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reingest_bodies", side_effect=FileNotFoundError):
            params = EmailAdminInput(
                action="reingest_bodies",
                olm_path="/nonexistent.olm",
            )
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_reingest_bodies_generic_error(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reingest_bodies", side_effect=RuntimeError("disk full")):
            params = EmailAdminInput(
                action="reingest_bodies",
                olm_path="/tmp/test.olm",
            )
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_reingest_bodies_with_force(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reingest_bodies") as mock_fn:
            mock_fn.return_value = {"updated": 20, "skipped": 0}
            params = EmailAdminInput(
                action="reingest_bodies",
                olm_path="/tmp/test.olm",
                force=True,
            )
            result = await fn(params)
            data = json.loads(result)
            assert data["updated"] == 20
            mock_fn.assert_called_once_with("/tmp/test.olm", force=True)


class TestReembed:
    @pytest.mark.asyncio
    async def test_reembed_happy_path(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src import mcp_server
        from src.mcp_models import EmailAdminInput

        original_retriever = mcp_server._retriever
        original_email_db = mcp_server._email_db
        original_retriever_lock = mcp_server._retriever_lock
        original_email_db_lock = mcp_server._email_db_lock
        try:
            mcp_server._retriever = object()
            mcp_server._email_db = object()
            mcp_server._retriever_lock = threading.Lock()
            mcp_server._email_db_lock = threading.Lock()

            with patch("src.ingest.reembed") as mock_fn:
                mock_fn.return_value = {"chunks_embedded": 500}
                params = EmailAdminInput(action="reembed", batch_size=50)
                result = await fn(params)
                data = json.loads(result)
                assert data["chunks_embedded"] == 500
                mock_fn.assert_called_once_with(batch_size=50)
                assert mcp_server._retriever is None
                assert mcp_server._email_db is None
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._email_db = original_email_db
            mcp_server._retriever_lock = original_retriever_lock
            mcp_server._email_db_lock = original_email_db_lock

    @pytest.mark.asyncio
    async def test_reembed_error(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reembed", side_effect=RuntimeError("OOM")):
            params = EmailAdminInput(action="reembed")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data


class TestReingestMetadata:
    @pytest.mark.asyncio
    async def test_reingest_metadata_happy_path(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src import mcp_server
        from src.mcp_models import EmailAdminInput

        original_retriever = mcp_server._retriever
        original_email_db = mcp_server._email_db
        original_retriever_lock = mcp_server._retriever_lock
        original_email_db_lock = mcp_server._email_db_lock
        try:
            mcp_server._retriever = object()
            mcp_server._email_db = object()
            mcp_server._retriever_lock = threading.Lock()
            mcp_server._email_db_lock = threading.Lock()

            with patch("src.ingest.reingest_metadata") as mock_fn:
                mock_fn.return_value = {"updated": 15}
                params = EmailAdminInput(
                    action="reingest_metadata",
                    olm_path="/tmp/test.olm",
                )
                result = await fn(params)
                data = json.loads(result)
                assert data["updated"] == 15
                assert mcp_server._retriever is None
                assert mcp_server._email_db is None
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._email_db = original_email_db
            mcp_server._retriever_lock = original_retriever_lock
            mcp_server._email_db_lock = original_email_db_lock

    @pytest.mark.asyncio
    async def test_reingest_metadata_missing_olm_path(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        params = EmailAdminInput(action="reingest_metadata")
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data
        assert "olm_path" in data["error"]

    @pytest.mark.asyncio
    async def test_reingest_metadata_file_not_found(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reingest_metadata", side_effect=FileNotFoundError):
            params = EmailAdminInput(
                action="reingest_metadata",
                olm_path="/nonexistent.olm",
            )
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.asyncio
    async def test_reingest_metadata_generic_error(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reingest_metadata", side_effect=RuntimeError("bad XML")):
            params = EmailAdminInput(
                action="reingest_metadata",
                olm_path="/tmp/test.olm",
            )
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data


class TestReingestAnalytics:
    @pytest.mark.asyncio
    async def test_reingest_analytics_happy_path(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src import mcp_server
        from src.mcp_models import EmailAdminInput

        original_retriever = mcp_server._retriever
        original_email_db = mcp_server._email_db
        original_retriever_lock = mcp_server._retriever_lock
        original_email_db_lock = mcp_server._email_db_lock
        try:
            mcp_server._retriever = object()
            mcp_server._email_db = object()
            mcp_server._retriever_lock = threading.Lock()
            mcp_server._email_db_lock = threading.Lock()

            with patch("src.ingest.reingest_analytics") as mock_fn:
                mock_fn.return_value = {"processed": 100}
                params = EmailAdminInput(action="reingest_analytics")
                result = await fn(params)
                data = json.loads(result)
                assert data["processed"] == 100
                assert mcp_server._retriever is None
                assert mcp_server._email_db is None
        finally:
            mcp_server._retriever = original_retriever
            mcp_server._email_db = original_email_db
            mcp_server._retriever_lock = original_retriever_lock
            mcp_server._email_db_lock = original_email_db_lock

    @pytest.mark.asyncio
    async def test_reingest_analytics_error(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        with patch("src.ingest.reingest_analytics", side_effect=RuntimeError("model load failed")):
            params = EmailAdminInput(action="reingest_analytics")
            result = await fn(params)
            data = json.loads(result)
            assert "error" in data


class TestInvalidAction:
    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailAdminInput

        with pytest.raises(ValidationError, match="action"):
            EmailAdminInput(action="destroy_everything")
