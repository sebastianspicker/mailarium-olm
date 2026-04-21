from __future__ import annotations

import json

import pytest

from src.case_analysis import build_case_analysis, build_case_analysis_payload
from src.mcp_models import EmailCaseAnalysisInput

from .helpers.case_analysis_fixtures import case_payload


def test_transform_case_analysis_payload_accepts_manifest_backed_native_chat_sources() -> None:
    from src.case_analysis import transform_case_analysis_payload

    payload = case_payload()
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:chat:1",
                "source_class": "chat_export",
                "title": "Teams export",
                "text": "Please keep this off email for now.",
            }
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)
    transformed = transform_case_analysis_payload({}, params)
    assert "mixed_case_file_declared_without_mixed_record_support" not in transformed["case_scope_quality"]["downgrade_reasons"]


@pytest.mark.asyncio
async def test_build_case_analysis_augments_multi_source_bundle_with_chat_logs(monkeypatch) -> None:
    payload = case_payload()
    payload["source_scope"] = "emails_and_attachments"
    payload["chat_log_entries"] = [
        {
            "source_id": "chat-1",
            "platform": "Teams",
            "title": "Teams follow-up",
            "date": "2025-03-16T10:00:00",
            "participants": ["employee@example.test", "manager@example.test"],
            "text": "Please keep this off email for now.",
            "related_email_uid": "uid-1",
        }
    ]
    params = EmailCaseAnalysisInput.model_validate(payload)

    async def fake_build_answer_context_payload(_deps, _answer_params, **kwargs):
        return {
            "case_bundle": {"scope": {"case_label": "case-123"}},
            "multi_source_case_bundle": {
                "summary": {
                    "source_count": 1,
                    "source_type_counts": {"email": 1},
                    "available_source_types": ["email"],
                    "missing_source_types": [
                        "attachment",
                        "meeting_note",
                        "chat_log",
                        "formal_document",
                        "note_record",
                        "time_record",
                        "participation_record",
                    ],
                    "link_count": 0,
                    "direct_text_source_count": 1,
                    "contradiction_ready_source_count": 1,
                },
                "sources": [
                    {
                        "source_id": "email:uid-1",
                        "source_type": "email",
                        "uid": "uid-1",
                        "source_weighting": {
                            "text_available": True,
                            "can_corroborate_or_contradict": True,
                        },
                    }
                ],
                "source_links": [],
                "source_type_profiles": [],
            },
            "candidates": [
                {
                    "uid": "uid-1",
                    "date": "2025-03-15T10:00:00",
                    "sender_name": "manager",
                    "sender_email": "manager@example.test",
                    "subject": "Status",
                    "snippet": "Please just comply with the updated process.",
                    "verification_status": "forensic_exact",
                    "provenance": {"evidence_handle": "email:uid-1"},
                    "language_rhetoric": {"authored_text": {"signal_count": 0, "signals": []}},
                    "message_findings": {"authored_text": {"behavior_candidates": [], "counter_indicators": []}},
                }
            ],
            "attachment_candidates": [],
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)

    rendered = await build_case_analysis(deps=object(), params=params)
    transformed = json.loads(rendered)

    assert transformed["multi_source_case_bundle"]["summary"]["source_type_counts"] == {"chat_log": 1, "email": 1}
    assert transformed["analysis_limits"]["missing_source_types"] == [
        "attachment",
        "meeting_note",
        "formal_document",
        "note_record",
        "time_record",
        "participation_record",
    ]
    assert "chat_log_source_type_not_available_in_current_case_bundle" not in transformed["analysis_limits"]["notes"]


