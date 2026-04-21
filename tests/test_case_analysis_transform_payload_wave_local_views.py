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


def test_transform_case_analysis_payload_adds_wave_local_views() -> None:
    payload = _case_payload()
    payload["wave_id"] = "wave_8"
    params = EmailCaseAnalysisInput.model_validate(payload)
    answer_payload = {
        "search": {},
        "case_bundle": {"bundle_id": "case-123"},
        "multi_source_case_bundle": {
            "summary": {"missing_source_types": []},
            "sources": [],
            "source_links": [],
            "source_type_profiles": [],
        },
        "matter_ingestion_report": {
            "version": "1",
            "review_mode": "retrieval_only",
            "completeness_status": "partial",
            "summary": {"total_supplied_artifacts": 0},
            "artifacts": [],
        },
        "power_context": {},
        "case_patterns": {},
        "retaliation_analysis": {},
        "comparative_treatment": {},
        "communication_graph": {},
        "actor_identity_graph": {"actors": []},
        "finding_evidence_index": {
            "findings": [
                {
                    "finding_id": "finding-time system",
                    "finding_label": "time system discrepancy",
                    "supporting_uids": ["uid-1"],
                    "supporting_evidence": [{"message_or_document_id": "uid-1", "citation_id": "CIT-1"}],
                },
                {
                    "finding_id": "finding-bem",
                    "finding_label": "BEM invite",
                    "supporting_uids": ["uid-2"],
                    "supporting_evidence": [{"message_or_document_id": "uid-2", "citation_id": "CIT-2"}],
                },
            ]
        },
        "matter_evidence_index": {
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "short_description": "Rebooking note",
                    "supporting_finding_ids": ["finding-time system"],
                    "supporting_citation_ids": ["CIT-1"],
                    "supporting_uids": ["uid-1"],
                    "quoted_evidence": {"original_text": "Bitte umbuchen."},
                },
                {
                    "exhibit_id": "EXH-002",
                    "source_id": "email:uid-2",
                    "short_description": "BEM invite",
                    "supporting_finding_ids": ["finding-bem"],
                    "supporting_citation_ids": ["CIT-2"],
                    "supporting_uids": ["uid-2"],
                    "quoted_evidence": {"original_text": "BEM Einladung."},
                },
            ]
        },
        "master_chronology": {
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2025-02-01",
                    "title": "Rebooking instruction",
                    "source_linkage": {
                        "source_ids": ["email:uid-1"],
                        "supporting_uids": ["uid-1"],
                        "supporting_citation_ids": ["CIT-1"],
                    },
                },
                {
                    "chronology_id": "CHR-002",
                    "date": "2025-02-02",
                    "title": "BEM invite",
                    "source_linkage": {
                        "source_ids": ["email:uid-2"],
                        "supporting_uids": ["uid-2"],
                        "supporting_citation_ids": ["CIT-2"],
                    },
                },
            ]
        },
        "lawyer_issue_matrix": {
            "rows": [
                {
                    "issue_id": "attendance_control",
                    "title": "Attendance control",
                    "supporting_finding_ids": ["finding-time system"],
                    "supporting_source_ids": ["email:uid-1"],
                    "supporting_uids": ["uid-1"],
                    "strongest_documents": [{"source_id": "email:uid-1", "exhibit_id": "EXH-001"}],
                },
                {
                    "issue_id": "bem_process",
                    "title": "BEM process",
                    "supporting_finding_ids": ["finding-bem"],
                    "supporting_source_ids": ["email:uid-2"],
                    "supporting_uids": ["uid-2"],
                    "strongest_documents": [{"source_id": "email:uid-2", "exhibit_id": "EXH-002"}],
                },
            ]
        },
        "document_request_checklist": {
            "groups": [
                {
                    "group_id": "attendance_records",
                    "title": "Attendance records",
                    "supporting_finding_ids": ["finding-time system"],
                    "supporting_source_ids": ["email:uid-1"],
                    "supporting_uids": ["uid-1"],
                    "items": [{"request": "time system export", "supporting_uids": ["uid-1"]}],
                },
                {
                    "group_id": "bem_records",
                    "title": "BEM records",
                    "supporting_finding_ids": ["finding-bem"],
                    "supporting_source_ids": ["email:uid-2"],
                    "supporting_uids": ["uid-2"],
                    "items": [{"request": "BEM invite", "supporting_uids": ["uid-2"]}],
                },
            ]
        },
        "promise_contradiction_analysis": {
            "promises_vs_actions": [
                {"source_id": "email:uid-1", "supporting_uids": ["uid-1"], "summary": "Rebooking required."},
                {"source_id": "email:uid-2", "supporting_uids": ["uid-2"], "summary": "BEM invite sent."},
            ],
            "omission_rows": [],
            "contradiction_table": [],
        },
        "archive_harvest": {"evidence_bank": [{"uid": "uid-1"}]},
        "evidence_table": {"row_count": 0},
        "behavioral_strength_rubric": {"version": "1"},
        "investigation_report": {"summary": {"section_count": 0}, "sections": {}},
        "timeline": [
            {"date": "2025-02-01", "summary": "time system Umbuchung wurde angeordnet."},
            {"date": "2025-02-02", "summary": "BEM Einladung wurde versandt."},
        ],
        "candidates": [],
    }

    transformed = transform_case_analysis_payload(answer_payload, params)

    assert transformed["wave_local_views"]["wave_id"] == "wave_8"
    assert transformed["wave_local_views"]["surface_counts"]["finding_evidence_index"] >= 1


