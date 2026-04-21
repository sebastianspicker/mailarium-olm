from __future__ import annotations

import json
from typing import Any, cast

import pytest

from tests.helpers.mcp_tool_extended_fakes import _register_module


def _legal_support_payload() -> dict[str, object]:
    return {
        "workflow": "case_analysis",
        "review_mode": "exhaustive_matter_review",
        "review_classification": {
            "classification": "counsel_grade_exhaustive_review",
            "may_be_presented_as_full_matter_review": True,
        },
        "analysis_query": "workplace case analysis. target employee",
        "privacy_guardrails": {"privacy_mode": "external_counsel_export"},
        "case_scope_quality": {"status": "degraded", "warnings": [], "downgrade_reasons": []},
        "analysis_limits": {"status": "bounded"},
        "matter_coverage_ledger": {"summary": {"coverage_status": "complete", "total_source_count": 2}},
        "matter_persistence": {
            "snapshot_id": "snapshot:case123",
            "workspace_id": "workspace:case123",
            "matter_id": "matter:case123",
            "review_state": "human_verified",
            "last_approved_snapshot_id": "",
            "changes_since_last_approved": None,
        },
        "matter_ingestion_report": {
            "completeness_status": "complete",
            "summary": {"total_supplied_artifacts": 2},
        },
        "matter_evidence_index": {
            "row_count": 1,
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "date": "2025-03-11",
                    "document_type": "email",
                    "sender_or_author": "actor-manager",
                    "recipients": ["employee@example.test"],
                    "short_description": "Status email about SBV participation.",
                    "main_issue_tags": ["sbv_participation"],
                    "why_it_matters": "Supports participation review.",
                    "exhibit_reliability": {"strength": "strong", "next_step_logic": {"readiness": "usable_now"}},
                    "source_conflict_status": "stable",
                    "source_conflict_ids": [],
                    "supporting_citation_ids": ["c-1"],
                    "follow_up_needed": [],
                }
            ],
        },
        "master_chronology": {
            "entry_count": 1,
            "summary": {"source_conflict_registry": {"conflict_count": 0, "conflicts": []}},
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2025-03-11",
                    "title": "Status",
                    "description": "Status email sent after complaint.",
                    "fact_stability": "stable",
                    "source_linkage": {"source_ids": ["email:uid-1"]},
                }
            ],
        },
        "lawyer_issue_matrix": {"row_count": 1, "rows": [{"issue_id": "retaliation"}]},
        "skeptical_employer_review": {"summary": {"weakness_count": 1}, "weaknesses": [{"weakness_id": "w-1"}]},
        "document_request_checklist": {
            "group_count": 1,
            "groups": [{"group_id": "g-1", "group_title": "Records", "items": [{"requested_record": "SBV file"}]}],
        },
        "actor_map": {"actor_count": 1, "actors": [{"actor_id": "actor-manager"}]},
        "witness_map": {"primary_decision_makers": [{"actor_id": "actor-manager"}]},
        "promise_contradiction_analysis": {"summary": {"contradiction_row_count": 1}, "contradiction_table": [{}]},
        "lawyer_briefing_memo": {
            "memo_format": "lawyer_onboarding_brief",
            "sections": {"executive_summary": [{"entry_id": "memo-1", "text": "Key issue summary."}]},
        },
        "controlled_factual_drafting": {
            "drafting_format": "controlled_factual_drafting",
            "summary": {"preflight_ready": True},
            "framing_preflight": {
                "objective_of_draft": "Prepare an evidence-bound professional draft.",
                "allegation_ceiling": {"release_status": "ready_for_controlled_draft"},
            },
            "controlled_draft": {"tone": "firm_professional_evidence_bound"},
        },
        "retaliation_timeline_assessment": {"version": "1", "overall_evidentiary_rating": {"rating": "moderate"}},
        "comparative_treatment": {
            "summary": {"matrix_row_count": 1, "available_comparator_count": 1},
            "comparator_summaries": [
                {
                    "comparator_actor_id": "actor-comparator",
                    "comparator_email": "pat@example.org",
                    "status": "comparator_available",
                    "comparison_quality": "high",
                    "comparison_quality_label": "high_quality_comparator",
                    "comparator_matrix": {
                        "row_count": 1,
                        "rows": [
                            {
                                "issue_id": "mobile_work_approvals_or_restrictions",
                                "claimant_treatment": "Restricted",
                                "comparator_treatment": "Approved",
                                "comparison_strength": "strong",
                            }
                        ],
                    },
                }
            ],
        },
        "case_dashboard": {
            "dashboard_format": "refreshable_case_dashboard",
            "cards": {"main_claims_or_issues": [{"entry_id": "card-1", "title": "Retaliation", "summary": "Requires review."}]},
        },
        "investigation_report": {"version": "1", "sections": {"executive_summary": {"status": "supported"}}},
    }


