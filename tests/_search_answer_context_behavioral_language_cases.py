from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.mcp_models import (
    BehavioralCaseScopeInput,
    CasePartyInput,
    EmailAnswerContextInput,
)


async def test_email_answer_context_emits_authored_vs_quoted_language_rhetoric(monkeypatch):
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod
    from src.config import get_settings

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-2",
                        "subject": "Re: Process follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-13T10:00:00",
                        "conversation_id": "conv-case-2",
                    },
                    chunk_id="chunk-case-2",
                    text="For the record, you failed to provide the figures.",
                    score=0.95,
                )
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-2": {
                    "uid": "uid-case-2",
                    "body_text": (
                        "For the record, you failed to provide the figures. As already stated, please just send them today."
                    ),
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "alex@example.com",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-2",
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
        answer_context_mod,
        "_segment_rows_for_uid",
        lambda db, uid: [
            {
                "ordinal": 1,
                "segment_type": "authored_body",
                "text": "For the record, you failed to provide the figures. As already stated, please just send them today.",
            },
            {
                "ordinal": 2,
                "segment_type": "quoted_reply",
                "text": "It appears questions remain about the timeline.",
            },
        ],
    )
    monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "18000")
    get_settings.cache_clear()

    try:
        payload = await search_mod.email_answer_context(
            EmailAnswerContextInput(
                question="What was the tone of the follow-up?",
                max_results=1,
                case_scope=BehavioralCaseScopeInput(
                    target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                    allegation_focus=["retaliation"],
                    analysis_goal="hr_review",
                ),
            )
        )
    finally:
        get_settings.cache_clear()
    data = json.loads(payload)

    authored_signal_ids = [
        signal["signal_id"] for signal in data["candidates"][0]["language_rhetoric"]["authored_text"]["signals"]
    ]
    quoted_block = data["candidates"][0]["language_rhetoric"]["quoted_blocks"][0]

    assert data["candidates"][0]["language_rhetoric"]["version"] == "1"
    assert "institutional_pressure_framing" in authored_signal_ids
    assert "implicit_accusation" in authored_signal_ids
    assert "dismissiveness" in authored_signal_ids
    assert quoted_block["segment_ordinal"] == 2
    assert quoted_block["analysis"]["text_scope"] == "quoted_text"
    assert quoted_block["analysis"]["signals"][0]["signal_id"] == "strategic_ambiguity"


@pytest.mark.asyncio
async def test_email_answer_context_emits_message_findings_with_counter_indicators(monkeypatch):
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-3",
                        "subject": "Process update",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-14T10:00:00",
                        "conversation_id": "conv-case-3",
                    },
                    chunk_id="chunk-case-3",
                    text="It appears we decided to proceed without delay. Alex Example will be informed later.",
                    score=0.93,
                )
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-3": {
                    "uid": "uid-case-3",
                    "body_text": "It appears we decided to proceed without delay. Alex Example will be informed later.",
                    "normalized_body_source": "body_text_html",
                    "to": ["HR Example <hr@example.com>"],
                    "cc": ["Morgan Manager <manager@example.com>"],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-3",
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
        answer_context_mod,
        "_segment_rows_for_uid",
        lambda db, uid: [
            {
                "ordinal": 1,
                "segment_type": "authored_body",
                "text": "It appears we decided to proceed without delay. Alex Example will be informed later.",
            }
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="What behaviour cues are present?",
            max_results=1,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["exclusion"],
                analysis_goal="hr_review",
            ),
        )
    )
    data = json.loads(payload)

    behavior_ids = [
        candidate["behavior_id"]
        for candidate in data["candidates"][0]["message_findings"]["authored_text"]["behavior_candidates"]
    ]

    assert data["candidates"][0]["message_findings"]["version"] == "1"
    assert "deadline_pressure" in behavior_ids
    assert "exclusion" in behavior_ids
    assert "withholding" in behavior_ids
    assert (
        "Some rhetorical cues remained wording-only because message-level behavioural support was insufficient."
        in data["candidates"][0]["message_findings"]["authored_text"]["counter_indicators"]
    )


def test_compact_message_findings_preserves_stable_authored_text_shape():
    from src.tools.search_answer_context import _compact_message_findings_payload

    compacted = _compact_message_findings_payload(
        {
            "quoted_blocks": [
                {
                    "segment_ordinal": 2,
                    "quote_attribution_status": "resolved",
                    "findings": {
                        "behavior_candidates": [{"behavior_id": "withholding", "label": "Withholding"}],
                    },
                }
            ]
        }
    )

    assert compacted["version"] == "1"
    assert compacted["authored_text"]["text_scope"] == "authored_text"
    assert compacted["authored_text"]["behavior_candidate_count"] == 0
    assert compacted["authored_text"]["behavior_candidates"] == []
    assert compacted["summary"]["total_behavior_candidate_count"] == 1
    assert compacted["quoted_blocks"][0]["findings"]["behavior_candidate_count"] == 1