def test_wave_local_views_ignore_unlinked_rows_even_when_text_matches_wave_terms() -> None:
    from src.wave_local_views import build_wave_local_views

    payload = {
        "archive_harvest": {"evidence_bank": [{"uid": "uid-linked"}]},
        "finding_evidence_index": {
            "findings": [
                {
                    "finding_id": "finding-linked",
                    "finding_label": "Generic routing note",
                    "supporting_uids": ["uid-linked"],
                    "supporting_evidence": [{"message_or_document_id": "uid-linked", "citation_id": "CIT-linked"}],
                },
                {
                    "finding_id": "finding-unlinked",
                    "finding_label": "time system discrepancy",
                    "supporting_uids": ["uid-unlinked"],
                    "supporting_evidence": [{"message_or_document_id": "uid-unlinked", "citation_id": "CIT-unlinked"}],
                },
            ]
        },
        "matter_evidence_index": {
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-linked",
                    "short_description": "Generic linked note",
                    "supporting_finding_ids": ["finding-linked"],
                    "supporting_citation_ids": ["CIT-linked"],
                    "supporting_uids": ["uid-linked"],
                },
                {
                    "exhibit_id": "EXH-002",
                    "source_id": "email:uid-unlinked",
                    "short_description": "time system evidence",
                    "supporting_finding_ids": ["finding-unlinked"],
                    "supporting_citation_ids": ["CIT-unlinked"],
                    "supporting_uids": ["uid-unlinked"],
                },
            ]
        },
        "master_chronology": {
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "title": "Generic routing note",
                    "source_linkage": {"source_ids": ["email:uid-linked"], "supporting_uids": ["uid-linked"]},
                },
                {
                    "chronology_id": "CHR-002",
                    "title": "time system Umbuchung",
                    "source_linkage": {"source_ids": ["email:uid-unlinked"], "supporting_uids": ["uid-unlinked"]},
                },
            ]
        },
        "lawyer_issue_matrix": {
            "rows": [
                {
                    "issue_id": "linked_issue",
                    "title": "Generic attendance control issue",
                    "supporting_finding_ids": ["finding-linked"],
                    "supporting_source_ids": ["email:uid-linked"],
                    "supporting_uids": ["uid-linked"],
                },
                {
                    "issue_id": "time system_issue",
                    "title": "time system differential",
                    "supporting_finding_ids": ["finding-unlinked"],
                    "supporting_source_ids": ["email:uid-unlinked"],
                    "supporting_uids": ["uid-unlinked"],
                },
            ]
        },
        "document_request_checklist": {"groups": []},
        "promise_contradiction_analysis": {"promises_vs_actions": [], "omission_rows": [], "contradiction_table": []},
    }

    wave_local = build_wave_local_views(payload, wave_id="wave_8")

    assert wave_local["surface_counts"]["lawyer_issue_matrix"] == 1
    assert wave_local["lawyer_issue_matrix"]["rows"][0]["issue_id"] == "linked_issue"
    assert wave_local["surface_counts"]["master_chronology"] == 1
    assert wave_local["master_chronology"]["entries"][0]["chronology_id"] == "CHR-001"


