from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.mcp_models import (
    BehavioralCaseScopeInput,
    CasePartyInput,
    EmailAnswerContextInput,
    TriggerEventInput,
)


@pytest.mark.asyncio
async def test_email_answer_context_emits_retaliation_analysis(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-5a",
                        "subject": "Before complaint",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-01T10:00:00",
                        "conversation_id": "conv-case-5a",
                    },
                    chunk_id="chunk-case-5a",
                    text="Please send the figures by end of day.",
                    score=0.80,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-5b",
                        "subject": "After complaint",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-05T10:00:00",
                        "conversation_id": "conv-case-5b",
                    },
                    chunk_id="chunk-case-5b",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.95,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-5a": {
                    "uid": "uid-case-5a",
                    "body_text": "Please send the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-5a",
                },
                "uid-case-5b": {
                    "uid": "uid-case-5b",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>", "HR Example <hr@example.com>"],
                    "cc": ["Morgan Manager <manager@example.com>"],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-5b",
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
                    "Please send the figures by end of day."
                    if uid == "uid-case-5a"
                    else "For the record, you failed to provide the figures by end of day."
                ),
            }
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="Did things change after the complaint?",
            max_results=2,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["retaliation"],
                analysis_goal="hr_review",
                trigger_events=[
                    TriggerEventInput(
                        trigger_type="complaint",
                        date="2026-02-03",
                        actor=CasePartyInput(name="Alex Example", email="alex@example.com"),
                    )
                ],
            ),
        )
    )
    data = json.loads(payload)

    event = data["retaliation_analysis"]["trigger_events"][0]

    assert data["retaliation_analysis"]["version"] == "1"
    assert data["retaliation_analysis"]["trigger_event_count"] == 1
    assert event["assessment"]["analysis_quality"] == "medium"
    assert event["assessment"]["status"] == "adverse_shift_after_trigger"
    timeline_assessment = data["retaliation_analysis"]["retaliation_timeline_assessment"]
    assert timeline_assessment["protected_activity_timeline"][0]["trigger_type"] == "complaint"
    assert timeline_assessment["temporal_correlation_analysis"][0]["assessment_status"] == "adverse_shift_after_trigger"
    assert timeline_assessment["overall_evidentiary_rating"]["rating"] == "limited_or_mixed_timing_support"


@pytest.mark.asyncio
async def test_email_answer_context_emits_comparative_treatment(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-6a",
                        "subject": "Re: Figures follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-10T10:00:00",
                        "conversation_id": "conv-case-6",
                    },
                    chunk_id="chunk-case-6a",
                    text="For the record, you failed to provide the figures by end of day.",
                    score=0.95,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-6b",
                        "subject": "Figures follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-10T11:00:00",
                        "conversation_id": "conv-case-6",
                    },
                    chunk_id="chunk-case-6b",
                    text="Please send the figures by end of day.",
                    score=0.90,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-6a": {
                    "uid": "uid-case-6a",
                    "body_text": "For the record, you failed to provide the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-6",
                },
                "uid-case-6b": {
                    "uid": "uid-case-6b",
                    "body_text": "Please send the figures by end of day.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Pat Peer <pat@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-6",
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
        lambda: config_mod.Settings(
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
                    "For the record, you failed to provide the figures by end of day."
                    if uid == "uid-case-6a"
                    else "Please send the figures by end of day."
                ),
            }
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="Was Alex treated differently than Pat?",
            max_results=2,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                comparator_actors=[CasePartyInput(name="Pat Peer", email="pat@example.com")],
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["unequal_treatment"],
                analysis_goal="hr_review",
            ),
        )
    )
    data = json.loads(payload)

    comparator = data["comparative_treatment"]["comparator_summaries"][0]

    assert data["comparative_treatment"]["version"] == "2"
    assert data["comparative_treatment"]["summary"]["available_comparator_count"] == 1
    assert comparator["status"] == "comparator_available"
    assert comparator["comparison_quality"] == "high"
    assert comparator["comparison_quality_label"] == "high_quality_comparator"
    assert "same_sender_escalates_more_against_target" in comparator["unequal_treatment_signals"]
    assert comparator["comparator_matrix"]["row_count"] >= 1
    assert comparator["comparator_matrix"]["rows"][0]["issue_id"]
    assert comparator["comparator_matrix"]["rows"][0]["evidence"]
    assert data["comparative_treatment"]["summary"]["matrix_row_count"] >= 1


@pytest.mark.asyncio
async def test_email_answer_context_emits_communication_graph(monkeypatch):
    import src.config as config_mod
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-7a",
                        "subject": "Internal update",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-10T10:00:00",
                        "conversation_id": "conv-case-7",
                    },
                    chunk_id="chunk-case-7a",
                    text="Alex Example will be informed later.",
                    score=0.95,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-7b",
                        "subject": "Internal update 2",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-11T10:00:00",
                        "conversation_id": "conv-case-7",
                    },
                    chunk_id="chunk-case-7b",
                    text="Alex Example will be informed later.",
                    score=0.94,
                ),
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-7c",
                        "subject": "Internal update",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-12T10:00:00",
                        "conversation_id": "conv-case-7",
                    },
                    chunk_id="chunk-case-7c",
                    text="We decided to proceed and Alex Example is informed on this update.",
                    score=0.90,
                ),
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            return {
                "uid-case-7a": {
                    "uid": "uid-case-7a",
                    "body_text": "Alex Example will be informed later.",
                    "normalized_body_source": "body_text_html",
                    "to": ["HR Example <hr@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-7",
                },
                "uid-case-7b": {
                    "uid": "uid-case-7b",
                    "body_text": "Alex Example will be informed later.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Ops Example <ops@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-7",
                },
                "uid-case-7c": {
                    "uid": "uid-case-7c",
                    "body_text": "We decided to proceed and Alex Example is informed on this update.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": ["HR Example <hr@example.com>"],
                    "bcc": [],
                    "reply_context_from": "",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-7",
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
        lambda: config_mod.Settings(
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
                    "Alex Example will be informed later."
                    if uid != "uid-case-7c"
                    else "We decided to proceed and Alex Example is informed on this update."
                ),
            }
        ],
    )

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="Is there a graph-based exclusion pattern?",
            max_results=3,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
                allegation_focus=["exclusion"],
                analysis_goal="hr_review",
            ),
        )
    )
    data = json.loads(payload)

    finding_types = [finding["graph_signal_type"] for finding in data["communication_graph"]["graph_findings"]]

    assert data["communication_graph"]["version"] == "1"
    assert data["communication_graph"]["summary"]["target_email"] == "alex@example.com"
    assert "repeated_exclusion" in finding_types
    assert "visibility_asymmetry" in finding_types
    assert "decision_visibility_asymmetry" in finding_types
