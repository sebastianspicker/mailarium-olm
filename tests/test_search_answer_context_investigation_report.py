from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.mcp_models import (
    BehavioralCaseScopeInput,
    CasePartyInput,
    EmailAnswerContextInput,
)

from ._search_answer_context_investigation_report_report_case import *  # noqa: F403


@pytest.mark.asyncio
async def test_email_answer_context_emits_multi_source_case_bundle(monkeypatch):
    import src.tools.search as search_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-8",
                        "subject": "Policy follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-14T10:00:00",
                        "conversation_id": "conv-case-8",
                    },
                    chunk_id="chunk-case-8-body",
                    text="Please see the attached policy update before the meeting.",
                    score=0.95,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-8",
                        "subject": "Policy follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-14T10:00:00",
                        "conversation_id": "conv-case-8",
                        "attachment_filename": "policy.pdf",
                        "mime_type": "application/pdf",
                        "is_attachment": True,
                        "extraction_state": "text_extracted",
                    },
                    chunk_id="chunk-case-8-att",
                    text="Section 4 requires written approval for schedule changes.",
                    score=0.91,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-8": {
                    "uid": "uid-case-8",
                    "subject": "Policy follow-up",
                    "date": "2026-02-14T10:00:00",
                    "body_text": "Please see the attached policy update before the meeting.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-8",
                    "meeting_data": {
                        "OPFMeetingLocation": "Room A",
                        "OPFMeetingStartDate": "2026-02-14T09:00:00",
                    },
                }
            }

        def attachments_for_email(self, uid):
            assert uid == "uid-case-8"
            return [
                {
                    "name": "policy.pdf",
                    "mime_type": "application/pdf",
                    "size": 2048,
                    "content_id": None,
                    "is_inline": False,
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

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="What sources support the policy concern?",
            max_results=2,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["retaliation", "exclusion"],
                analysis_goal="hr_review",
            ),
        )
    )
    data = json.loads(payload)

    source_types = {source["source_type"] for source in data["multi_source_case_bundle"]["sources"]}

    assert data["multi_source_case_bundle"]["version"] == "1"
    assert data["multi_source_case_bundle"]["summary"]["source_type_counts"] == {
        "email": 1,
        "formal_document": 1,
        "meeting_note": 1,
    }
    assert data["multi_source_case_bundle"]["summary"]["missing_source_types"] == [
        "attachment",
        "chat_log",
        "note_record",
        "time_record",
        "participation_record",
    ]
    assert data["multi_source_case_bundle"]["summary"]["documentary_source_count"] == 2
    assert data["multi_source_case_bundle"]["summary"]["weak_extraction_source_count"] == 0
    assert data["multi_source_case_bundle"]["summary"]["chronology_anchor_count"] == 3
    assert source_types == {"email", "formal_document", "meeting_note"}
    formal_document = next(
        source for source in data["multi_source_case_bundle"]["sources"] if source["source_type"] == "formal_document"
    )
    assert formal_document["documentary_support"]["extraction_state"] == "text_extracted"
    assert formal_document["document_locator"]["chunk_id"] == "chunk-case-8-att"
    assert any(link["link_type"] == "attached_to_email" for link in data["multi_source_case_bundle"]["source_links"])
    assert any(
        profile["source_type"] == "formal_document" and profile["available"] is True
        for profile in data["multi_source_case_bundle"]["source_type_profiles"]
    )


