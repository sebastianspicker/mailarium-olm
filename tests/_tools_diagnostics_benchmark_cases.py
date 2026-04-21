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

        assert readiness["investigation_case_analysis"]["source_report"].endswith("qa_eval_report.investigation.live.json")
        assert readiness["investigation_case_analysis"]["case_bundle_present"]["pass_rate"] == pytest.approx(1.0, rel=1e-6)
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
        assert readiness["behavioral_analysis_benchmark"]["overclaim_guard_match"]["pass_rate"] == pytest.approx(5 / 6, rel=1e-6)