def test_wave_local_views_differ_by_linked_archive_context() -> None:
    from src.wave_local_views import build_wave_local_views

    shared_payload = {
        "finding_evidence_index": {
            "findings": [
                {
                    "finding_id": "finding-wave-1",
                    "supporting_uids": ["uid-wave-1"],
                    "supporting_evidence": [{"message_or_document_id": "uid-wave-1", "citation_id": "CIT-1"}],
                },
                {
                    "finding_id": "finding-wave-8",
                    "supporting_uids": ["uid-wave-8"],
                    "supporting_evidence": [{"message_or_document_id": "uid-wave-8", "citation_id": "CIT-8"}],
                },
            ]
        },
        "matter_evidence_index": {
            "rows": [
                {
                    "exhibit_id": "EXH-1",
                    "source_id": "email:uid-wave-1",
                    "supporting_finding_ids": ["finding-wave-1"],
                    "supporting_uids": ["uid-wave-1"],
                },
                {
                    "exhibit_id": "EXH-8",
                    "source_id": "email:uid-wave-8",
                    "supporting_finding_ids": ["finding-wave-8"],
                    "supporting_uids": ["uid-wave-8"],
                },
            ]
        },
        "master_chronology": {"entries": []},
        "lawyer_issue_matrix": {
            "rows": [
                {
                    "issue_id": "wave_1_issue",
                    "supporting_finding_ids": ["finding-wave-1"],
                    "supporting_source_ids": ["email:uid-wave-1"],
                    "supporting_uids": ["uid-wave-1"],
                },
                {
                    "issue_id": "wave_8_issue",
                    "supporting_finding_ids": ["finding-wave-8"],
                    "supporting_source_ids": ["email:uid-wave-8"],
                    "supporting_uids": ["uid-wave-8"],
                },
            ]
        },
        "document_request_checklist": {"groups": []},
        "promise_contradiction_analysis": {"promises_vs_actions": [], "omission_rows": [], "contradiction_table": []},
    }

    wave_1_payload = {**shared_payload, "archive_harvest": {"evidence_bank": [{"uid": "uid-wave-1"}]}}
    wave_8_payload = {**shared_payload, "archive_harvest": {"evidence_bank": [{"uid": "uid-wave-8"}]}}

    wave_1 = build_wave_local_views(wave_1_payload, wave_id="wave_1")
    wave_8 = build_wave_local_views(wave_8_payload, wave_id="wave_8")

    assert wave_1["lawyer_issue_matrix"]["rows"][0]["issue_id"] == "wave_1_issue"
    assert wave_8["lawyer_issue_matrix"]["rows"][0]["issue_id"] == "wave_8_issue"


def test_wave_local_views_seed_context_from_archive_source_ids() -> None:
    from src.wave_local_views import build_wave_local_views

    payload = {
        "archive_harvest": {"evidence_bank": [{"source_id": "meeting:uid-1:meeting_data"}]},
        "finding_evidence_index": {"findings": []},
        "matter_evidence_index": {
            "rows": [
                {
                    "exhibit_id": "EXH-1",
                    "source_id": "meeting:uid-1:meeting_data",
                    "supporting_source_ids": ["meeting:uid-1:meeting_data"],
                }
            ]
        },
        "master_chronology": {"entries": []},
        "lawyer_issue_matrix": {"rows": []},
        "document_request_checklist": {"groups": []},
        "promise_contradiction_analysis": {"promises_vs_actions": [], "omission_rows": [], "contradiction_table": []},
    }

    wave_local = build_wave_local_views(payload, wave_id="wave_1")

    assert wave_local["surface_counts"]["matter_evidence_index"] == 1
    assert wave_local["matter_evidence_index"]["rows"][0]["source_id"] == "meeting:uid-1:meeting_data"


