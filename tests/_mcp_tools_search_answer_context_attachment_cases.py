"""Answer-context attachment evidence, thread grouping, confidence, and ambiguity behavior."""

import json

import pytest

from .helpers.answer_context_fakes import _AnswerContextDeps
from .helpers.mcp_tool_extended_fakes import _assert_strong_attachment_candidate
from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result


class _ConversationGroupRetriever(_BasicRetriever):
    def search_filtered(self, query, top_k=10, **kwargs):
        return [
            _make_result(
                uid="uid-thread-2",
                chunk_id="chunk-thread-2",
                text="Please send the updated report by Friday.",
                distance=0.10,
            ),
            _make_result(
                uid="uid-thread-1",
                chunk_id="chunk-thread-1",
                text="We decided to go with vendor A.",
                distance=0.15,
            ),
        ]


class _ConversationGroupDB:
    conn = None

    def get_emails_full_batch(self, uids):
        return {
            "uid-thread-1": {
                "uid": "uid-thread-1",
                "body_text": "We decided to go with vendor A.",
                "normalized_body_source": "body_text",
                "forensic_body_text": "",
                "forensic_body_source": "",
            },
            "uid-thread-2": {
                "uid": "uid-thread-2",
                "body_text": "Please send the updated report by Friday.",
                "normalized_body_source": "body_text_html",
                "forensic_body_text": "",
                "forensic_body_source": "",
            },
        }

    def get_thread_emails(self, conversation_id):
        assert conversation_id == "conv-1"
        return [
            {
                "uid": "uid-thread-1",
                "subject": "Budget Review",
                "sender_email": "employee@example.test",
                "sender_name": "Alice",
                "date": "2025-06-01",
                "conversation_id": "conv-1",
            },
            {
                "uid": "uid-thread-2",
                "subject": "Budget Review",
                "sender_email": "bob@example.com",
                "sender_name": "Bob",
                "date": "2025-06-02",
                "conversation_id": "conv-1",
            },
        ]


@pytest.mark.asyncio
async def test_email_answer_context_separates_attachment_candidates(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-att-1",
                    chunk_id="uid-att-1__att_abc__0",
                    text='[Attachment: budget.xlsx from email "Budget Review" (2025-06-01)]\n\nUpdated budget totals for Q4.',
                    distance=0.2,
                )
            ]

    class DummyDB:
        def attachments_for_email(self, uid):
            assert uid == "uid-att-1"
            return [
                {
                    "name": "budget.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size": 2048,
                    "content_id": "",
                    "is_inline": False,
                }
            ]

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(EmailAnswerContextInput(question="What does the budget spreadsheet say?"))
    data = json.loads(payload)

    assert data["count"] == 1
    assert data["candidates"] == []
    assert data["counts"] == {"body": 0, "attachments": 1, "total": 1}
    assert len(data["attachment_candidates"]) == 1
    candidate = data["attachment_candidates"][0]
    _assert_strong_attachment_candidate(candidate, uid="uid-att-1", filename="budget.xlsx")
    assert candidate["attachment"]["mime_type"].startswith("application/vnd.openxmlformats")
    assert candidate["provenance"]["evidence_handle"].startswith("attachment:uid-att-1:budget.xlsx:")


@pytest.mark.asyncio
async def test_email_answer_context_marks_binary_only_attachment_as_weak(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-att-weak-1",
                    chunk_id="uid-att-weak-1__att_archive__0",
                    text='[Attachment: archive.bin from email "Artifacts" (2025-06-01)]',
                    distance=0.2,
                )
            ]

    class DummyDB:
        def attachments_for_email(self, uid):
            assert uid == "uid-att-weak-1"
            return [
                {
                    "name": "archive.bin",
                    "mime_type": "application/octet-stream",
                    "size": 4096,
                    "content_id": "",
                    "is_inline": False,
                }
            ]

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(EmailAnswerContextInput(question="What is in the archive attachment?"))
    data = json.loads(payload)

    candidate = data["attachment_candidates"][0]
    assert candidate["attachment"]["filename"] == "archive.bin"
    assert candidate["attachment"]["extraction_state"] == "binary_only"
    assert candidate["attachment"]["text_available"] is False
    assert candidate["attachment"]["ocr_used"] is False
    assert candidate["attachment"]["failure_reason"] == "no_text_extracted"
    assert candidate["attachment"]["evidence_strength"] == "weak_reference"