@pytest.mark.asyncio
async def test_build_case_analysis_augments_multi_source_bundle_with_native_chat_exports(monkeypatch, tmp_path) -> None:
    payload = case_payload()
    export_path = tmp_path / "teams-export.html"
    export_path.write_text(
        (
            "<html><body>"
            "[2025-03-01 09:10] employee: Please keep this off email for now.\n"
            "[2025-03-01 09:12] manager: We will discuss this later."
            "</body></html>"
        ),
        encoding="utf-8",
    )
    payload["source_scope"] = "mixed_case_file"
    payload["chat_exports"] = [
        {
            "source_id": "chat-export-1",
            "source_path": str(export_path),
            "platform": "Teams",
            "title": "Teams export",
            "related_email_uid": "uid-1",
        }
    ]
    params = EmailCaseAnalysisInput.model_validate(payload)

    async def fake_build_answer_context_payload(_deps, _answer_params, **kwargs):
        return {
            "case_bundle": {"scope": {"case_label": "case-123"}},
            "multi_source_case_bundle": {
                "summary": {
                    "source_count": 1,
                    "source_type_counts": {"email": 1},
                    "available_source_types": ["email"],
                    "missing_source_types": [
                        "attachment",
                        "meeting_note",
                        "chat_log",
                        "formal_document",
                        "note_record",
                        "time_record",
                        "participation_record",
                    ],
                    "link_count": 0,
                    "direct_text_source_count": 1,
                    "contradiction_ready_source_count": 1,
                },
                "sources": [
                    {
                        "source_id": "email:uid-1",
                        "source_type": "email",
                        "uid": "uid-1",
                        "source_weighting": {
                            "text_available": True,
                            "can_corroborate_or_contradict": True,
                        },
                    }
                ],
                "source_links": [],
                "source_type_profiles": [],
            },
            "candidates": [],
            "finding_evidence_index": {"findings": []},
            "investigation_report": {
                "summary": {"section_count": 1, "supported_section_count": 1, "insufficient_section_count": 0},
                "sections": {
                    "missing_information": {
                        "section_id": "missing_information",
                        "title": "Missing Information / Further Evidence Needed",
                        "status": "supported",
                        "entries": [],
                    }
                },
            },
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)
    bundle = payload_out["multi_source_case_bundle"]
    assert bundle is not None
    chat_log = next(source for source in bundle["sources"] if source["source_type"] == "chat_log")
    assert chat_log["source_id"] == "chat-export-1"
    assert "Please keep this off email for now." in chat_log["snippet"]
    assert chat_log["participants"] == ["employee", "manager"]
    assert chat_log["chat_message_count"] == 2
    assert chat_log["chat_message_units"][0]["speaker"] == "employee"
    assert chat_log["provenance"]["speaker_time_parsing"] == "common_line_patterns"
    assert payload_out["chat_export_ingestion_report"]["summary"]["ingested_chat_export_count"] == 1


@pytest.mark.asyncio
async def test_build_case_analysis_augments_retaliation_and_comparator_outputs_with_manifest_sources(monkeypatch) -> None:
    payload = case_payload()
    payload["source_scope"] = "emails_and_attachments"
    payload["case_scope"]["comparator_actors"] = [
        {
            "name": "Pat Peer",
            "email": "pat@example.org",
        }
    ]
    payload["case_scope"]["trigger_events"] = [{"trigger_type": "complaint", "date": "2025-03-10"}]
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:note:complaint",
                "source_class": "note_record",
                "date": "2025-03-10",
                "title": "Complaint to HR",
                "text": "employee raised a formal complaint to HR and SBV.",
            },
            {
                "source_id": "manifest:note:target-home-office",
                "source_class": "note_record",
                "date": "2025-03-12",
                "title": "Home office denied",
                "text": "employee was denied home office after the complaint.",
            },
            {
                "source_id": "manifest:note:comparator-home-office",
                "source_class": "note_record",
                "date": "2025-03-13",
                "title": "Home office approved",
                "text": "Pat Peer received home office approval during the same week.",
            },
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)

    async def fake_build_answer_context_payload(_deps, _answer_params, **kwargs):
        return {
            "case_bundle": {
                "bundle_id": "case-123",
                "scope": {
                    "target_person": {"name": "employee", "email": "employee@example.test"},
                    "comparator_actors": [{"name": "Pat Peer", "email": "pat@example.org"}],
                    "employment_issue_tags": ["sbv_participation"],
                    "allegation_focus": ["retaliation", "unequal_treatment"],
                },
            },
            "multi_source_case_bundle": {
                "summary": {"source_count": 0, "source_type_counts": {}},
                "sources": [],
                "source_links": [],
                "source_type_profiles": [],
            },
            "retaliation_analysis": None,
            "comparative_treatment": None,
            "finding_evidence_index": {"findings": []},
            "investigation_report": {
                "summary": {"section_count": 1, "supported_section_count": 1, "insufficient_section_count": 0},
                "sections": {
                    "missing_information": {
                        "section_id": "missing_information",
                        "title": "Missing Information / Further Evidence Needed",
                        "status": "supported",
                        "entries": [],
                    }
                },
            },
            "candidates": [],
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)

    class MockDeps:
        @staticmethod
        def get_email_db():
            return None

    payload_out = await build_case_analysis_payload(MockDeps(), params)
    assert payload_out["retaliation_analysis"]["source_backed_candidate_counts"]["protected_activity"] == 1
    assert payload_out["retaliation_analysis"]["source_backed_candidate_counts"]["adverse_actions"] >= 1
    assert payload_out["comparative_treatment"]["summary"]["source_backed_point_count"] == 1
    assert payload_out["comparative_treatment"]["source_backed_comparator_points"][0]["issue_id"] == (
        "mobile_work_approvals_or_restrictions"
    )


