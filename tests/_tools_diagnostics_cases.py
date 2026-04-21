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


class MockRetriever:
    """Minimal retriever stub with embedder attribute for diagnostics."""

    def __init__(self):
        self.embedder = MagicMock()
        self.embedder.device = "cpu"
        self.embedder._model = MagicMock()
        self.embedder.has_sparse = False
        self.embedder.has_colbert = False
        self.embedder.runtime_summary.return_value = {
            "backend": "fake",
            "device": "cpu",
            "batch_size": 16,
            "load_mode": "local_only",
            "has_sparse": False,
            "has_colbert": False,
        }


class MockEmailDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def sparse_vector_count(self):
        return 42


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
    from src.tools import diagnostics

    fake_mcp = FakeMCP()
    diagnostics.register(fake_mcp, MockDeps)
    return fake_mcp


# ── Tests ────────────────────────────────────────────────────


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
            conn = sqlite3.connect(":memory:")

        MockDeps._email_db = MinimalDB()
        try:
            from src.mcp_models import EmailAdminInput

            params = EmailAdminInput(action="diagnostics")
            result = await fn(params)
            data = json.loads(result)
            assert data["sparse_vector_count"] == 0
        finally:
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
                        ("u1", "content", "", "source_header", "alice@example.com", "parent-1"),
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

        MockDeps._email_db = RichDB()
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
                            "alice@example.com",
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

        MockDeps._email_db = ReadinessDB()
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
            MockDeps._email_db = old_db

    @pytest.mark.asyncio
    async def test_diagnostics_includes_answer_task_readiness_from_eval_report(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        report_path = tmp_path / "qa_eval_report.core.captured.json"
        report_path.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {
                            "attachment_lookup": 2,
                            "fact_lookup": 4,
                            "thread_process": 2,
                            "ambiguity_stress": 2,
                        },
                        "top_1_correctness": {"scorable": 10, "passed": 9, "failed": 1},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.925},
                        "attachment_answer_success": {"scorable": 2, "passed": 2, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 2, "passed": 1, "failed": 1},
                        "attachment_ocr_text_evidence_success": {"scorable": 1, "passed": 1, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 9, "failed": 1},
                        "weak_evidence_explained": {"scorable": 2, "passed": 2, "failed": 0},
                        "quote_attribution_precision": {"scorable": 2, "average": 0.75},
                        "quote_attribution_coverage": {"scorable": 2, "average": 1.0},
                        "thread_group_id_match": {"scorable": 2, "passed": 2, "failed": 0},
                        "thread_group_source_match": {"scorable": 2, "passed": 1, "failed": 1},
                    }
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [report_path])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["source_report"].endswith("qa_eval_report.core.captured.json")
        assert readiness["total_cases"] == 10
        assert readiness["bucket_counts"]["fact_lookup"] == 4
        assert readiness["top_1_correctness"]["passed"] == 9
        assert readiness["top_1_correctness"]["pass_rate"] == pytest.approx(0.9, rel=1e-6)
        assert readiness["support_uid_hit_top_3"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["evidence_precision"]["average"] == pytest.approx(0.925, rel=1e-6)
        assert readiness["attachment_answer_success"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["attachment_text_evidence_success"]["pass_rate"] == pytest.approx(0.5, rel=1e-6)
        assert readiness["attachment_ocr_text_evidence_success"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["confidence_calibration_match"]["pass_rate"] == pytest.approx(0.9, rel=1e-6)
        assert readiness["weak_evidence_explained"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["quote_attribution_precision"]["available"] is True
        assert readiness["quote_attribution_precision"]["average"] == pytest.approx(0.75, rel=1e-6)
        assert readiness["quote_attribution_coverage"]["available"] is True
        assert readiness["quote_attribution_coverage"]["average"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["thread_group_id_match"]["source_report"].endswith("qa_eval_report.core.captured.json")
        assert readiness["thread_group_id_match"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["thread_group_source_match"]["pass_rate"] == pytest.approx(0.5, rel=1e-6)

    @pytest.mark.asyncio
    async def test_diagnostics_prefers_thread_metrics_from_specialized_report(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        inferred_report = tmp_path / "qa_eval_report.inferred_thread.captured.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        inferred_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "thread_group_id_match": {"scorable": 2, "passed": 2, "failed": 0},
                        "thread_group_source_match": {"scorable": 2, "passed": 2, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report, inferred_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["thread_group_id_match"]["source_report"].endswith("qa_eval_report.inferred_thread.captured.json")
        assert readiness["thread_group_id_match"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["thread_group_source_match"]["source_report"].endswith("qa_eval_report.inferred_thread.captured.json")

    @pytest.mark.asyncio
    async def test_diagnostics_prefers_live_thread_metrics_over_captured_specialized_report(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        inferred_captured_report = tmp_path / "qa_eval_report.inferred_thread.captured.json"
        inferred_live_report = tmp_path / "qa_eval_report.inferred_thread.live.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        inferred_captured_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "thread_group_id_match": {"scorable": 2, "passed": 2, "failed": 0},
                        "thread_group_source_match": {"scorable": 2, "passed": 2, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        inferred_live_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "thread_group_id_match": {"scorable": 2, "passed": 1, "failed": 1},
                        "thread_group_source_match": {"scorable": 2, "passed": 1, "failed": 1},
                    }
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(
            diagnostics,
            "_qa_eval_report_candidates",
            lambda: [core_report, inferred_captured_report, inferred_live_report],
        )

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["thread_group_id_match"]["source_report"].endswith("qa_eval_report.inferred_thread.live.json")
        assert readiness["thread_group_id_match"]["pass_rate"] == pytest.approx(0.5, rel=1e-6)
        assert readiness["thread_group_source_match"]["source_report"].endswith("qa_eval_report.inferred_thread.live.json")

    @pytest.mark.asyncio
    async def test_diagnostics_includes_natural_inferred_thread_prevalence(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        prevalence_report = tmp_path / "qa_eval_inferred_thread_prevalence.live.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        prevalence_report.write_text(
            json.dumps(
                {
                    "artifact_type": "natural_inferred_thread_prevalence",
                    "sample_email_count": 1500,
                    "emails_with_inferred_thread_id": 0,
                    "emails_with_inferred_parent_uid": 0,
                    "inferred_only_email_count": 0,
                    "distinct_inferred_thread_ids": 0,
                    "inferred_thread_id_rate": 0.0,
                    "inferred_parent_uid_rate": 0.0,
                    "inferred_only_email_rate": 0.0,
                    "decision": "deprioritize",
                    "recommendation": "Natural inferred-thread prevalence is zero on the measured slice.",
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report])
        monkeypatch.setattr(diagnostics, "_inferred_thread_prevalence_candidates", lambda: [prevalence_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["natural_inferred_thread_prevalence"]["source_report"].endswith(
            "qa_eval_inferred_thread_prevalence.live.json"
        )
        assert readiness["natural_inferred_thread_prevalence"]["sample_email_count"] == 1500
        assert readiness["natural_inferred_thread_prevalence"]["inferred_only_email_count"] == 0
        assert readiness["natural_inferred_thread_prevalence"]["decision"] == "deprioritize"

    @pytest.mark.asyncio
    async def test_diagnostics_prefers_long_thread_metrics_from_specialized_live_report(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        long_thread_report = tmp_path / "qa_eval_report.long_thread.live.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "long_thread_answer_present": {"scorable": 0, "passed": 0, "failed": 0},
                        "long_thread_structure_preserved": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        long_thread_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "long_thread_answer_present": {"scorable": 2, "passed": 2, "failed": 0},
                        "long_thread_structure_preserved": {"scorable": 2, "passed": 2, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report, long_thread_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["long_thread_answer_present"]["source_report"].endswith("qa_eval_report.long_thread.live.json")
        assert readiness["long_thread_answer_present"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
        assert readiness["long_thread_structure_preserved"]["source_report"].endswith("qa_eval_report.long_thread.live.json")

    @pytest.mark.asyncio
    async def test_diagnostics_prefers_attachment_ocr_metrics_from_specialized_report(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        attachment_ocr_report = tmp_path / "qa_eval_report.attachment_ocr.captured.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 2, "passed": 2, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 2, "passed": 0, "failed": 2},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        attachment_ocr_report.write_text(
            json.dumps({"summary": {"attachment_ocr_text_evidence_success": {"scorable": 2, "passed": 1, "failed": 1}}}),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report, attachment_ocr_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["attachment_ocr_text_evidence_success"]["source_report"].endswith(
            "qa_eval_report.attachment_ocr.captured.json"
        )
        assert readiness["attachment_ocr_text_evidence_success"]["pass_rate"] == pytest.approx(0.5, rel=1e-6)

    @pytest.mark.asyncio
    async def test_diagnostics_includes_remediation_summary_from_saved_artifact(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.live_expanded.live.json"
        remediation_report = tmp_path / "qa_eval_remediation.live_expanded.live.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 18,
                        "bucket_counts": {"fact_lookup": 6},
                        "top_1_correctness": {"scorable": 18, "passed": 2, "failed": 16},
                        "support_uid_hit_top_3": {"scorable": 18, "passed": 3, "failed": 15},
                        "evidence_precision": {"scorable": 4, "average": 0.56},
                        "attachment_answer_success": {"scorable": 4, "passed": 0, "failed": 4},
                        "attachment_text_evidence_success": {"scorable": 4, "passed": 0, "failed": 4},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 18, "passed": 4, "failed": 14},
                        "weak_evidence_explained": {"scorable": 4, "passed": 0, "failed": 4},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        remediation_report.write_text(
            json.dumps(
                {
                    "total_cases": 18,
                    "failure_taxonomy": {
                        "total_flagged_cases": 18,
                        "ranked_categories": [
                            {
                                "category": "retrieval_recall",
                                "priority_score": 32,
                                "flagged_cases": 8,
                                "failed_cases": 7,
                                "weak_cases": 1,
                                "case_ids": ["fact-101"],
                                "drivers": ["no_supported_hit"],
                                "recommended_track": "retrieval_quality",
                                "recommended_next_step": "define and implement retrieval-quality remediation after AQ20",
                            }
                        ],
                    },
                    "immediate_next_targets": [
                        {
                            "category": "retrieval_recall",
                            "recommended_track": "retrieval_quality",
                            "recommended_next_step": "define and implement retrieval-quality remediation after AQ20",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report])
        monkeypatch.setattr(diagnostics, "_qa_eval_remediation_candidates", lambda: [remediation_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["remediation_summary"]["source_report"].endswith("qa_eval_remediation.live_expanded.live.json")
        assert readiness["remediation_summary"]["ranked_categories"][0]["category"] == "retrieval_recall"
        assert readiness["remediation_summary"]["immediate_next_targets"][0]["recommended_track"] == "retrieval_quality"

    @pytest.mark.asyncio
    async def test_diagnostics_includes_investigation_case_analysis_readiness(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        investigation_report = tmp_path / "qa_eval_report.investigation.live.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "case_bundle_present": {"scorable": 0, "passed": 0, "failed": 0},
                        "investigation_blocks_present": {"scorable": 0, "passed": 0, "failed": 0},
                        "case_bundle_support_uid_hit": {"scorable": 0, "passed": 0, "failed": 0},
                        "case_bundle_support_uid_recall": {"scorable": 0, "average": 0.0},
                        "multi_source_source_types_match": {"scorable": 0, "passed": 0, "failed": 0},
                    }
                }
            ),
            encoding="utf-8",
        )
        investigation_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "case_bundle_present": {"scorable": 2, "passed": 2, "failed": 0},
                        "investigation_blocks_present": {"scorable": 2, "passed": 2, "failed": 0},
                        "case_bundle_support_uid_hit": {"scorable": 2, "passed": 2, "failed": 0},
                        "case_bundle_support_uid_recall": {"scorable": 2, "average": 1.0},
                        "multi_source_source_types_match": {"scorable": 2, "passed": 2, "failed": 0},
                    },
                    "investigation_corpus_readiness": {
                        "live_backend": "sqlite_fallback",
                        "case_scope_case_count": 2,
                        "expected_case_bundle_uid_count": 4,
                        "total_emails": 400,
                        "emails_with_segments_count": 400,
                        "attachment_email_count": 40,
                        "corpus_populated": True,
                        "supports_case_analysis": True,
                        "known_blockers": [],
                    },
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report, investigation_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["investigation_case_analysis"]["source_report"].endswith(
            "qa_eval_report.investigation.live.json"
        )
        assert readiness["investigation_case_analysis"]["case_bundle_present"]["pass_rate"] == pytest.approx(
            1.0, rel=1e-6
        )
        assert readiness["investigation_case_analysis"]["case_bundle_support_uid_recall"]["average"] == pytest.approx(
            1.0, rel=1e-6
        )
        assert readiness["investigation_corpus_readiness"]["supports_case_analysis"] is True
        assert readiness["investigation_corpus_readiness"]["case_scope_case_count"] == 2

    @pytest.mark.asyncio
    async def test_diagnostics_includes_behavioral_analysis_benchmark(self, monkeypatch, tmp_path):
        fake_mcp = _register()
        fn = fake_mcp._tools["email_admin"]
        core_report = tmp_path / "qa_eval_report.core.captured.json"
        behavioral_report = tmp_path / "qa_eval_report.behavioral_analysis.captured.json"
        core_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_cases": 10,
                        "bucket_counts": {"fact_lookup": 4},
                        "top_1_correctness": {"scorable": 10, "passed": 10, "failed": 0},
                        "support_uid_hit_top_3": {"scorable": 10, "passed": 10, "failed": 0},
                        "evidence_precision": {"scorable": 10, "average": 0.9},
                        "attachment_answer_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "attachment_ocr_text_evidence_success": {"scorable": 0, "passed": 0, "failed": 0},
                        "confidence_calibration_match": {"scorable": 10, "passed": 10, "failed": 0},
                        "weak_evidence_explained": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_id_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "thread_group_source_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "behavior_tag_coverage": {"scorable": 0, "average": 0.0},
                        "behavior_tag_precision": {"scorable": 0, "average": 0.0},
                        "counter_indicator_quality": {"scorable": 0, "average": 0.0},
                        "overclaim_guard_match": {"scorable": 0, "passed": 0, "failed": 0},
                        "report_completeness": {"scorable": 0, "passed": 0, "failed": 0},
                        "chronology_uid_hit": {"scorable": 0, "passed": 0, "failed": 0},
                        "chronology_uid_recall": {"scorable": 0, "average": 0.0},
                    }
                }
            ),
            encoding="utf-8",
        )
        behavioral_report.write_text(
            json.dumps(
                {
                    "summary": {
                        "behavior_tag_coverage": {"scorable": 6, "average": 0.8333333333},
                        "behavior_tag_precision": {"scorable": 6, "average": 0.9166666667},
                        "counter_indicator_quality": {"scorable": 4, "average": 0.75},
                        "overclaim_guard_match": {"scorable": 6, "passed": 5, "failed": 1},
                        "report_completeness": {"scorable": 6, "passed": 6, "failed": 0},
                        "chronology_uid_hit": {"scorable": 4, "passed": 4, "failed": 0},
                        "chronology_uid_recall": {"scorable": 4, "average": 1.0},
                    }
                }
            ),
            encoding="utf-8",
        )

        from src.mcp_models import EmailAdminInput
        from src.tools import diagnostics

        monkeypatch.setattr(diagnostics, "_qa_eval_report_candidates", lambda: [core_report, behavioral_report])

        result = await fn(EmailAdminInput(action="diagnostics"))
        data = json.loads(result)
        readiness = data["answer_task_readiness"]

        assert readiness["behavioral_analysis_benchmark"]["available"] is True
        assert readiness["behavioral_analysis_benchmark"]["source_report"].endswith(
            "qa_eval_report.behavioral_analysis.captured.json"
        )
        assert readiness["behavioral_analysis_benchmark"]["behavior_tag_coverage"]["average"] == pytest.approx(
            0.8333333333, rel=1e-6
        )
        assert readiness["behavioral_analysis_benchmark"]["overclaim_guard_match"]["pass_rate"] == pytest.approx(
            5 / 6, rel=1e-6
        )


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
