# ruff: noqa: F401, F403
from __future__ import annotations

import pytest

from src.case_analysis import (
    build_case_analysis_payload,
    derive_case_analysis_query,
    transform_case_analysis_payload,
)
from src.case_analysis_harvest import _coverage_metrics, _split_evidence_bank_layers, build_archive_harvest_bundle
from src.mcp_models import EmailCaseAnalysisInput, EmailLegalSupportInput
from src.question_execution_waves import derive_wave_query_lane_specs

from ._case_analysis_integration_cases import *
from .helpers.case_analysis_fixtures import case_payload as _case_payload


def test_transform_case_analysis_payload_compacts_case_evidence_when_requested() -> None:
    payload = _case_payload()
    payload["compact_case_evidence"] = True
    params = EmailCaseAnalysisInput.model_validate(payload)
    answer_payload = {
        "finding_evidence_index": {
            "findings": [
                {"finding_id": "f-1"},
                {"finding_id": "f-2"},
                {"finding_id": "f-3"},
                {"finding_id": "f-4"},
            ]
        },
        "evidence_table": {"row_count": 8},
        "candidates": [
            {
                "uid": f"uid-{idx}",
                "date": "2025-03-15T10:00:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": f"Status {idx}",
                "snippet": "Please just comply with the updated process.",
                "language_rhetoric": {"authored_text": {"signal_count": 0, "signals": []}},
                "message_findings": {"authored_text": {"behavior_candidates": [], "counter_indicators": []}},
            }
            for idx in range(1, 8)
        ],
    }

    transformed = transform_case_analysis_payload(answer_payload, params)
    assert transformed["finding_evidence_index"]["summary"]["finding_count"] == 4
    assert transformed["evidence_table"]["summary"]["row_count"] == 8
    assert transformed["message_appendix"]["shown_row_count"] == 5
    assert transformed["message_appendix"]["_truncated"] == 2


def test_transform_case_analysis_payload_preserves_email_source_metadata_in_compacted_bundle() -> None:
    payload = _case_payload()
    payload["review_mode"] = "exhaustive_matter_review"
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-compact-1",
        "artifacts": [
            {
                "source_id": "manifest:note:1",
                "source_class": "formal_document",
                "title": "Meeting note",
                "date": "2025-03-10",
                "text": "Meeting note text.",
            }
        ],
    }
    payload["chat_log_entries"] = [
        {
            "platform": "Teams",
            "participants": ["employee@example.test", "manager@example.test"],
            "date": "2025-03-11T10:00:00Z",
            "text": "Please keep this off email for now.",
        }
    ]
    params = EmailCaseAnalysisInput.model_validate(payload)
    answer_payload = {
        "search": {},
        "case_bundle": {
            "scope": {
                "case_label": "Case A",
                "target_person": {"name": "employee", "email": "employee@example.test"},
                "analysis_goal": "lawyer_briefing",
                "allegation_focus": ["retaliation"],
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        },
        "multi_source_case_bundle": {
            "summary": {"source_type_counts": {"email": 1}},
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "title": "Status update",
                    "date": "2025-03-15T10:00:00",
                    "snippet": "Please comply with the updated process.",
                    "sender_name": "manager",
                    "sender_email": "manager@example.test",
                    "to": ["employee@example.test"],
                    "cc": ["sbv@example.org"],
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "document_locator": {"evidence_handle": "email:uid-1", "chunk_id": "chunk-1"},
                }
            ],
            "source_links": [],
            "source_type_profiles": [],
        },
        "matter_ingestion_report": {
            "version": "1",
            "review_mode": "exhaustive_matter_review",
            "completeness_status": "complete",
            "summary": {"total_supplied_artifacts": 1},
        },
        "power_context": {},
        "case_patterns": {},
        "retaliation_analysis": {},
        "comparative_treatment": {},
        "communication_graph": {},
        "actor_identity_graph": {"actors": []},
        "finding_evidence_index": {"findings": []},
        "evidence_table": {"row_count": 0},
        "behavioral_strength_rubric": {"version": "1"},
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
        "candidates": [
            {
                "uid": "uid-1",
                "date": "2025-03-15T10:00:00",
                "sender_name": "manager",
                "sender_email": "manager@example.test",
                "subject": "Status update",
                "snippet": "Please comply with the updated process.",
            }
        ],
    }

    transformed = transform_case_analysis_payload(answer_payload, params)

    evidence_row = transformed["matter_evidence_index"]["rows"][0]
    assert evidence_row["date"] == "2025-03-15T10:00:00"
    assert evidence_row["sender_or_author"] == "manager"
    assert evidence_row["recipients"] == ["employee@example.test", "sbv@example.org"]
    assert evidence_row["short_description"] == "Status update: Please comply with the updated process."
    assert evidence_row["key_quoted_passage"] == "Please comply with the updated process."