def test_wave_local_views_preserve_real_promise_contradiction_rows() -> None:
    from src.promise_contradiction_analysis import build_promise_contradiction_analysis
    from src.wave_local_views import build_wave_local_views

    promise_analysis = build_promise_contradiction_analysis(
        case_bundle={},
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "meeting:1",
                    "source_type": "meeting_note",
                    "uid": "uid-1",
                    "actor_id": "actor-manager",
                    "date": "2025-03-01",
                    "title": "BEM meeting",
                    "snippet": "We will include Alex Example in the BEM invite and inform the SBV.",
                },
                {
                    "source_id": "email:2",
                    "source_type": "email",
                    "uid": "uid-2",
                    "actor_id": "actor-manager",
                    "date": "2025-03-02",
                    "title": "BEM follow-up",
                    "snippet": "We did not include Alex Example in the invite and did not inform the SBV.",
                },
            ],
            "source_links": [{"from_source_id": "meeting:1", "to_source_id": "email:2"}],
        },
        master_chronology={},
    )

    assert promise_analysis is not None
    assert promise_analysis["contradiction_table"]

    wave_local = build_wave_local_views(
        {
            "archive_harvest": {"evidence_bank": [{"uid": "uid-1", "source_id": "meeting:1"}]},
            "finding_evidence_index": {"findings": []},
            "matter_evidence_index": {"rows": []},
            "master_chronology": {"entries": []},
            "lawyer_issue_matrix": {"rows": []},
            "document_request_checklist": {"groups": []},
            "promise_contradiction_analysis": promise_analysis,
        },
        wave_id="wave_1",
    )

    assert wave_local["surface_counts"]["contradiction_rows"] == len(promise_analysis["contradiction_table"])
    assert wave_local["promise_contradiction_analysis"]["contradiction_table"][0]["row_id"].startswith("contradiction:")


def test_message_appendix_rows_are_sorted_by_date_then_uid() -> None:
    params = EmailCaseAnalysisInput.model_validate(_case_payload())
    transformed = transform_case_analysis_payload(
        {
            "finding_evidence_index": {"findings": []},
            "candidates": [
                {
                    "uid": "uid-b",
                    "date": "2025-03-15T10:00:00",
                    "sender_name": "Sender B",
                    "sender_email": "b@example.org",
                    "subject": "Second",
                    "snippet": "Second snippet",
                    "language_rhetoric": {"authored_text": {"signal_count": 0, "signals": []}},
                    "message_findings": {"authored_text": {"behavior_candidates": [], "counter_indicators": []}},
                },
                {
                    "uid": "uid-a",
                    "date": "2025-03-15T10:00:00",
                    "sender_name": "Sender A",
                    "sender_email": "a@example.org",
                    "subject": "First",
                    "snippet": "First snippet",
                    "language_rhetoric": {"authored_text": {"signal_count": 0, "signals": []}},
                    "message_findings": {"authored_text": {"behavior_candidates": [], "counter_indicators": []}},
                },
                {
                    "uid": "uid-c",
                    "date": "2025-03-16T10:00:00",
                    "sender_name": "Sender C",
                    "sender_email": "c@example.org",
                    "subject": "Third",
                    "snippet": "Third snippet",
                    "language_rhetoric": {"authored_text": {"signal_count": 0, "signals": []}},
                    "message_findings": {"authored_text": {"behavior_candidates": [], "counter_indicators": []}},
                },
            ],
        },
        params,
    )
    rows = transformed["message_appendix"]["rows"]
    assert [row["uid"] for row in rows] == ["uid-a", "uid-b", "uid-c"]
