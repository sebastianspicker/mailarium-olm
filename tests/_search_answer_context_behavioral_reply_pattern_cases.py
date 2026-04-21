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
async def test_email_answer_context_emits_selective_non_response_for_target_authored_request(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-3b-1",
                        "subject": "Need confirmation",
                        "sender_email": "alex@example.com",
                        "sender_name": "Alex Example",
                        "date": "2026-02-14T09:00:00",
                        "conversation_id": "conv-case-3b",
                    },
                    chunk_id="chunk-case-3b-1",
                    text="Please confirm whether the figures are approved.",
                    score=0.97,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-3b-2",
                        "subject": "Re: Need confirmation",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-14T12:00:00",
                        "conversation_id": "conv-case-3b",
                    },
                    chunk_id="chunk-case-3b-2",
                    text="Please update HR directly.",
                    score=0.96,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-3b-1": {
                    "uid": "uid-case-3b-1",
                    "body_text": "Please confirm whether the figures are approved.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Morgan Manager <manager@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-3b",
                },
                "uid-case-3b-2": {
                    "uid": "uid-case-3b-2",
                    "body_text": "Please update HR directly.",
                    "normalized_body_source": "body_text_html",
                    "to": ["HR Example <hr@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-3b",
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
                "text": (
                    "Please confirm whether the figures are approved." if uid == "uid-case-3b-1" else "Please update HR directly."
                ),
            }
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="Was there selective non-response?",
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
    target_candidate = next(candidate for candidate in data["candidates"] if candidate["uid"] == "uid-case-3b-1")
    behavior_ids = [
        candidate["behavior_id"] for candidate in target_candidate["message_findings"]["authored_text"]["behavior_candidates"]
    ]

    assert target_candidate["reply_pairing"]["response_status"] == "indirect_activity_without_direct_reply"
    assert target_candidate["reply_pairing"]["supports_selective_non_response_inference"] is True
    assert "selective_non_response" in behavior_ids


@pytest.mark.asyncio
async def test_email_answer_context_emits_case_patterns(monkeypatch):
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod
    from src.config import get_settings

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-4a",
                        "subject": "Process update",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-10T10:00:00",
                        "conversation_id": "conv-case-4a",
                    },
                    chunk_id="chunk-case-4a",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.95,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-4b",
                        "subject": "Follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-14T10:00:00",
                        "conversation_id": "conv-case-4b",
                    },
                    chunk_id="chunk-case-4b",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.94,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-4a": {
                    "uid": "uid-case-4a",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>", "HR Example <hr@example.com>"],
                    "cc": ["Morgan Manager <manager@example.com>"],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-4a",
                },
                "uid-case-4b": {
                    "uid": "uid-case-4b",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>", "HR Example <hr@example.com>"],
                    "cc": ["Morgan Manager <manager@example.com>"],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-4b",
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
    monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "18000")
    get_settings.cache_clear()

    try:
        payload = await search_mod.email_answer_context(
            EmailAnswerContextInput(
                question="Is there a repeated pattern?",
                max_results=2,
                case_scope=BehavioralCaseScopeInput(
                    target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                    allegation_focus=["retaliation", "exclusion"],
                    analysis_goal="hr_review",
                ),
            )
        )
    finally:
        get_settings.cache_clear()
    data = json.loads(payload)

    assert data["case_patterns"]["version"] == "1"
    assert data["case_patterns"]["summary"]["message_count_with_findings"] == 2
    escalation_pattern = next(summary for summary in data["case_patterns"]["behavior_patterns"] if summary["key"] == "escalation")
    assert escalation_pattern["primary_recurrence"] == "repeated"
    assert "targeted" not in escalation_pattern["recurrence_flags"]
    assert data["case_patterns"]["directional_summaries"] == []
    assert data["case_patterns"]["corpus_behavioral_review"]["message_count_reviewed"] == 2
    recurring_phrases = data["case_patterns"]["corpus_behavioral_review"]["recurring_phrases"]
    assert any(item["phrase"] == "for the record" for item in recurring_phrases)
    assert data["case_patterns"]["corpus_behavioral_review"]["escalation_points"][0]["uid"] == "uid-case-4a"
