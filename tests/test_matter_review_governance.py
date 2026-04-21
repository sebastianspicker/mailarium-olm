from __future__ import annotations

import pytest

from src.case_analysis import build_case_analysis_payload
from src.email_db import EmailDatabase
from src.mcp_models import EmailCaseAnalysisInput


def test_matter_review_override_table_exists() -> None:
    db = EmailDatabase(":memory:")
    tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "matter_review_overrides" in tables
    db.close()


def test_upsert_and_list_matter_review_overrides(db_with_email: EmailDatabase) -> None:
    result = db_with_email.upsert_matter_review_override(
        workspace_id="workspace:abc123",
        target_type="actor_link",
        target_id="actor-manager",
        review_state="human_verified",
        override_payload={"display_names": ["Erika Human Verified"]},
        machine_payload={"display_names": ["manager"]},
        source_evidence=[{"source_id": "email:uid-1"}],
        reviewer="reviewer@example.org",
        review_notes="Confirmed actor linkage after manual review.",
    )

    assert result["workspace_id"] == "workspace:abc123"
    overrides = db_with_email.list_matter_review_overrides(workspace_id="workspace:abc123")
    assert len(overrides) == 1
    assert overrides[0]["override_payload"]["display_names"] == ["Erika Human Verified"]
    assert overrides[0]["machine_payload"]["display_names"] == ["manager"]
    assert overrides[0]["source_evidence"] == [{"source_id": "email:uid-1"}]

    summary = db_with_email.matter_review_status_summary(workspace_id="workspace:abc123")
    assert summary["override_count"] == 1
    assert summary["review_state_counts"]["human_verified"] == 1
    events = db_with_email.get_custody_chain(action="review_override_upsert")
    assert events


@pytest.mark.asyncio
async def test_build_case_analysis_payload_applies_review_overrides(monkeypatch) -> None:
    params = EmailCaseAnalysisInput.model_validate(
        {
            "case_scope": {
                "target_person": {"name": "employee", "email": "employee@example.test"},
                "suspected_actors": [{"name": "manager", "email": "manager@example.test"}],
                "allegation_focus": ["retaliation"],
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-06-30",
            },
            "source_scope": "emails_only",
        }
    )

    async def fake_build_answer_context_payload(_deps, _answer_params, **kwargs):
        return {
            "case_bundle": {
                "bundle_id": "case-123",
                "scope": {
                    "case_label": "Case 123",
                    "target_person": {"name": "employee", "email": "employee@example.test"},
                    "suspected_actors": [{"name": "manager", "email": "manager@example.test"}],
                    "allegation_focus": ["retaliation"],
                    "analysis_goal": "lawyer_briefing",
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                },
            },
            "actor_identity_graph": {
                "actors": [
                    {
                        "actor_id": "actor-manager",
                        "primary_email": "manager@example.test",
                        "display_names": ["manager"],
                    }
                ]
            },
            "multi_source_case_bundle": {
                "summary": {"source_type_counts": {"email": 1}, "missing_source_types": []},
                "sources": [
                    {
                        "source_id": "email:uid-1",
                        "source_type": "email",
                        "uid": "uid-1",
                        "actor_id": "actor-manager",
                        "title": "Status",
                        "date": "2025-03-15T10:00:00",
                        "snippet": "We will send the summary.",
                        "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                        "source_reliability": {"level": "high", "basis": "authored_email_body"},
                        "provenance": {"evidence_handle": "email:uid-1"},
                        "chronology_anchor": {"date": "2025-03-15T10:00:00"},
                    }
                ],
                "source_links": [],
                "source_type_profiles": [],
                "chronology_anchors": [],
            },
            "finding_evidence_index": {"findings": []},
            "evidence_table": {"row_count": 0},
            "candidates": [
                {
                    "uid": "uid-1",
                    "date": "2025-03-15T10:00:00",
                    "sender_name": "manager",
                    "sender_email": "manager@example.test",
                    "subject": "Status",
                    "snippet": "We will send the summary.",
                    "language_rhetoric": {"authored_text": {"signal_count": 0, "signals": []}},
                    "message_findings": {"authored_text": {"behavior_candidates": [], "counter_indicators": []}},
                }
            ],
            "timeline": {
                "events": [
                    {
                        "date": "2025-03-15",
                        "summary": "Status note",
                        "uid": "uid-1",
                    }
                ]
            },
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

    class ReviewDB:
        def list_matter_review_overrides(self, *, workspace_id: str, apply_on_refresh_only: bool = False):
            assert workspace_id
            assert apply_on_refresh_only is True
            return [
                {
                    "workspace_id": workspace_id,
                    "target_type": "actor_link",
                    "target_id": "actor-manager",
                    "review_state": "human_verified",
                    "override_payload": {"display_names": ["Erika Human Verified"]},
                    "source_evidence": [{"source_id": "email:uid-1"}],
                    "reviewer": "reviewer@example.org",
                    "review_notes": "Confirmed actor identity.",
                    "apply_on_refresh": True,
                },
                {
                    "workspace_id": workspace_id,
                    "target_type": "chronology_entry",
                    "target_id": "CHR-001",
                    "review_state": "disputed",
                    "override_payload": {"summary": "Date disputed by reviewer."},
                    "source_evidence": [{"source_id": "email:uid-1"}],
                    "reviewer": "reviewer@example.org",
                    "review_notes": "Chronology needs manual clarification.",
                    "apply_on_refresh": True,
                },
                {
                    "workspace_id": workspace_id,
                    "target_type": "exhibit_description",
                    "target_id": "email:uid-1",
                    "review_state": "export_approved",
                    "override_payload": {"short_description": "Human-approved description."},
                    "source_evidence": [{"source_id": "email:uid-1"}],
                    "reviewer": "reviewer@example.org",
                    "review_notes": "Approved for counsel export.",
                    "apply_on_refresh": True,
                },
            ]

    class MockDeps:
        @staticmethod
        def get_email_db():
            return ReviewDB()

    payload = await build_case_analysis_payload(MockDeps(), params)

    assert payload["review_governance"]["override_count"] == 3
    assert payload["review_governance"]["review_state_counts"]["human_verified"] == 1
    assert payload["actor_identity_graph"]["actors"][0]["display_names"] == ["Erika Human Verified"]
    assert payload["actor_identity_graph"]["actors"][0]["review_provenance"]["review_state"] == "human_verified"
    assert payload["master_chronology"]["entries"][0]["summary"] == "Date disputed by reviewer."
    assert payload["master_chronology"]["entries"][0]["review_provenance"]["review_state"] == "disputed"
    assert payload["matter_evidence_index"]["rows"][0]["short_description"] == "Human-approved description."
    assert payload["matter_evidence_index"]["rows"][0]["review_provenance"]["review_state"] == "export_approved"