@pytest.mark.asyncio
async def test_build_case_analysis_wraps_answer_context(monkeypatch) -> None:
    params = EmailCaseAnalysisInput.model_validate(case_payload())

    async def fake_build_answer_context_payload(_deps, answer_params, **kwargs):
        assert answer_params.question
        return {
            "search": {
                "top_k": 8,
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
                "hybrid": False,
                "rerank": False,
            },
            "case_bundle": {
                "bundle_id": "case-123",
                "scope": {
                    "employment_issue_tags": ["sbv_participation"],
                    "allegation_focus": ["retaliation", "exclusion"],
                },
            },
            "multi_source_case_bundle": {
                "summary": {"missing_source_types": [], "source_type_counts": {"email": 1}},
                "chronology_anchors": [
                    {
                        "source_id": "email:uid-1",
                        "source_type": "email",
                        "document_kind": "email_body",
                        "date": "2025-03-15T10:00:00",
                        "title": "Status",
                        "reliability_level": "high",
                    }
                ],
                "sources": [
                    {
                        "source_id": "email:uid-1",
                        "source_type": "email",
                        "document_kind": "email_body",
                        "uid": "uid-1",
                        "title": "Status",
                        "date": "2025-03-15T10:00:00",
                        "snippet": "Please just comply with the updated process.",
                        "source_reliability": {"level": "high", "basis": "authored_email_body"},
                        "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                        "provenance": {"evidence_handle": "email:uid-1"},
                    }
                ],
                "source_links": [],
            },
            "timeline": {
                "events": [
                    {
                        "uid": "uid-1",
                        "date": "2025-03-15T10:00:00",
                        "subject": "Status",
                        "conversation_id": "conv-1",
                    }
                ]
            },
            "power_context": {"missing_org_context": True},
            "case_patterns": {},
            "retaliation_analysis": None,
            "comparative_treatment": None,
            "actor_identity_graph": {
                "actors": [
                    {
                        "actor_id": "actor-manager",
                        "primary_email": "manager@example.com",
                        "display_names": ["Morgan Manager"],
                        "role_hints": ["manager"],
                        "role_context": {
                            "supplied_role_facts": [{"role": "manager"}],
                        },
                    }
                ]
            },
            "communication_graph": {
                "graph_findings": [
                    {
                        "finding_id": "decision_visibility_asymmetry:actor-manager",
                        "graph_signal_type": "decision_visibility_asymmetry",
                        "summary": "Decision flow varies with target visibility.",
                        "evidence_chain": {
                            "sender_node_id": "actor-manager",
                            "message_uids": ["uid-1"],
                            "thread_group_ids": ["conv-1"],
                        },
                    }
                ]
            },
            "finding_evidence_index": {"findings": []},
            "evidence_table": {"row_count": 0},
            "behavioral_strength_rubric": {"version": "1"},
            "investigation_report": {"summary": {"section_count": 8}},
            "candidates": [],
        }

    monkeypatch.setattr("src.tools.search_answer_context.build_answer_context_payload", fake_build_answer_context_payload)

    class MockDeps:
        async def offload(self, fn, *args, **kwargs):
            if args or kwargs:
                return fn(*args, **kwargs)
            return fn()

    rendered = await build_case_analysis(MockDeps(), params)
    payload = json.loads(rendered)
    assert payload["workflow"] == "case_analysis"
    assert payload["search"]["date_from"] == "2025-01-01"
    assert payload["search"]["date_to"] == "2025-06-30"
    assert payload["matter_evidence_index"]["row_count"] == 1
    assert payload["matter_evidence_index"]["rows"][0]["exhibit_id"] == "EXH-001"
    assert payload["matter_evidence_index"]["rows"][0]["source_id"] == "email:uid-1"
    assert payload["matter_evidence_index"]["rows"][0]["main_issue_tags"] == []
    assert payload["matter_evidence_index"]["rows"][0]["scope_issue_tags"] == ["sbv_participation"]
    assert payload["matter_evidence_index"]["rows"][0]["inferred_issue_tags"] == ["retaliation_massregelung"]
    assert payload["matter_evidence_index"]["rows"][0]["all_issue_tags"] == [
        "sbv_participation",
        "retaliation_massregelung",
    ]
    assert payload["matter_evidence_index"]["rows"][0]["issue_tags"][0]["assignment_basis"] == "operator_supplied"
    assert payload["matter_evidence_index"]["rows"][0]["exhibit_reliability"]["strength"] == "strong"
    assert payload["matter_evidence_index"]["rows"][0]["exhibit_reliability"]["next_step_logic"]["readiness"] == "usable_now"
    assert payload["master_chronology"]["entry_count"] == 1
    assert payload["master_chronology"]["entries"][0]["source_linkage"]["source_ids"] == ["email:uid-1"]
    assert payload["master_chronology"]["entries"][0]["event_support_matrix"]["ordinary_managerial_explanation"]["status"] == (
        "plausible_alternative"
    )
    assert payload["master_chronology"]["views"]["short_neutral_chronology"]["entry_count"] == 1
    assert payload["master_chronology"]["views"]["balanced_timeline_assessment"]["summary"]["strongest_timeline_inferences"]
    assert payload["matter_workspace"]["matter"]["bundle_id"] == "case-123"
    assert payload["matter_workspace"]["evidence_registry"]["exhibit_ids"] == ["EXH-001"]
    assert payload["matter_workspace"]["chronology_registry"]["entry_ids"] == ["CHR-001"]
    assert payload["actor_identity_graph"]["actors"][0]["actor_id"] == "actor-manager"
    assert payload["actor_map"]["actors"][0]["actor_id"] == "actor-manager"
    assert payload["actor_map"]["actors"][0]["status"]["decision_maker"] is True
    assert payload["witness_map"]["primary_decision_makers"][0]["actor_id"] == "actor-manager"
    assert payload["promise_contradiction_analysis"]["summary"]["promise_action_row_count"] == 0
    assert payload["lawyer_briefing_memo"]["memo_format"] == "lawyer_onboarding_brief"
    assert payload["lawyer_briefing_memo"]["sections"]["strongest_evidence"]
    assert payload["controlled_factual_drafting"]["drafting_format"] == "controlled_factual_drafting"
    assert payload["controlled_factual_drafting"]["controlled_draft"]["sections"]["established_facts"]
    assert payload["case_dashboard"]["dashboard_format"] == "refreshable_case_dashboard"
    assert payload["case_dashboard"]["cards"]["main_actors"][0]["actor_id"] == "actor-manager"
    assert payload["message_appendix"]["included"] is True
