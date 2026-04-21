from __future__ import annotations

from src.case_analysis import _matter_coverage_ledger
from src.mcp_models import EmailCaseAnalysisInput


def test_matter_coverage_ledger_counts_issue_matrix_source_linkage_from_supporting_source_ids() -> None:
    params = EmailCaseAnalysisInput.model_validate(
        {
            "case_scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
                "allegation_focus": ["retaliation"],
            },
            "source_scope": "emails_and_attachments",
            "review_mode": "exhaustive_matter_review",
            "matter_manifest": {
                "artifacts": [
                    {
                        "source_class": "email",
                        "title": "Complaint email",
                        "date": "2025-01-15",
                        "text": "Project withdrawal followed the complaint.",
                    }
                ]
            },
        }
    )

    payload = _matter_coverage_ledger(
        params=params,
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "snippet": "Project withdrawal followed the complaint.",
                    "source_weighting": {"text_available": True},
                },
                {
                    "source_id": "formal_document:uid-2",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "snippet": "Unlinked document",
                    "source_weighting": {"text_available": True},
                },
            ]
        },
        matter_evidence_index={"rows": []},
        master_chronology={"entries": []},
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "retaliation_massregelungsverbot",
                    "supporting_source_ids": ["email:uid-1"],
                    "strongest_documents": [],
                }
            ]
        },
        message_appendix={"rows": []},
    )

    assert payload["summary"]["linked_source_count"] == 1
    assert payload["summary"]["stage_counts"]["linked_to_issue_matrix"] == 1
    assert payload["summary"]["uncovered_ingestible_source_count"] == 1

    rows = {row["source_id"]: row for row in payload["rows"]}
    assert rows["email:uid-1"]["analysis_status"] == "linked"
    assert rows["email:uid-1"]["stage_flags"]["linked_to_issue_matrix"] is True
    assert rows["email:uid-1"]["lineage"]["issue_ids"] == ["retaliation_massregelungsverbot"]
    assert rows["formal_document:uid-2"]["analysis_status"] == "ingested_not_yet_linked"
    assert payload["uncovered_ingestible_source_ids"] == ["formal_document:uid-2"]
