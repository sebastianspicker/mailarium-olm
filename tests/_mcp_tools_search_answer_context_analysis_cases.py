"""Answer-context timeline, speaker attribution, thread graph, weak evidence, and policy behavior."""

import json
import sqlite3

import pytest

from .helpers.answer_context_fakes import _AnswerContextDeps
from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result


def _timeline_email(uid: str, body_text: str) -> dict[str, str]:
    return {
        "uid": uid,
        "body_text": body_text,
        "normalized_body_source": "body_text",
        "forensic_body_text": "",
        "forensic_body_source": "",
    }


def _timeline_thread_email(uid: str, sender_email: str, sender_name: str, date: str) -> dict[str, str]:
    return {
        "uid": uid,
        "subject": "Rollout",
        "sender_email": sender_email,
        "sender_name": sender_name,
        "date": date,
        "conversation_id": "conv-time",
    }


def _speaker_thread_email(uid: str, sender_email: str, sender_name: str, date: str) -> dict[str, str]:
    return {
        "uid": uid,
        "subject": "Figures",
        "sender_email": sender_email,
        "sender_name": sender_name,
        "date": date,
        "conversation_id": "conv-speak",
    }


class _TimelineRetriever(_BasicRetriever):
    def search_filtered(self, query, top_k=10, **kwargs):
        return [
            _make_result(
                uid="uid-time-2",
                chunk_id="chunk-time-2",
                text="Decision made on the rollout.",
                distance=0.09,
                conversation_id="conv-time",
                date="2025-06-03",
            ),
            _make_result(
                uid="uid-time-1",
                chunk_id="chunk-time-1",
                text="Initial request for the rollout.",
                distance=0.11,
                conversation_id="conv-time",
                date="2025-06-01",
            ),
            _make_result(
                uid="uid-time-3",
                chunk_id="chunk-time-3",
                text="Follow-up confirmation after rollout.",
                distance=0.14,
                conversation_id="conv-time",
                date="2025-06-05",
            ),
        ]


class _TimelineDB:
    conn = None

    def get_emails_full_batch(self, uids):
        return {
            "uid-time-1": _timeline_email("uid-time-1", "Initial request for the rollout."),
            "uid-time-2": _timeline_email("uid-time-2", "Decision made on the rollout."),
            "uid-time-3": _timeline_email("uid-time-3", "Follow-up confirmation after rollout."),
        }

    def get_thread_emails(self, conversation_id):
        assert conversation_id == "conv-time"
        return [
            _timeline_thread_email("uid-time-1", "employee@example.test", "Alice", "2025-06-01"),
            _timeline_thread_email("uid-time-2", "bob@example.com", "Bob", "2025-06-03"),
            _timeline_thread_email("uid-time-3", "carol@example.com", "Carol", "2025-06-05"),
        ]


class _SpeakerRetriever(_BasicRetriever):
    def search_filtered(self, query, top_k=10, **kwargs):
        return [
            _make_result(
                uid="uid-speak-1",
                chunk_id="chunk-speak-1",
                text="Replying inline to the request.",
                distance=0.09,
                conversation_id="conv-speak",
                date="2025-06-03",
            )
        ]


class _SpeakerDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE TABLE message_segments (email_uid TEXT, ordinal INTEGER, segment_type TEXT, depth INTEGER, "
            "text TEXT, source_surface TEXT, provenance_json TEXT)"
        )
        self.conn.execute(
            "INSERT INTO message_segments VALUES "
            "('uid-speak-1', 0, 'authored_body', 0, 'Replying inline to the request.', 'body_text', '{}')"
        )
        self.conn.execute(
            "INSERT INTO message_segments VALUES "
            "('uid-speak-1', 1, 'quoted_reply', 1, 'Can you send the figures?', 'body_text', '{}')"
        )
        self.conn.commit()

    def get_emails_full_batch(self, uids):
        return {
            "uid-speak-1": {
                "uid": "uid-speak-1",
                "body_text": "Replying inline to the request.\n\n> Can you send the figures?",
                "normalized_body_source": "body_text",
                "forensic_body_text": "",
                "forensic_body_source": "",
                "reply_context_from": "Bob Example (mailto:bob@example.com)",
            }
        }

    def get_thread_emails(self, conversation_id):
        return [
            _speaker_thread_email("uid-speak-1", "employee@example.test", "Alice", "2025-06-03"),
            _speaker_thread_email("uid-speak-0", "bob@example.com", "Bob", "2025-06-02"),
        ]


@pytest.mark.asyncio
async def test_email_answer_context_adds_timeline_summary(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(_TimelineRetriever(), _TimelineDB()))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="How did the rollout evolve?", max_results=3)
    )
    data = json.loads(payload)

    assert data["timeline"]["event_count"] == 3
    assert data["timeline"]["date_range"] == {"first": "2025-06-01", "last": "2025-06-05"}
    assert data["timeline"]["first_uid"] == "uid-time-1"
    assert data["timeline"]["last_uid"] == "uid-time-3"
    assert data["timeline"]["key_transition_uid"] == "uid-time-2"
    assert [event["uid"] for event in data["timeline"]["events"]] == ["uid-time-1", "uid-time-2", "uid-time-3"]


