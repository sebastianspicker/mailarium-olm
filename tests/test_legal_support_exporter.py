from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from src.legal_support_acceptance_fixtures import execute_fixture_full_pack_sync
from src.legal_support_exporter import LegalSupportExporter


def _payload() -> dict[str, object]:
    return {
        "analysis_query": "workplace case analysis. target employee",
        "review_mode": "exhaustive_matter_review",
        "privacy_guardrails": {"privacy_mode": "external_counsel_export"},
        "case_scope_quality": {"status": "degraded"},
        "matter_ingestion_report": {
            "completeness_status": "complete",
            "summary": {"total_supplied_artifacts": 3},
        },
        "analysis_limits": {
            "notes": ["review_mode_is_retrieval_only", "chat_log_source_type_not_available_in_current_case_bundle"]
        },
        "matter_coverage_ledger": {
            "summary": {
                "coverage_status": "partial",
                "total_source_count": 3,
            }
        },
        "matter_persistence": {
            "snapshot_id": "snapshot:abc123",
            "workspace_id": "workspace:abc123",
            "matter_id": "matter:abc123",
            "review_state": "human_verified",
            "last_approved_snapshot_id": "snapshot:older001",
            "changes_since_last_approved": {
                "changed": True,
                "changed_registries": ["source_ids", "issue_ids"],
            },
        },
        "lawyer_briefing_memo": {"sections": {"executive_summary": [{"entry_id": "memo-1", "text": "Key issue summary."}]}},
        "case_dashboard": {
            "cards": {"main_claims_or_issues": [{"entry_id": "card-1", "title": "Retaliation", "summary": "Requires review."}]}
        },
        "lawyer_issue_matrix": {
            "rows": [
                {
                    "issue_id": "retaliation_massregelungsverbot",
                    "title": "Retaliation",
                    "legal_relevance_status": "potentially_relevant",
                    "source_conflict_status": "possible_conflict_elsewhere_in_record",
                    "missing_proof": ["Comparator evidence"],
                }
            ]
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
                    "source_id": "email:uid-1",
                    "exhibit_reliability": {"strength": "strong", "next_step_logic": {"readiness": "usable_now"}},
                    "source_conflict_status": "disputed",
                    "source_conflict_ids": ["SCF-001"],
                    "supporting_citation_ids": ["c-1"],
                    "follow_up_needed": [],
                }
            ],
        },
        "master_chronology": {
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2025-03-11",
                    "title": "Status",
                    "description": "Status email sent after complaint.",
                    "fact_stability": "disputed",
                }
            ],
            "summary": {
                "source_conflict_registry": {
                    "conflict_count": 1,
                    "conflicts": [
                        {
                            "conflict_id": "SCF-001",
                            "conflict_kind": "inconsistent_summary",
                            "resolution_status": "unresolved_human_review_needed",
                            "priority_rule_applied": "authored_text_over_metadata",
                            "summary": "Meeting note and later email differ on SBV inclusion.",
                        }
                    ],
                }
            },
        },
        "document_request_checklist": {
            "groups": [{"group_id": "g-1", "group_title": "Records", "items": [{"requested_record": "SBV file"}]}]
        },
        "investigation_report": {"version": "1", "sections": {"executive_summary": {"status": "supported"}}},
    }


def _ready_payload() -> dict[str, object]:
    payload = _payload()
    payload["matter_coverage_ledger"] = {
        "summary": {
            "coverage_status": "complete",
            "total_source_count": 3,
        }
    }
    return payload


def test_export_counsel_handoff_html(tmp_path: Path) -> None:
    output = tmp_path / "handoff.html"
    result = LegalSupportExporter().export_file(
        payload=_ready_payload(),
        output_path=str(output),
        delivery_target="counsel_handoff",
        delivery_format="html",
    )

    assert result["delivery_format"] == "html"
    text = output.read_text(encoding="utf-8")
    assert "Counsel Handoff" in text
    assert "Key issue summary." in text
    assert "Meeting note and later email differ on SBV inclusion." in text
    assert "Review mode: exhaustive_matter_review" in text
    assert "Completeness: complete" in text
    assert "snapshot:abc123" in text
    assert "Coverage status: complete" in text
    assert "Downgrade markers" in text
    assert result["export_metadata"]["snapshot_id"] == "snapshot:abc123"


def test_counsel_export_status_reports_internal_only_governance_for_machine_extracted() -> None:
    payload = cast(dict[str, Any], _ready_payload())
    payload["matter_persistence"]["review_state"] = "machine_extracted"

    result = LegalSupportExporter().counsel_export_status(payload=payload)

    readiness = result["export_metadata"]["counsel_export_readiness"]
    assert result["ready"] is False
    assert result["blockers"] == ["snapshot_review_state:machine_extracted"]
    assert readiness["policy_state"] == "internal_only"
    assert readiness["required_review_states"] == ["human_verified", "export_approved"]
    assert readiness["recommended_internal_targets"] == ["dashboard", "exhibit_register"]
    assert "Promote the persisted snapshot" in readiness["next_step"]


def test_counsel_export_status_allows_export_approved_snapshot() -> None:
    payload = cast(dict[str, Any], _ready_payload())
    payload["matter_persistence"]["review_state"] = "export_approved"

    result = LegalSupportExporter().counsel_export_status(payload=payload)

    readiness = result["export_metadata"]["counsel_export_readiness"]
    assert result["ready"] is True
    assert result["blockers"] == []
    assert readiness["policy_state"] == "counsel_ready"


