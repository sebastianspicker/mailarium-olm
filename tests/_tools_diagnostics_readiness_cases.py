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