@pytest.mark.asyncio
async def test_email_answer_context_adds_conversation_groups(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(_ConversationGroupRetriever(), _ConversationGroupDB()))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="What happened in the budget thread?", max_results=2)
    )
    data = json.loads(payload)

    assert len(data["conversation_groups"]) == 1
    group = data["conversation_groups"][0]
    assert group["conversation_id"] == "conv-1"
    assert group["top_uid"] == "uid-thread-2"
    assert group["message_count"] == 2
    assert group["participants"] == ["bob@example.com", "employee@example.test"]
    assert group["date_range"] == {"first": "2025-06-01", "last": "2025-06-02"}
    assert group["matched_uids"] == ["uid-thread-2", "uid-thread-1"]
    assert data["candidates"][0]["conversation_context"]["conversation_id"] == "conv-1"
    assert data["candidates"][0]["conversation_context"]["message_count"] == 2
    assert data["candidates"][0]["conversation_context"]["top_uid"] == "uid-thread-2"


@pytest.mark.asyncio
async def test_email_answer_context_reports_high_confidence_when_top_hit_is_clear(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-clear-1",
                    chunk_id="chunk-clear-1",
                    text="Please send the updated budget by Friday.",
                    distance=0.05,
                ),
                _make_result(
                    uid="uid-clear-2",
                    chunk_id="chunk-clear-2",
                    text="Another unrelated note.",
                    distance=0.45,
                    conversation_id="conv-2",
                    date="2025-06-03",
                ),
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-clear-1": {
                    "uid": "uid-clear-1",
                    "body_text": "Intro. Please send the updated budget by Friday. Thanks.",
                    "normalized_body_source": "body_text_html",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
                "uid-clear-2": {
                    "uid": "uid-clear-2",
                    "body_text": "Another unrelated note.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
            }

        conn = None

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    data = json.loads(
        await search_mod.email_answer_context(
            EmailAnswerContextInput(question="Who asked for the updated budget?", max_results=2)
        )
    )

    assert data["answer_quality"]["confidence_label"] == "high"
    assert data["answer_quality"]["ambiguity_reason"] == ""
    assert data["answer_quality"]["alternative_candidates"] == []
    assert data["answer_quality"]["top_candidate_uid"] == "uid-clear-1"
    assert data["answer_quality"]["top_conversation_id"] == "conv-1"


@pytest.mark.asyncio
async def test_email_answer_context_reports_ambiguity_when_top_hits_are_close(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-amb-1",
                    chunk_id="chunk-amb-1",
                    text="Budget update from Alice.",
                    distance=0.10,
                    conversation_id="conv-amb-1",
                ),
                _make_result(
                    uid="uid-amb-2",
                    chunk_id="chunk-amb-2",
                    text="Budget update from Bob.",
                    distance=0.11,
                    conversation_id="conv-amb-2",
                    date="2025-06-02",
                ),
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-amb-1": {
                    "uid": "uid-amb-1",
                    "body_text": "Budget update from Alice.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
                "uid-amb-2": {
                    "uid": "uid-amb-2",
                    "body_text": "Budget update from Bob.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
            }

        conn = None

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="Which budget update matters?", max_results=2)
    )
    data = json.loads(payload)

    assert data["answer_quality"]["confidence_label"] == "ambiguous"
    assert data["answer_quality"]["ambiguity_reason"] == "close_top_scores"
    assert data["answer_quality"]["alternative_candidates"] == ["uid-amb-2"]
    assert data["answer_quality"]["top_candidate_uid"] == "uid-amb-1"