@pytest.mark.asyncio
async def test_email_answer_context_adds_speaker_attribution(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    deps = _AnswerContextDeps(_SpeakerRetriever(), _SpeakerDB())
    monkeypatch.setattr(search_mod, "_deps", deps)
    try:
        payload = await search_mod.email_answer_context(
            EmailAnswerContextInput(question="Who said what about the figures?", max_results=1)
        )
        data = json.loads(payload)

        attribution = data["candidates"][0]["speaker_attribution"]
        assert attribution["authored_speaker"]["email"] == "employee@example.test"
        assert attribution["authored_speaker"]["source"] == "canonical_sender"
        assert attribution["quoted_blocks"][0]["speaker_email"] == "bob@example.com"
        assert attribution["quoted_blocks"][0]["source"] == "reply_context_from"
        assert attribution["quoted_blocks"][0]["confidence"] == pytest.approx(0.8)
    finally:
        deps.db.conn.close()


@pytest.mark.asyncio
async def test_email_answer_context_adds_thread_graph(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-thread-1",
                    chunk_id="chunk-thread-1",
                    text="Follow-up in the budget thread.",
                    distance=0.08,
                    conversation_id="conv-thread",
                    date="2025-06-05",
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-thread-1": {
                    "uid": "uid-thread-1",
                    "body_text": "Follow-up in the budget thread.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                    "conversation_id": "conv-thread",
                    "in_reply_to": "parent-msg@example.com",
                    "references": ["root-msg@example.com", "parent-msg@example.com"],
                    "inferred_parent_uid": "uid-parent",
                    "inferred_thread_id": "thread-inferred-1",
                    "inferred_match_reason": "base_subject,participants",
                    "inferred_match_confidence": 0.91,
                }
            }

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(EmailAnswerContextInput(question="How is this thread linked?", max_results=1))
    data = json.loads(payload)

    graph = data["candidates"][0]["thread_graph"]
    assert graph["canonical"]["conversation_id"] == "conv-thread"
    assert graph["canonical"]["in_reply_to"] == "parent-msg@example.com"
    assert graph["canonical"]["references"] == ["root-msg@example.com", "parent-msg@example.com"]
    assert graph["canonical"]["has_thread_links"] is True
    assert graph["inferred"]["parent_uid"] == "uid-parent"
    assert graph["inferred"]["thread_id"] == "thread-inferred-1"
    assert graph["inferred"]["reason"] == "base_subject,participants"
    assert graph["inferred"]["confidence"] == pytest.approx(0.91)
    assert graph["inferred"]["has_parent_link"] is True


@pytest.mark.asyncio
async def test_email_answer_context_adds_weak_message_semantics(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-weak-1",
                    chunk_id="chunk-weak-1",
                    text="The weak source-shell message matched.",
                    distance=0.08,
                    conversation_id="",
                    date="2025-06-05",
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-weak-1": {
                    "uid": "uid-weak-1",
                    "body_text": "Source-shell message with no recoverable visible body text.",
                    "normalized_body_source": "source_shell_summary",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                    "conversation_id": "",
                    "body_kind": "content",
                    "body_empty_reason": "source_shell_only",
                    "recovery_strategy": "source_shell_summary",
                    "recovery_confidence": 0.2,
                }
            }

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="Which source-shell message discussed the certificate?", max_results=1)
    )
    data = json.loads(payload)

    weak_message = data["candidates"][0]["weak_message"]
    assert weak_message["code"] == "source_shell_only"
    assert weak_message["label"] == "Source-shell message"
    assert weak_message["body_empty_reason"] == "source_shell_only"


@pytest.mark.asyncio
async def test_email_answer_context_adds_answer_policy(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-policy-1",
                    chunk_id="chunk-policy-1",
                    text="Alice wrote: Please approve the budget.",
                    distance=0.05,
                    conversation_id="conv-policy",
                    date="2025-06-05",
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-policy-1": {
                    "uid": "uid-policy-1",
                    "body_text": "Alice wrote: Please approve the budget.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "Alice wrote: Please approve the budget.",
                    "forensic_body_source": "raw_body_text",
                    "conversation_id": "conv-policy",
                }
            }

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="What exactly did Alice write about the budget?", max_results=1)
    )
    data = json.loads(payload)

    policy = data["answer_policy"]
    assert policy["decision"] == "answer"
    assert policy["verification_mode"] == "verify_forensic"
    assert policy["max_citations"] == 1
    assert policy["cite_candidate_uids"] == ["uid-policy-1"]
    assert policy["cite_candidate_references"] == [
        {"uid": "uid-policy-1", "evidence_handle": "email:uid-policy-1:retrieval:body_text:0:39"}
    ]
    assert policy["refuse_to_overclaim"] is True
    contract = data["final_answer_contract"]
    assert contract["decision"] == "answer"
    assert contract["answer_format"]["shape"] == "single_paragraph"
    assert contract["citation_format"]["style"] == "inline_reference_brackets"
    assert contract["required_citation_uids"] == ["uid-policy-1"]
    assert contract["required_citation_handles"] == ["email:uid-policy-1:retrieval:body_text:0:39"]
    final_answer = data["final_answer"]
    assert final_answer["decision"] == "answer"
    assert final_answer["citations"] == ["email:uid-policy-1:retrieval:body_text:0:39"]
    assert final_answer["verification_mode"] == "verify_forensic"
    assert "[ref:email:uid-policy-1:retrieval:body_text:0:39]" in final_answer["text"]