def _legal_support_input() -> dict[str, object]:
    return {
        "case_scope": {
            "target_person": {"name": "employee", "email": "employee@example.test"},
            "allegation_focus": ["retaliation"],
            "analysis_goal": "lawyer_briefing",
            "date_from": "2025-01-01",
            "date_to": "2025-06-30",
        },
        "source_scope": "emails_only",
        "matter_manifest": {
            "manifest_id": "matter-case-1",
            "artifacts": [
                {
                    "source_id": "manifest:email:1",
                    "source_class": "formal_document",
                    "title": "Case summary",
                    "date": "2025-03-11",
                    "text": "Document text.",
                }
            ],
        },
    }


class TestLegalSupportTools:
    def test_registers_durable_legal_support_tools(self) -> None:
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)

        assert "email_case_issue_matrix" in fake_mcp._tools
        assert "email_case_evidence_index" in fake_mcp._tools
        assert "email_case_master_chronology" in fake_mcp._tools
        assert "email_case_comparator_matrix" in fake_mcp._tools
        assert "email_case_skeptical_review" in fake_mcp._tools
        assert "email_case_document_request_checklist" in fake_mcp._tools
        assert "email_case_actor_witness_map" in fake_mcp._tools
        assert "email_case_promise_contradictions" in fake_mcp._tools
        assert "email_case_lawyer_briefing_memo" in fake_mcp._tools
        assert "email_case_draft_preflight" in fake_mcp._tools
        assert "email_case_controlled_draft" in fake_mcp._tools
        assert "email_case_retaliation_timeline" in fake_mcp._tools
        assert "email_case_dashboard" in fake_mcp._tools
        assert "email_case_export" in fake_mcp._tools

    def test_registers_legal_support_products_as_idempotent_writes(self) -> None:
        from src.tools import legal_support

        captured_annotations: dict[str, dict[str, str]] = {}

        class FakeMCP:
            def tool(self, name=None, annotations=None):
                def decorator(fn):
                    captured_annotations[str(name)] = dict(annotations or {})
                    return fn

                return decorator

        class FakeDeps:
            @staticmethod
            def tool_annotations(title):
                return {"title": title, "mode": "read_only"}

            @staticmethod
            def write_tool_annotations(title):
                return {"title": title, "mode": "write"}

            @staticmethod
            def idempotent_write_annotations(title):
                return {"title": title, "mode": "idempotent_write"}

        legal_support.register(cast(Any, FakeMCP()), cast(Any, FakeDeps))

        expected_tools = {
            "email_case_issue_matrix",
            "email_case_evidence_index",
            "email_case_master_chronology",
            "email_case_comparator_matrix",
            "email_case_skeptical_review",
            "email_case_document_request_checklist",
            "email_case_actor_witness_map",
            "email_case_promise_contradictions",
            "email_case_lawyer_briefing_memo",
            "email_case_draft_preflight",
            "email_case_controlled_draft",
            "email_case_retaliation_timeline",
            "email_case_dashboard",
            "email_case_export",
        }

        assert expected_tools.issubset(captured_annotations)
        for tool_name in expected_tools:
            assert captured_annotations[tool_name]["mode"] == "idempotent_write"

    @pytest.mark.asyncio
    async def test_email_case_issue_matrix_returns_selected_product(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_issue_matrix"]

        async def fake_build_case_analysis_payload(_deps, params):
            assert params.output_mode == "full_report"
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input() | {"output_mode": "report_only"}))
        data = json.loads(result)

        assert data["workflow"] == "legal_support_product"
        assert data["product"] == "lawyer_issue_matrix"
        assert data["review_mode"] == "exhaustive_matter_review"
        assert data["review_classification"]["classification"] == "counsel_grade_exhaustive_review"
        assert data["matter_ingestion_report"]["completeness_status"] == "complete"
        assert data["privacy_guardrails"]["privacy_mode"] == "external_counsel_export"
        assert data["lawyer_issue_matrix"]["row_count"] == 1

    @pytest.mark.asyncio
    async def test_email_case_evidence_index_returns_selected_product(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_evidence_index"]

        async def fake_build_case_analysis_payload(_deps, params):
            assert params.output_mode == "full_report"
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "matter_evidence_index"
        assert data["matter_evidence_index"]["row_count"] == 1
        assert data["matter_evidence_index"]["rows"][0]["exhibit_id"] == "EXH-001"

    @pytest.mark.asyncio
    async def test_email_case_master_chronology_returns_selected_product(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_master_chronology"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "master_chronology"
        assert data["master_chronology"]["entry_count"] == 1
        assert data["master_chronology"]["entries"][0]["chronology_id"] == "CHR-001"

    @pytest.mark.asyncio
    async def test_email_case_comparator_matrix_returns_flattened_rows(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_comparator_matrix"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "comparator_matrix"
        assert data["comparator_matrix"]["row_count"] == 1
        assert data["comparator_matrix"]["rows"][0]["comparison_strength"] == "strong"
        assert data["comparator_matrix"]["rows"][0]["comparator_actor_id"] == "actor-comparator"

    @pytest.mark.asyncio
    async def test_email_case_comparator_matrix_surfaces_insufficiency_from_summary(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_comparator_matrix"]

        async def fake_build_case_analysis_payload(_deps, params):
            payload = _legal_support_payload()
            payload["comparative_treatment"] = {
                "summary": {
                    "matrix_row_count": 0,
                    "available_comparator_count": 0,
                    "status": "insufficient_comparator_scope",
                    "insufficiency_reason": "Comparator actors are missing from the current scope.",
                    "missing_inputs": ["comparator_actors"],
                },
                "comparator_summaries": [],
            }
            return payload

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "comparator_matrix"
        assert data["comparator_matrix"]["row_count"] == 0
        assert data["comparator_matrix"]["insufficiency"]["status"] == "insufficient_comparator_scope"
        assert data["comparator_matrix"]["insufficiency"]["missing_inputs"] == ["comparator_actors"]

    @pytest.mark.asyncio
    async def test_email_case_actor_witness_map_returns_both_maps(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_actor_witness_map"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "actor_and_witness_map"
        assert data["review_mode"] == "exhaustive_matter_review"
        assert data["review_classification"]["classification"] == "counsel_grade_exhaustive_review"
        assert data["matter_ingestion_report"]["summary"]["total_supplied_artifacts"] == 2
        assert data["actor_map"]["actor_count"] == 1
        assert data["witness_map"]["primary_decision_makers"][0]["actor_id"] == "actor-manager"

    @pytest.mark.asyncio
    async def test_email_case_dashboard_returns_refreshable_dashboard(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_dashboard"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "case_dashboard"
        assert data["case_dashboard"]["dashboard_format"] == "refreshable_case_dashboard"
        assert "refresh the product" in data["refresh_behavior"]

    @pytest.mark.asyncio
    async def test_email_case_retaliation_timeline_returns_assessment(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_retaliation_timeline"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "retaliation_timeline_assessment"
        assert data["retaliation_timeline_assessment"]["overall_evidentiary_rating"]["rating"] == "moderate"

    @pytest.mark.asyncio
    async def test_email_case_draft_preflight_returns_preflight(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_draft_preflight"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "draft_preflight"
        assert data["draft_preflight"]["objective_of_draft"] == "Prepare an evidence-bound professional draft."

    @pytest.mark.asyncio
    async def test_email_case_controlled_draft_returns_draft(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_controlled_draft"]

        async def fake_build_case_analysis_payload(_deps, params):
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        result = await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))
        data = json.loads(result)

        assert data["product"] == "controlled_factual_draft"
        assert data["controlled_factual_draft"]["tone"] == "firm_professional_evidence_bound"

    @pytest.mark.asyncio
    async def test_email_case_controlled_draft_rejects_unready_preflight(self, monkeypatch) -> None:
        from src.mcp_models import EmailLegalSupportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_controlled_draft"]

        async def fake_build_case_analysis_payload(_deps, params):
            payload = _legal_support_payload()
            payload["controlled_factual_drafting"] = {
                "drafting_format": "controlled_factual_drafting",
                "framing_preflight": {
                    "objective_of_draft": "Prepare an evidence-bound professional draft.",
                    "allegation_ceiling": {"release_status": "insufficient_for_controlled_draft"},
                },
                "controlled_draft": {"tone": "firm_professional_evidence_bound", "preflight_ready": False},
            }
            return payload

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)

        with pytest.raises(ValueError, match="Run email_case_draft_preflight first"):
            await fn(EmailLegalSupportInput.model_validate(_legal_support_input()))

    @pytest.mark.asyncio
    async def test_email_case_export_writes_bundle(self, monkeypatch, tmp_path) -> None:
        from src.mcp_models import EmailLegalSupportExportInput
        from src.tools import legal_support

        fake_mcp = _register_module(legal_support)
        fn = fake_mcp._tools["email_case_export"]
        recorded: list[dict[str, object]] = []

        class _RecordingDB:
            def record_matter_export(self, **kwargs):
                recorded.append(kwargs)
                return {"export_id": "export:123", **kwargs}

        class _RecordingDeps:
            @staticmethod
            def get_email_db():
                return _RecordingDB()

        async def fake_build_case_analysis_payload(_deps, params):
            assert params.output_mode == "full_report"
            return _legal_support_payload()

        monkeypatch.setattr(legal_support, "build_case_analysis_payload", fake_build_case_analysis_payload)
        monkeypatch.setattr(legal_support, "_deps", _RecordingDeps)

        result = await fn(
            EmailLegalSupportExportInput.model_validate(
                _legal_support_input()
                | {
                    "delivery_target": "counsel_handoff_bundle",
                    "delivery_format": "bundle",
                    "output_path": str(tmp_path / "handoff.zip"),
                }
            )
        )
        data = json.loads(result)

        assert data["delivery_target"] == "counsel_handoff_bundle"
        assert data["artifact_count"] >= 6
        assert data["export_metadata"]["snapshot_id"] == "snapshot:case123"
        assert data["recorded_export"]["snapshot_id"] == "snapshot:case123"
        assert recorded[0]["delivery_target"] == "counsel_handoff_bundle"
        assert (tmp_path / "handoff.zip").exists()

    def test_email_legal_support_input_rejects_retrieval_only(self) -> None:
        from src.mcp_models import EmailLegalSupportInput

        with pytest.raises(ValueError, match="Dedicated legal-support tools require review_mode='exhaustive_matter_review'"):
            EmailLegalSupportInput.model_validate(_legal_support_input() | {"review_mode": "retrieval_only"})
