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


class TestBrowseTools:
    @pytest.mark.asyncio
    async def test_email_browse_default(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(limit=10)
        result = await fn(params)
        data = json.loads(result)

        assert "emails" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_email_browse_list_categories(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(list_categories=True)
        result = await fn(params)
        data = json.loads(result)

        assert "categories" in data

    @pytest.mark.asyncio
    async def test_email_browse_calendar(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(is_calendar=True, limit=5)
        result = await fn(params)
        data = json.loads(result)

        assert "emails" in data
        assert "count" in data

    @pytest.mark.asyncio
    async def test_email_browse_forensic_body_mode(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_browse"]

        from src.mcp_models import BrowseInput

        params = BrowseInput(limit=10, include_body=True, render_mode="forensic")
        result = await fn(params)
        data = json.loads(result)

        assert data["emails"][0]["body_text"] == "Full forensic body for uid-1."
        assert data["emails"][0]["body_render_mode"] == "forensic"

    @pytest.mark.asyncio
    async def test_email_browse_include_body_surfaces_weak_message(self):
        from src.tools import browse

        try:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = 'source_shell_only',
                       recovery_strategy = 'source_shell_summary',
                       recovery_confidence = 0.2
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

            fake_mcp = _register_module(browse)
            fn = fake_mcp._tools["email_browse"]

            from src.mcp_models import BrowseInput

            params = BrowseInput(limit=10, include_body=True)
            result = await fn(params)
            data = json.loads(result)

            weak_message = data["emails"][0]["weak_message"]
            assert weak_message["code"] == "source_shell_only"
            assert weak_message["label"] == "Source-shell message"
        finally:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = '',
                       recovery_strategy = '',
                       recovery_confidence = 1.0
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

    @pytest.mark.asyncio
    async def test_email_deep_context_basic(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(
            uid="uid-1",
            include_thread=True,
            include_evidence=True,
            include_sender_stats=True,
        )
        result = await fn(params)
        data = json.loads(result)

        assert "email" in data
        assert data["email"]["uid"] == "uid-1"
        assert "thread" in data
        assert "evidence" in data
        assert "sender" in data

    @pytest.mark.asyncio
    async def test_email_deep_context_surfaces_weak_message(self):
        from src.tools import browse

        try:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = 'metadata_only_reply',
                       recovery_strategy = 'metadata_summary',
                       recovery_confidence = 0.2
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

            fake_mcp = _register_module(browse)
            fn = fake_mcp._tools["email_deep_context"]

            from src.mcp_models import EmailDeepContextInput

            result = await fn(EmailDeepContextInput(uid="uid-1"))
            data = json.loads(result)

            weak_message = data["email"]["weak_message"]
            assert weak_message["code"] == "metadata_only_reply"
            assert weak_message["label"] == "Metadata-only reply"
        finally:
            MockDeps._email_db.conn.execute(
                """UPDATE emails
                   SET body_kind = 'content',
                       body_empty_reason = '',
                       recovery_strategy = '',
                       recovery_confidence = 1.0
                   WHERE uid = 'uid-1'"""
            )
            MockDeps._email_db.conn.commit()

    @pytest.mark.asyncio
    async def test_email_deep_context_not_found(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(uid="nonexistent-uid")
        result = await fn(params)
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_email_deep_context_no_thread(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(
            uid="uid-1",
            include_thread=False,
            include_evidence=False,
            include_sender_stats=False,
        )
        result = await fn(params)
        data = json.loads(result)

        assert "email" in data
        assert "thread" not in data
        assert "evidence" not in data
        assert "sender" not in data

    @pytest.mark.asyncio
    async def test_email_deep_context_conversation_debug(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_deep_context"]

        from src.mcp_models import EmailDeepContextInput

        params = EmailDeepContextInput(
            uid="uid-2",
            include_thread=False,
            include_evidence=False,
            include_sender_stats=False,
            include_conversation_debug=True,
            render_mode="forensic",
        )
        result = await fn(params)
        data = json.loads(result)

        assert data["email"]["body_text"] == "Full forensic body for uid-2."
        assert data["email"]["body_render_mode"] == "forensic"
        assert "conversation_debug" in data
        assert data["conversation_debug"]["segment_count"] == 0
        assert data["conversation_debug"]["canonical_thread"]["conversation_id"] == "conv-1"
        assert data["conversation_debug"]["canonical_thread"]["in_reply_to"] == "budget-parent@example.com"
        assert data["conversation_debug"]["canonical_thread"]["references"] == [
            "budget-root@example.com",
            "budget-parent@example.com",
        ]
        assert data["conversation_debug"]["inferred_thread"]["parent_uid"] == "uid-1"

    @pytest.mark.asyncio
    async def test_email_deep_context_budget_compaction_keeps_body_surface(self, monkeypatch):
        from src.tools import browse

        get_settings.cache_clear()
        monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "500")
        try:
            MockDeps._email_db.conn.execute(
                "UPDATE emails SET body_text = ? WHERE uid = 'uid-1'",
                ("x" * 4000,),
            )
            MockDeps._email_db.conn.commit()
            fake_mcp = _register_module(browse)
            fn = fake_mcp._tools["email_deep_context"]

            from src.mcp_models import EmailDeepContextInput

            result = await fn(
                EmailDeepContextInput(
                    uid="uid-1",
                    include_thread=True,
                    include_evidence=True,
                    include_sender_stats=True,
                    include_conversation_debug=True,
                )
            )
            data = json.loads(result)
            assert data["email"]["uid"] == "uid-1"
            assert data["email"]["body_text"] != ""
            assert data["email"]["body_total_chars"] >= len(data["email"]["body_text"])
        finally:
            MockDeps._email_db.conn.execute(
                "UPDATE emails SET body_text = ? WHERE uid = 'uid-1'",
                ("We decided to go with vendor A.",),
            )
            MockDeps._email_db.conn.commit()
            get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_email_export_single_html(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        with patch("src.email_exporter.EmailExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_single_html.return_value = {
                "html": "<html>email</html>",
                "uid": "uid-1",
            }
            mock_cls.return_value = mock_exporter

            params = EmailExportInput(uid="uid-1")
            result = await fn(params)
            data = json.loads(result)

            assert "uid" in data or "html" in data

    @pytest.mark.asyncio
    async def test_email_export_forensic_mode(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        with patch("src.email_exporter.EmailExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_single_html.return_value = {
                "html": "<html>forensic</html>",
                "uid": "uid-1",
                "render_mode": "forensic",
            }
            mock_cls.return_value = mock_exporter

            params = EmailExportInput(uid="uid-1", render_mode="forensic")
            result = await fn(params)
            data = json.loads(result)

            mock_exporter.export_single_html.assert_called_once_with("uid-1", render_mode="forensic")
            assert data["render_mode"] == "forensic"

    @pytest.mark.asyncio
    async def test_email_export_thread_html(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        with patch("src.email_exporter.EmailExporter") as mock_cls:
            mock_exporter = MagicMock()
            mock_exporter.export_thread_html.return_value = {
                "html": "<html>thread</html>",
                "conversation_id": "conv-1",
                "email_count": 2,
            }
            mock_cls.return_value = mock_exporter

            params = EmailExportInput(conversation_id="conv-1")
            result = await fn(params)
            data = json.loads(result)

            assert "conversation_id" in data or "html" in data

    @pytest.mark.asyncio
    async def test_email_export_rejects_pdf_without_output_path_even_if_validation_is_bypassed(self):
        from src.tools import browse

        fake_mcp = _register_module(browse)
        fn = fake_mcp._tools["email_export"]

        from src.mcp_models import EmailExportInput

        params = EmailExportInput.model_construct(uid="uid-1", conversation_id=None, output_path=None, format="pdf")
        result = await fn(params)
        data = json.loads(result)

        assert data["error"] == "pdf export requires output_path; omit output_path only for in-memory HTML export."


class TestScanTools:
    def setup_method(self):
        """Reset scan sessions between tests."""
        from src import scan_session

        scan_session.reset_all_sessions()

    @pytest.mark.asyncio
    async def test_scan_flag_and_status(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Flag some candidates
        params = EmailScanInput(
            action="flag",
            scan_id="test_case",
            uids=["uid-1", "uid-2"],
            label="relevant",
            phase=1,
        )
        result = await fn(params)
        data = json.loads(result)

        assert data["flagged"] == 2
        assert data["total_candidates"] == 2
        assert data["scan_id"] == "test_case"

        # Check status
        params = EmailScanInput(action="status", scan_id="test_case")
        result = await fn(params)
        data = json.loads(result)

        assert data["scan_id"] == "test_case"
        assert data["candidate_count"] == 2
        assert data["seen_count"] >= 2

    @pytest.mark.asyncio
    async def test_scan_candidates(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Flag first
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="case2",
                uids=["uid-a", "uid-b"],
                label="bossing",
                phase=1,
            )
        )

        # Get candidates
        params = EmailScanInput(action="candidates", scan_id="case2")
        result = await fn(params)
        data = json.loads(result)

        assert "candidates" in data
        assert data["count"] == 2
        assert all(c["label"] == "bossing" for c in data["candidates"])

    @pytest.mark.asyncio
    async def test_scan_candidates_filtered_by_label(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        await fn(
            EmailScanInput(
                action="flag",
                scan_id="case3",
                uids=["uid-1"],
                label="bossing",
                phase=1,
            )
        )
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="case3",
                uids=["uid-2"],
                label="harassment",
                phase=2,
            )
        )

        # Filter by label
        params = EmailScanInput(
            action="candidates",
            scan_id="case3",
            label="bossing",
        )
        result = await fn(params)
        data = json.loads(result)

        assert data["count"] == 1
        assert data["candidates"][0]["label"] == "bossing"

    @pytest.mark.asyncio
    async def test_scan_reset(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Create a session
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="reset_test",
                uids=["uid-1"],
                label="test",
                phase=1,
            )
        )

        # Reset it
        params = EmailScanInput(action="reset", scan_id="reset_test")
        result = await fn(params)
        data = json.loads(result)

        assert data["reset"] == "reset_test"
        assert data["existed"] is True

        # Status should fail now
        params = EmailScanInput(action="status", scan_id="reset_test")
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_scan_reset_all(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        # Create sessions
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="s1",
                uids=["uid-1"],
                label="test",
                phase=1,
            )
        )
        await fn(
            EmailScanInput(
                action="flag",
                scan_id="s2",
                uids=["uid-2"],
                label="test",
                phase=1,
            )
        )

        # Reset all
        params = EmailScanInput(action="reset", scan_id="__all__")
        result = await fn(params)
        data = json.loads(result)

        assert data["reset"] == "all"
        assert data["sessions_cleared"] >= 2

    @pytest.mark.asyncio
    async def test_scan_flag_missing_uids(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        params = EmailScanInput(
            action="flag",
            scan_id="test",
            label="test",
        )
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_scan_flag_missing_label(self):
        from src.tools import scan

        fake_mcp = FakeMCP()
        scan.register(fake_mcp, MockDeps)
        fn = fake_mcp._tools["email_scan"]

        from src.mcp_models import EmailScanInput

        params = EmailScanInput(
            action="flag",
            scan_id="test",
            uids=["uid-1"],
        )
        result = await fn(params)
        data = json.loads(result)
        assert "error" in data

    def test_scan_invalid_action(self):
        from pydantic import ValidationError

        from src.mcp_models import EmailScanInput

        # Literal validation rejects invalid actions at parse time
        with pytest.raises(ValidationError, match="action"):
            EmailScanInput(action="destroy", scan_id="test")
