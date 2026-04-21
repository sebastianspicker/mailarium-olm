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


class TestDiagnostics:
    def test_answer_task_readiness_summary_delegates_to_summary_module(self):
        from src.tools import diagnostics

        expected = {"source_report": "x"}
        with patch("src.tools.diagnostics_summary.answer_task_readiness_summary_impl", return_value=expected) as mock_impl:
            assert diagnostics._answer_task_readiness_summary() == expected
        mock_impl.assert_called_once()

    def test_qa_readiness_summary_delegates_to_summary_module(self):
        from src.tools import diagnostics

        fake_db = object()
        expected = {"total_emails": 1}
        with patch("src.tools.diagnostics_summary.qa_readiness_summary_impl", return_value=expected) as mock_impl:
            assert diagnostics._qa_readiness_summary(fake_db) == expected
        mock_impl.assert_called_once_with(
            fake_db,
            table_columns=diagnostics._table_columns,
            scalar_count=diagnostics._scalar_count,
            count_rows=diagnostics._count_rows,
            rate=diagnostics._rate,
        )

    def test_diagnostics_docstrings_describe_runtime_summary(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models_analysis import EmailAdminInput

        assert "resolved runtime settings" in (fn.__doc__ or "")
        assert "embedder state" in (EmailAdminInput.__doc__ or "")

    @pytest.mark.asyncio
    async def test_diagnostics_action(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        params = EmailAdminInput(action="diagnostics")
        result = await fn(params)
        data = json.loads(result)
        assert "embedding_model" in data
        assert "runtime_profile" in data
        assert "embedding_load_mode" in data
        assert "resolved_device" in data
        assert "resolved_batch_size" in data
        assert "embedder_device" in data
        assert "embedder_batch_size" in data
        assert "embedder_load_mode" in data
        assert "embedder_backend" in data
        assert "mcp_profile" in data
        assert "mcp_budget" in data
        assert "sparse_vector_count" in data
        assert data["sparse_vector_count"] == 42
        assert "device" not in data
        assert "batch_size" not in data
        assert "load_mode" not in data

    @pytest.mark.asyncio
    async def test_diagnostics_without_sparse_count(self):
        """DB without sparse_vector_count method still works."""
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        old_db = MockDeps._email_db

        class MinimalDB:
            def __init__(self):
                self.conn = sqlite3.connect(":memory:")

            def close(self) -> None:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None

        temp_db = MinimalDB()
        MockDeps._email_db = temp_db
        try:
            from src.mcp_models import EmailAdminInput

            params = EmailAdminInput(action="diagnostics")
            result = await fn(params)
            data = json.loads(result)
            assert data["sparse_vector_count"] == 0
        finally:
            temp_db.close()
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_diagnostics_namespaces_embedder_summary(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        from src.mcp_models import EmailAdminInput

        params = EmailAdminInput(action="diagnostics")
        result = await fn(params)
        data = json.loads(result)
        assert data["resolved_batch_size"] >= 1
        assert data["embedder_batch_size"] == 16
        assert data["embedder_device"] == "cpu"
        assert data["embedder_load_mode"] == "local_only"

    @pytest.mark.asyncio
    async def test_diagnostics_includes_parser_layer_counters(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        old_db = MockDeps._email_db

        class RichDB:
            def __init__(self):
                self.conn = sqlite3.connect(":memory:", check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute(
                    "CREATE TABLE emails ("
                    "uid TEXT, body_kind TEXT, body_empty_reason TEXT, "
                    "recipient_identity_source TEXT, reply_context_from TEXT, inferred_parent_uid TEXT)"
                )
                self.conn.execute("CREATE TABLE message_segments (email_uid TEXT)")
                self.conn.executemany(
                    "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        ("u1", "content", "", "source_header", "employee@example.test", "parent-1"),
                        ("u2", "metadata_only", "metadata_only_reply", "structured_xml", "", ""),
                        ("u3", "empty", "html_shell_only", "", "", ""),
                    ],
                )
                self.conn.executemany(
                    "INSERT INTO message_segments VALUES (?)",
                    [("u1",), ("u1",), ("u2",)],
                )

            def sparse_vector_count(self):
                return 0

            def close(self) -> None:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None

        temp_db = RichDB()
        MockDeps._email_db = temp_db
        try:
            from src.mcp_models import EmailAdminInput

            params = EmailAdminInput(action="diagnostics")
            result = await fn(params)
            data = json.loads(result)

            assert data["body_kind_counts"]["content"] == 1
            assert data["body_kind_counts"]["metadata_only"] == 1
            assert data["body_empty_reason_counts"]["metadata_only_reply"] == 1
            assert data["recipient_identity_source_counts"]["source_header"] == 1
            assert data["reply_context_recovered_count"] == 1
            assert data["message_segment_count"] == 3
            assert data["emails_with_inferred_thread_count"] == 1
        finally:
            temp_db.close()
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_diagnostics_includes_answer_readiness_summary(self):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        old_db = MockDeps._email_db

        class ReadinessDB:
            def __init__(self):
                self.conn = sqlite3.connect(":memory:", check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute(
                    "CREATE TABLE emails ("
                    "uid TEXT, email_type TEXT, has_attachments INTEGER, conversation_id TEXT, "
                    "in_reply_to TEXT, references_json TEXT, raw_source TEXT, "
                    "forensic_body_text TEXT, body_kind TEXT, body_empty_reason TEXT, "
                    "recipient_identity_source TEXT, reply_context_from TEXT, inferred_parent_uid TEXT)"
                )
                self.conn.execute("CREATE TABLE message_segments (email_uid TEXT)")
                self.conn.executemany(
                    "INSERT INTO emails VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            "u1",
                            "reply",
                            1,
                            "thread-1",
                            "parent-1",
                            '["ref-1"]',
                            "raw-source-1",
                            "forensic-1",
                            "content",
                            "",
                            "source_header",
                            "employee@example.test",
                            "parent-1",
                        ),
                        (
                            "u2",
                            "forward",
                            0,
                            "thread-1",
                            "",
                            "[]",
                            "",
                            "",
                            "metadata_only",
                            "metadata_only_reply",
                            "structured_xml",
                            "",
                            "",
                        ),
                        (
                            "u3",
                            "original",
                            1,
                            "",
                            "",
                            "[]",
                            "raw-source-3",
                            "",
                            "empty",
                            "image_only",
                            "",
                            "",
                            "",
                        ),
                    ],
                )
                self.conn.executemany(
                    "INSERT INTO message_segments VALUES (?)",
                    [("u1",), ("u1",), ("u2",)],
                )

            def sparse_vector_count(self):
                return 0

            def close(self) -> None:
                if self.conn is not None:
                    self.conn.close()
                    self.conn = None

        temp_db = ReadinessDB()
        MockDeps._email_db = temp_db
        try:
            from src.mcp_models import EmailAdminInput

            params = EmailAdminInput(action="diagnostics")
            result = await fn(params)
            data = json.loads(result)
            readiness = data["qa_readiness"]

            assert readiness["total_emails"] == 3
            assert readiness["content_email_count"] == 1
            assert readiness["attachment_email_count"] == 2
            assert readiness["forensic_body_count"] == 1
            assert readiness["raw_source_count"] == 2
            assert readiness["emails_with_segments_count"] == 2
            assert readiness["reply_or_forward_count"] == 2
            assert readiness["reply_context_recovered_count"] == 1
            assert readiness["canonical_thread_linked_count"] == 1
            assert readiness["inferred_thread_linked_count"] == 1
            assert readiness["content_email_rate"] == pytest.approx(1 / 3, rel=1e-6)
            assert readiness["attachment_email_rate"] == pytest.approx(2 / 3, rel=1e-6)
            assert readiness["segment_provenance_rate"] == pytest.approx(2 / 3, rel=1e-6)
            assert readiness["reply_context_recovery_rate"] == pytest.approx(0.5, rel=1e-6)
            assert readiness["canonical_thread_link_rate"] == pytest.approx(1 / 3, rel=1e-6)
            assert readiness["inferred_thread_link_rate"] == pytest.approx(1 / 3, rel=1e-6)
            assert readiness["top_body_empty_reasons"][0] == {
                "label": "image_only",
                "count": 1,
            }
            assert readiness["top_body_empty_reasons"][1] == {
                "label": "metadata_only_reply",
                "count": 1,
            }
        finally:
            temp_db.close()
            MockDeps._email_db = old_db