def test_transform_case_analysis_payload_rebuilds_report_from_final_mixed_source_bundle() -> None:
    payload = _case_payload()
    payload["review_mode"] = "exhaustive_matter_review"
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-report-1",
        "artifacts": [
            {
                "source_id": "manifest:note:1",
                "source_class": "note_record",
                "title": "Complaint note",
                "date": "2025-03-10",
                "text": "employee raised a formal complaint to HR.",
            }
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)
    answer_payload = {
        "search": {},
        "case_bundle": {
            "scope": {
                "case_label": "Case A",
                "target_person": {"name": "employee", "email": "employee@example.test"},
                "analysis_goal": "lawyer_briefing",
                "allegation_focus": ["retaliation"],
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            }
        },
        "multi_source_case_bundle": {
            "summary": {"source_type_counts": {"note_record": 1}},
            "sources": [
                {
                    "source_id": "manifest:note:1",
                    "source_type": "note_record",
                    "document_kind": "attached_note_record",
                    "title": "Complaint note",
                    "date": "2025-03-10",
                    "snippet": "employee raised a formal complaint to HR.",
                    "author": "employee",
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                    "source_reliability": {"level": "high", "basis": "matter_manifest_parsed"},
                    "chronology_anchor": {"date": "2025-03-10", "source_id": "manifest:note:1", "source_type": "note_record"},
                    "document_locator": {"evidence_handle": "manifest:note:1"},
                }
            ],
            "source_links": [],
            "source_type_profiles": [],
        },
        "matter_ingestion_report": {
            "version": "1",
            "review_mode": "exhaustive_matter_review",
            "completeness_status": "complete",
            "summary": {"total_supplied_artifacts": 1},
        },
        "power_context": {},
        "case_patterns": {},
        "retaliation_analysis": {},
        "comparative_treatment": {},
        "communication_graph": {},
        "actor_identity_graph": {"actors": []},
        "finding_evidence_index": {"findings": []},
        "evidence_table": {"row_count": 0},
        "behavioral_strength_rubric": {"version": "1"},
        "investigation_report": {
            "summary": {"section_count": 1, "supported_section_count": 0, "insufficient_section_count": 1},
            "sections": {
                "matter_evidence_index": {
                    "section_id": "matter_evidence_index",
                    "title": "Matter Evidence Index",
                    "status": "insufficient",
                    "entries": [],
                }
            },
        },
        "candidates": [],
    }

    transformed = transform_case_analysis_payload(answer_payload, params)

    assert transformed["matter_evidence_index"]["row_count"] == 1
    assert transformed["matter_evidence_index"]["rows"][0]["source_id"] == "manifest:note:1"
    assert transformed["investigation_report"]["sections"]["matter_evidence_index"]["status"] == "supported"


def test_transform_case_analysis_payload_adds_mixed_scope_warning() -> None:
    payload = _case_payload()
    payload["source_scope"] = "mixed_case_file"
    payload["chat_log_entries"] = [
        {
            "source_id": "chat-1",
            "platform": "Teams",
            "text": "Please keep this off email for now.",
        }
    ]
    params = EmailCaseAnalysisInput.model_validate(payload)
    transformed = transform_case_analysis_payload({}, params)
    assert "mixed_case_file_declared_without_mixed_record_support" not in transformed["case_scope_quality"]["downgrade_reasons"]
    assert all(
        item["code"] != "mixed_case_file_declared_without_mixed_record_support"
        for item in transformed["analysis_limits"]["scope_warnings"]
    )


def test_transform_case_analysis_payload_accepts_manifest_backed_non_email_records() -> None:
    payload = _case_payload()
    payload["source_scope"] = "mixed_case_file"
    payload["matter_manifest"] = {
        "manifest_id": "matter-1",
        "artifacts": [
            {
                "source_id": "manifest:calendar:1",
                "source_class": "calendar_export",
                "title": "Meeting invite",
                "text": "SUMMARY: BEM review DTSTART:2025-03-10T10:00:00",
            }
        ],
    }
    params = EmailCaseAnalysisInput.model_validate(payload)
    transformed = transform_case_analysis_payload({}, params)
    assert "mixed_case_file_declared_without_mixed_record_support" not in transformed["case_scope_quality"]["downgrade_reasons"]
    assert "mixed_case_file_declared_but_no_mixed_record_support_was_supplied" not in transformed["analysis_limits"]["notes"]
