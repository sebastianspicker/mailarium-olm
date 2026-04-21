from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.mcp_models import (
    BehavioralCaseScopeInput,
    BehavioralOrgContextInput,
    CasePartyInput,
    EmailAnswerContextInput,
    ReportingLineInput,
    RoleFactInput,
    TriggerEventInput,
)


@pytest.mark.asyncio
async def test_email_answer_context_emits_case_bundle_and_applies_case_scope_dates(monkeypatch):
    import src.tools.search as search_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            assert query == "What happened after the complaint?"
            assert top_k == 1
            assert kwargs["date_from"] == "2026-02-01"
            assert kwargs["date_to"] == "2026-02-28"
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-1",
                        "subject": "Re: Complaint follow-up",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-12T10:00:00",
                        "conversation_id": "conv-case-1",
                    },
                    chunk_id="chunk-case-1",
                    text="We should discuss this privately tomorrow morning.",
                    score=0.92,
                )
            ]

    class DummyDB:
        conn = None

        def get_emails_full_batch(self, uids):
            assert uids == ["uid-case-1"]
            return {
                "uid-case-1": {
                    "uid": "uid-case-1",
                    "body_text": "Intro. We should discuss this privately tomorrow morning. Thanks.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
                    "bcc": [],
                    "reply_context_from": "alex@example.com",
                    "reply_context_to_json": "[]",
                    "conversation_id": "conv-case-1",
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

    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(
            question="What happened after the complaint?",
            max_results=1,
            case_scope=BehavioralCaseScopeInput(
                case_label="complaint-follow-up",
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com", role_hint="employee"),
                comparator_actors=[CasePartyInput(name="Pat Peer", email="pat@example.com", role_hint="employee")],
                suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com", role_hint="manager")],
                date_from="2026-02-01",
                date_to="2026-02-28",
                allegation_focus=["retaliation", "exclusion"],
                analysis_goal="hr_review",
                context_notes="Complaint filed on 2026-02-03.",
                org_context=BehavioralOrgContextInput(
                    role_facts=[
                        RoleFactInput(
                            person=CasePartyInput(name="Morgan Manager", email="manager@example.com"),
                            role_type="manager",
                            title="Head of Unit",
                            department="Operations",
                        )
                    ],
                    reporting_lines=[
                        ReportingLineInput(
                            manager=CasePartyInput(name="Morgan Manager", email="manager@example.com"),
                            report=CasePartyInput(name="Alex Example", email="alex@example.com"),
                        )
                    ],
                ),
            ),
        )
    )
    data = json.loads(payload)

    assert data["search"]["date_from"] == "2026-02-01"
    assert data["search"]["date_to"] == "2026-02-28"
    assert data["case_bundle"]["bundle_id"].startswith("case-")
    assert data["case_bundle"]["scope"]["case_label"] == "complaint-follow-up"
    assert data["case_bundle"]["scope"]["target_person"]["name"] == "Alex Example"
    assert data["case_bundle"]["scope"]["comparator_actors"][0]["email"] == "pat@example.com"
    assert data["case_bundle"]["scope"]["suspected_actors"][0]["email"] == "manager@example.com"
    assert data["case_bundle"]["scope"]["allegation_focus"] == ["retaliation", "exclusion"]
    assert data["case_bundle"]["scope"]["analysis_goal"] == "hr_review"
    assert data["case_bundle"]["scope"]["target_person"]["actor_id"]
    assert data["case_bundle"]["scope"]["suspected_actors"][0]["actor_id"] == data["candidates"][0]["sender_actor_id"]
    assert data["candidates"][0]["sender_actor_resolution"] == {"resolved_by": "email", "ambiguous": False}
    assert data["actor_identity_graph"]["stats"]["actor_count"] == 2
    assert data["actor_identity_graph"]["unresolved_references"] == []
    assert data["power_context"]["org_context_provided"] is True
    assert data["power_context"]["missing_org_context"] is False
    assert data["power_context"]["supplied_role_facts"][0]["role_type"] == "manager"
    assert data["behavioral_taxonomy"]["version"] == "1"
    assert len(data["behavioral_taxonomy"]["categories"]) == 10
    assert data["behavioral_taxonomy"]["focus_category_ids"] == [
        "retaliatory_sequence",
        "escalation_pressure",
        "selective_non_response",
        "exclusion",
        "withholding_information",
    ]
    manager_actor = next(
        actor for actor in data["actor_identity_graph"]["actors"] if actor["primary_email"] == "manager@example.com"
    )
    assert manager_actor["role_context"]["supplied_role_facts"][0]["role_type"] == "manager"


@pytest.mark.asyncio
async def test_email_answer_context_prefers_top_level_dates_over_case_scope(monkeypatch):
    import src.tools.search as search_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            assert kwargs["date_from"] == "2026-03-01"
            assert kwargs["date_to"] == "2026-03-31"
            return []

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {}

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
            question="What changed in March?",
            max_results=1,
            date_from="2026-03-01",
            date_to="2026-03-31",
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.com"),
                date_from="2026-02-01",
                date_to="2026-02-28",
                allegation_focus=["retaliation"],
                analysis_goal="internal_review",
            ),
        )
    )
    data = json.loads(payload)

    assert data["search"]["date_from"] == "2026-03-01"
    assert data["search"]["date_to"] == "2026-03-31"


