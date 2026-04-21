from __future__ import annotations

from src.document_request_checklist import build_document_request_checklist


def test_build_document_request_checklist_groups_requests_and_preservation_actions() -> None:
    payload = build_document_request_checklist(
        matter_evidence_index={
            "top_10_missing_exhibits": [
                {
                    "requested_exhibit": "Complaint, objection, HR-contact, or participation-event record",
                    "issue_track_title": "Retaliation / Maßregelungsverbot",
                    "why_missing_matters": "This concrete document would help close the current retaliation proof gap.",
                    "linked_date_gap_ids": ["GAP-001"],
                },
                {
                    "requested_exhibit": "time system or attendance records for the disputed period",
                    "issue_track_title": "Fürsorgepflicht",
                    "why_missing_matters": "Attendance data may test the chronology and workability sequence.",
                    "linked_date_gap_ids": [],
                },
            ]
        },
        skeptical_employer_review={
            "weaknesses": [
                {
                    "category": "chronology_problem",
                    "why_it_matters": "Timeline gaps weaken temporal attribution.",
                    "linked_date_gap_ids": ["GAP-001"],
                    "supporting_finding_ids": ["finding-gap"],
                    "supporting_source_ids": ["email:uid-gap-1"],
                    "supporting_uids": ["uid-gap-1"],
                    "repair_guidance": {
                        "evidence_that_would_repair": "Native calendar items and meeting notes around the disputed sequence."
                    },
                }
            ]
        },
        missing_information_entries=[
            {"statement": "Structured org or dependency context is missing, which limits power-dynamics interpretation."}
        ],
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "burden_shifting_indicators",
                    "title": "Burden-shifting indicators",
                    "missing_proof": [
                        "Role-matched comparator actors and treatment records are still missing from the supplied case scope."
                    ],
                }
            ]
        },
        case_scope_quality={"missing_recommended_fields": ["comparator_actors"]},
        analysis_limits={"downgrade_reasons": []},
    )

    assert payload["group_count"] >= 2
    groups = {group["group_id"]: group for group in payload["groups"]}
    assert "time system_attendance_records" in groups
    attendance_item = groups["time system_attendance_records"]["items"][0]
    assert attendance_item["likely_custodian"] == "Timekeeping / payroll administration"
    assert attendance_item["risk_of_loss"] == "high"
    assert attendance_item["preservation_action"]
    general_or_personnel = groups["personnel_file"]["items"][0]
    assert "organization charts" in general_or_personnel["request"].lower()
    chronology_group = groups["calendar_meeting_records"]["items"][-1]
    assert chronology_group["linked_date_gap_ids"] == ["GAP-001"]
    assert groups["calendar_meeting_records"]["supporting_finding_ids"] == ["finding-gap"]
    assert groups["calendar_meeting_records"]["supporting_source_ids"] == ["email:uid-gap-1"]
    assert groups["calendar_meeting_records"]["supporting_uids"] == ["uid-gap-1"]
    assert "comparator_evidence" in groups