@pytest.mark.asyncio
async def test_email_answer_context_emits_finding_evidence_index_and_evidence_table(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-9",
                        "subject": "Follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-13T10:00:00",
                        "conversation_id": "conv-case-9",
                    },
                    chunk_id="chunk-case-9",
                    text="For the record, you failed to provide the figures.",
                    score=0.95,
                )
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-9": {
                    "uid": "uid-case-9",
                    "body_text": (
                        "For the record, you failed to provide the figures.\n"
                        "\n"
                        "On Tue, Alex Example wrote:\n"
                        "You failed to provide the figures."
                    ),
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": ["HR Example <hr@example.com>"],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-9",
                }
            }

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
                "text": "For the record, you failed to provide the figures.",
            },
            {
                "ordinal": 2,
                "segment_type": "quoted_reply",
                "text": "From: Alex Example <alex@example.com>\nFor the record, you failed to provide the figures.",
            },
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="What is the evidence chain for this behavior?",
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

    assert data["finding_evidence_index"]["version"] == "1"
    assert data["finding_evidence_index"]["finding_count"] >= 2
    message_finding = next(
        finding for finding in data["finding_evidence_index"]["findings"] if finding["finding_scope"] == "message_behavior"
    )
    quoted_finding = next(
        finding for finding in data["finding_evidence_index"]["findings"] if finding["finding_scope"] == "quoted_message_behavior"
    )
    assert message_finding["finding_id"].startswith("message:uid-case-9:authored:")
    assert message_finding["supporting_evidence"][0]["message_or_document_id"] == "uid-case-9"
    assert quoted_finding["quote_ambiguity"]["downgraded_due_to_quote_ambiguity"] is False
    assert quoted_finding["quote_ambiguity"]["quote_attribution_status"] == "explicit_header"
    assert quoted_finding["supporting_evidence"][0]["text_attribution"]["speaker_status"] == "inferred"
    assert quoted_finding["supporting_evidence"][0]["text_attribution"]["authored_quoted_inferred_status"] == "quoted"
    assert quoted_finding["supporting_evidence"][0]["text_attribution"]["quote_attribution_status"] == "explicit_header"
    assert data["evidence_table"]["version"] == "1"
    assert data["evidence_table"]["row_count"] >= 2
    assert any(row["finding_id"] == message_finding["finding_id"] for row in data["evidence_table"]["rows"])
    assert data["quote_attribution_metrics"]["version"] == "1"
    assert data["quote_attribution_metrics"]["status_counts"]["explicit_header"] == 1
    assert data["quote_attribution_metrics"]["downgraded_quote_finding_count"] == 0


@pytest.mark.asyncio
async def test_email_answer_context_emits_strength_scoring_and_confidence_split(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-10a",
                        "subject": "Follow-up A",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-13T10:00:00",
                        "conversation_id": "conv-case-10",
                    },
                    chunk_id="chunk-case-10a",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.95,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-10b",
                        "subject": "Follow-up B",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-14T10:00:00",
                        "conversation_id": "conv-case-10",
                    },
                    chunk_id="chunk-case-10b",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.94,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-10a": {
                    "uid": "uid-case-10a",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>", "HR Example <hr@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-10",
                },
                "uid-case-10b": {
                    "uid": "uid-case-10b",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>", "HR Example <hr@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-10",
                },
            }

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
            question="How strong is the repeated escalation pattern?",
            max_results=2,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["retaliation", "exclusion"],
                analysis_goal="hr_review",
            ),
        )
    )
    data = json.loads(payload)

    assert data["behavioral_strength_rubric"]["version"] == "1"
    assert "strong_indicator" in data["behavioral_strength_rubric"]["labels"]
    message_finding = next(
        finding for finding in data["finding_evidence_index"]["findings"] if finding["finding_scope"] == "message_behavior"
    )
    pattern_finding = next(
        finding for finding in data["finding_evidence_index"]["findings"] if finding["finding_scope"] == "case_pattern"
    )
    assert message_finding["evidence_strength"]["label"] in {
        "weak_indicator",
        "moderate_indicator",
        "strong_indicator",
    }
    assert message_finding["confidence_split"]["evidence_confidence"]["label"] in {"low", "medium", "high"}
    assert pattern_finding["confidence_split"]["interpretation_confidence"]["label"] in {"low", "medium", "high"}
    assert isinstance(pattern_finding["alternative_explanations"], list)
    table_row = next(row for row in data["evidence_table"]["rows"] if row["finding_id"] == message_finding["finding_id"])
    assert table_row["evidence_strength"] == message_finding["evidence_strength"]["label"]
