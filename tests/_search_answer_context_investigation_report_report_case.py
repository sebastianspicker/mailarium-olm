from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.mcp_models import (
    BehavioralCaseScopeInput,
    CasePartyInput,
    EmailAnswerContextInput,
)


@pytest.mark.asyncio
async def test_email_answer_context_emits_investigation_report(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-11",
                        "subject": "Re: Complaint follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-12T10:00:00",
                        "conversation_id": "conv-case-11",
                    },
                    chunk_id="chunk-case-11",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.95,
                )
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-11": {
                    "uid": "uid-case-11",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "conversation_id": "conv-case-11",
                }
            }

        def get_thread_emails(self, conversation_id):
            return [
                {
                    "uid": "uid-case-11",
                    "sender_email": "manager@example.com",
                    "sender_name": "Morgan Manager",
                }
            ]

    class DummyDeps:
        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

        @staticmethod
        def get_retriever():
            return DummyRetriever()

        @staticmethod
        def get_email_db():
            return DummyDB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        @staticmethod
        def sanitize(text: str) -> str:
            return text

        @staticmethod
        def tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def write_tool_annotations(title: str):
            return {"title": title}

        @staticmethod
        def idempotent_write_annotations(title: str):
            return {"title": title}

    monkeypatch.setattr(search_mod, "_deps", DummyDeps)
    monkeypatch.setattr(
        config_mod,
        "get_settings",
        lambda: SimpleNamespace(
            mcp_max_search_results=10,
            mcp_max_json_response_chars=200000,
            mcp_model_profile="test",
        ),
    )
    monkeypatch.setattr(
        answer_context_mod,
        "_segment_rows_for_uid",
        lambda db, uid: [
            {
                "ordinal": 1,
                "segment_type": "authored_body",
                "text": "For the record, you failed to provide the figures by end of day.",
            }
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="Prepare an investigation-style report for this case.",
            max_results=1,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["retaliation", "exclusion"],
                analysis_goal="hr_review",
            ),
        )
    )
    data = json.loads(payload)

    report = data["investigation_report"]
    assert report["version"] == "1"
    assert report["report_format"] == "investigation_briefing"
    assert report["interpretation_policy"]["version"] == "1"
    assert report["deadline_warnings"]["summary"]["warning_count"] >= 0
    assert report["section_order"] == [
        "executive_summary",
        "evidence_triage",
        "chronological_pattern_analysis",
        "language_analysis",
        "behaviour_analysis",
        "power_context_analysis",
        "evidence_table",
        "matter_evidence_index",
        "employment_issue_frameworks",
        "lawyer_issue_matrix",
        "actor_and_witness_map",
        "witness_question_packs",
        "promise_and_contradiction_analysis",
        "lawyer_briefing_memo",
        "controlled_factual_drafting",
        "case_dashboard",
        "cross_output_consistency",
        "skeptical_employer_review",
        "document_request_checklist",
        "overall_assessment",
        "missing_information",
    ]
    assert report["sections"]["executive_summary"]["status"] == "supported"
    assert report["sections"]["evidence_triage"]["status"] == "supported"
    assert report["sections"]["matter_evidence_index"]["status"] == "supported"
    assert report["sections"]["employment_issue_frameworks"]["status"] == "insufficient_evidence"
    assert report["sections"]["lawyer_issue_matrix"]["status"] == "insufficient_evidence"
    assert report["sections"]["actor_and_witness_map"]["status"] == "supported"
    assert report["sections"]["witness_question_packs"]["status"] == "supported"
    assert report["sections"]["promise_and_contradiction_analysis"]["status"] == "insufficient_evidence"
    assert report["sections"]["lawyer_briefing_memo"]["status"] == "supported"
    assert report["sections"]["controlled_factual_drafting"]["status"] == "supported"
    assert report["sections"]["case_dashboard"]["status"] == "supported"
    assert "timing_warnings" in report["sections"]["case_dashboard"]["case_dashboard"]["cards"]
    assert report["sections"]["cross_output_consistency"]["status"] == "supported"
    assert report["sections"]["skeptical_employer_review"]["status"] == "supported"
    assert report["sections"]["document_request_checklist"]["status"] == "supported"
    assert report["sections"]["executive_summary"]["entries"][0]["supporting_finding_ids"]
    assert report["sections"]["executive_summary"]["entries"][0]["claim_level"] in {
        "observed_fact",
        "pattern_concern",
        "stronger_interpretation",
    }
    assert report["sections"]["evidence_table"]["status"] == "supported"
    assert report["sections"]["missing_information"]["entries"]