@pytest.mark.asyncio
async def test_email_answer_context_emits_authored_vs_quoted_language_rhetoric(monkeypatch):
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

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
                        "For the record, you failed to provide the figures. "
                        "As already stated, please just send them today."
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


@pytest.mark.asyncio
async def test_email_answer_context_emits_case_patterns(monkeypatch):
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

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
    data = json.loads(payload)

    assert data["case_patterns"]["version"] == "1"
    assert data["case_patterns"]["summary"]["message_count_with_findings"] == 2
    escalation_pattern = next(
        summary for summary in data["case_patterns"]["behavior_patterns"] if summary["key"] == "escalation"
    )
    assert escalation_pattern["primary_recurrence"] == "repeated"
    assert "targeted" in escalation_pattern["recurrence_flags"]
    assert (
        data["case_patterns"]["directional_summaries"][0]["target_actor_id"]
        == data["case_bundle"]["scope"]["target_person"]["actor_id"]
    )


@pytest.mark.asyncio
async def test_email_answer_context_emits_retaliation_analysis(monkeypatch):
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
    assert event["before_after"]["before_message_count"] == 1
    assert event["before_after"]["after_message_count"] == 1
    assert event["before_after"]["metrics"]["response_time"]["status"] == "not_available"
    assert event["before_after"]["metrics"]["escalation_rate"]["delta"] == 1
    assert event["assessment"]["status"] == "possible_retaliatory_shift"


@pytest.mark.asyncio
async def test_email_answer_context_emits_comparative_treatment(monkeypatch):
    import src.tools.search as search_mod
    import src.tools.search_answer_context as answer_context_mod

    class DummyRetriever:
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                SimpleNamespace(
                    metadata={
                        "uid": "uid-case-6a",
                        "subject": "Target follow-up",
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
                        "subject": "Comparator follow-up",
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

    assert data["comparative_treatment"]["version"] == "1"
    assert data["comparative_treatment"]["summary"]["available_comparator_count"] == 1
    assert comparator["status"] == "comparator_available"
    assert comparator["similarity_checks"]["shared_process_step"] is True
    assert "same_sender_escalates_more_against_target" in comparator["unequal_treatment_signals"]


@pytest.mark.asyncio
async def test_email_answer_context_emits_communication_graph(monkeypatch):
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
                        "subject": "Direct note",
                        "sender_email": "manager@example.com",
                        "sender_name": "Morgan Manager",
                        "date": "2026-02-12T10:00:00",
                        "conversation_id": "conv-case-7",
                    },
                    chunk_id="chunk-case-7c",
                    text="Please send the figures.",
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
                    "body_text": "Please send the figures.",
                    "normalized_body_source": "body_text_html",
                    "to": ["Alex Example <alex@example.com>"],
                    "cc": [],
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
        answer_context_mod,
        "_segment_rows_for_uid",
        lambda db, uid: [
            {
                "ordinal": 1,
                "segment_type": "authored_body",
                "text": (
                    "Alex Example will be informed later."
                    if uid != "uid-case-7c"
                    else "Please send the figures."
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
    assert data["multi_source_case_bundle"]["summary"]["missing_source_types"] == ["attachment", "chat_log"]
    assert source_types == {"email", "formal_document", "meeting_note"}
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
        finding
        for finding in data["finding_evidence_index"]["findings"]
        if finding["finding_scope"] == "quoted_message_behavior"
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
    assert report["section_order"] == [
        "executive_summary",
        "chronological_pattern_analysis",
        "language_analysis",
        "behaviour_analysis",
        "power_context_analysis",
        "evidence_table",
        "overall_assessment",
        "missing_information",
    ]
    assert report["sections"]["executive_summary"]["status"] == "supported"
    assert report["sections"]["executive_summary"]["entries"][0]["supporting_finding_ids"]
    assert report["sections"]["executive_summary"]["entries"][0]["claim_level"] in {
        "observed_fact",
        "pattern_concern",
        "stronger_interpretation",
    }
    assert report["sections"]["evidence_table"]["status"] == "supported"
    assert report["sections"]["missing_information"]["entries"]
