from __future__ import annotations

from src.deadline_warnings import build_deadline_warnings


def test_build_deadline_warnings_surfaces_operational_timing_risks() -> None:
    payload = build_deadline_warnings(
        case_bundle={"scope": {"date_from": "2025-01-01"}},
        master_chronology={"summary": {"date_range": {"first": "2025-01-01"}}},
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "retaliation_massregelungsverbot",
                    "urgency_or_deadline_relevance": (
                        "Potential urgency if current participation or post-complaint measures are ongoing."
                    ),
                }
            ]
        },
        document_request_checklist={
            "groups": [
                {
                    "group_id": "calendar_meeting_records",
                    "items": [
                        {
                            "urgency": "high",
                            "risk_of_loss": "high",
                            "linked_date_gap_ids": ["gap-1"],
                        }
                    ],
                }
            ]
        },
        as_of_date="2026-04-12",
    )

    assert payload is not None
    assert payload["overall_status"] == "timing_review_recommended"
    assert payload["summary"]["warning_count"] >= 3
    categories = {item["category"] for item in payload["warnings"]}
    assert "possible_deadline_relevance" in categories
    assert "document_preservation_urgency" in categories
    assert "escalating_evidence_loss_risk" in categories


def test_build_deadline_warnings_returns_empty_safe_payload_when_no_signals() -> None:
    payload = build_deadline_warnings(
        case_bundle={"scope": {"date_from": "2026-04-01"}},
        master_chronology={"summary": {"date_range": {"first": "2026-04-01"}}},
        lawyer_issue_matrix={"rows": []},
        document_request_checklist={"groups": []},
        as_of_date="2026-04-12",
    )

    assert payload is not None
    assert payload["overall_status"] == "no_material_timing_warning"
    assert payload["summary"]["warning_count"] == 0