def test_counsel_export_status_rejects_legacy_approved_alias() -> None:
    payload = cast(dict[str, Any], _ready_payload())
    payload["matter_persistence"]["review_state"] = "approved"

    result = LegalSupportExporter().counsel_export_status(payload=payload)

    readiness = result["export_metadata"]["counsel_export_readiness"]
    assert result["ready"] is False
    assert result["blockers"] == ["snapshot_review_state:approved"]
    assert readiness["policy_state"] == "unsupported_review_state"
    assert readiness["required_review_states"] == ["human_verified", "export_approved"]
    assert "human_verified or export_approved" in readiness["next_step"]


def test_counsel_export_status_blocks_unpersisted_counsel_grade_payload() -> None:
    payload = cast(dict[str, Any], _ready_payload())
    payload.pop("matter_persistence")
    payload["review_classification"] = {
        "may_be_presented_as_full_matter_review": True,
        "counsel_use_status": "counsel_grade_exhaustive_review",
    }

    result = LegalSupportExporter().counsel_export_status(payload=payload)

    readiness = result["export_metadata"]["counsel_export_readiness"]
    assert result["ready"] is False
    assert result["blockers"] == ["snapshot_review_state:missing"]
    assert readiness["policy_state"] == "snapshot_missing"
    assert readiness["recommended_internal_targets"] == ["dashboard", "exhibit_register"]
    assert "Persist the snapshot" in readiness["next_step"]


def test_export_exhibit_register_csv(tmp_path: Path) -> None:
    output = tmp_path / "exhibits.csv"
    result = LegalSupportExporter().export_file(
        payload=_payload(),
        output_path=str(output),
        delivery_target="exhibit_register",
        delivery_format="csv",
    )

    assert result["spreadsheet_ready"] is True
    with output.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["exhibit_id"] == "EXH-001"
    assert rows[0]["source_id"] == "email:uid-1"
    assert rows[0]["source_conflict_status"] == "disputed"
    assert rows[0]["source_conflict_ids"] == "SCF-001"
    assert rows[0]["snapshot_id"] == "snapshot:abc123"
    assert rows[0]["coverage_status"] == "partial"


def test_export_dashboard_json(tmp_path: Path) -> None:
    output = tmp_path / "dashboard.json"
    result = LegalSupportExporter().export_file(
        payload=_payload(),
        output_path=str(output),
        delivery_target="dashboard",
        delivery_format="json",
    )

    assert result["delivery_format"] == "json"
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["export_metadata"]["snapshot_id"] == "snapshot:abc123"
    assert data["case_dashboard"]["cards"]["main_claims_or_issues"][0]["title"] == "Retaliation"


def test_export_counsel_handoff_bundle(tmp_path: Path) -> None:
    output = tmp_path / "handoff_bundle.zip"
    result = LegalSupportExporter().export_file(
        payload=_ready_payload(),
        output_path=str(output),
        delivery_target="counsel_handoff_bundle",
        delivery_format="bundle",
    )

    assert result["delivery_format"] == "bundle"
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "counsel_handoff.html" in names
        assert "exhibit_register.csv" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["delivery_target"] == "counsel_handoff_bundle"
    assert manifest["review_mode"] == "exhaustive_matter_review"
    assert manifest["matter_ingestion_report"]["completeness_status"] == "complete"
    assert manifest["export_metadata"]["snapshot_id"] == "snapshot:abc123"
    assert len(manifest["artifacts"]) >= 6


def test_export_bundle_from_realistic_full_pack_payload(tmp_path: Path) -> None:
    payload = execute_fixture_full_pack_sync("retaliation_rights_assertion")["full_case_analysis"]
    payload["matter_persistence"] = {
        "snapshot_id": "snapshot:fixture-1",
        "workspace_id": "workspace:fixture-1",
        "matter_id": "matter:fixture-1",
        "review_state": "human_verified",
    }
    output = tmp_path / "fixture_bundle.zip"

    result = LegalSupportExporter().export_file(
        payload=payload,
        output_path=str(output),
        delivery_target="counsel_handoff_bundle",
        delivery_format="bundle",
    )

    assert result["delivery_format"] == "bundle"
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "counsel_handoff.html" in names
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        dashboard_payload = json.loads(archive.read("case_dashboard.json").decode("utf-8"))
        issue_payload = json.loads(archive.read("lawyer_issue_matrix.json").decode("utf-8"))
    assert manifest["matter_ingestion_report"]["summary"]["source_class_counts"]["chat_export"] >= 1
    assert dashboard_payload["case_dashboard"]["cards"]["main_claims_or_issues"]
    assert issue_payload["lawyer_issue_matrix"]["rows"]
    assert payload["retaliation_analysis"]["retaliation_point_count"] == 1


def test_export_counsel_handoff_blocks_partial_payload(tmp_path: Path) -> None:
    output = tmp_path / "handoff.html"
    try:
        LegalSupportExporter().export_file(
            payload=_payload(),
            output_path=str(output),
            delivery_target="counsel_handoff",
            delivery_format="html",
        )
    except ValueError as exc:
        assert "Counsel-facing export blocked" in str(exc)
        assert "coverage_status:partial" in str(exc)
    else:
        raise AssertionError("expected counsel-facing export to be blocked for partial payload")


def test_export_file_rejects_existing_output_path(tmp_path: Path) -> None:
    output = tmp_path / "handoff.html"
    output.write_text("existing content", encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        LegalSupportExporter().export_file(
            payload=_ready_payload(),
            output_path=str(output),
            delivery_target="counsel_handoff",
            delivery_format="html",
        )
