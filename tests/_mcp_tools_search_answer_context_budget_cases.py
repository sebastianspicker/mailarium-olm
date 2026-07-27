"""Answer-context inferred grouping, evidence deduplication, and bounded packing behavior."""

import json

import pytest

from mailarium.config import get_settings

from .helpers.answer_context_fakes import _AnswerContextDeps
from .helpers.mcp_tool_extended_fakes import _inferred_thread_dependencies
from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result


class _BudgetTruncationRetriever(_BasicRetriever):
    def search_filtered(self, query, top_k=10, **kwargs):
        return [
            _make_result(
                uid="uid-pack-a",
                chunk_id="chunk-pack-a",
                text="A" * 240,
                distance=0.05,
                conversation_id="conv-pack-a",
                date="2025-06-01",
            ),
            _make_result(
                uid="uid-pack-b",
                chunk_id="chunk-pack-b",
                text="B" * 240,
                distance=0.07,
                conversation_id="conv-pack-b",
                date="2025-06-02",
            ),
            _make_result(
                uid="uid-pack-c",
                chunk_id="chunk-pack-c",
                text="C" * 240,
                distance=0.09,
                conversation_id="conv-pack-c",
                date="2025-06-03",
            ),
        ]


class _BudgetTruncationDB:
    conn = None

    def get_emails_full_batch(self, uids):
        return {
            uid: {
                "uid": uid,
                "body_text": f"{uid} " + ("X" * 320),
                "normalized_body_source": "body_text",
                "forensic_body_text": "",
                "forensic_body_source": "",
                "conversation_id": f"conv-{uid}",
            }
            for uid in uids
        }


class _BudgetStrengthRetriever(_BasicRetriever):
    def search_filtered(self, query, top_k=10, **kwargs):
        return [
            _make_result(
                uid="uid-pack-weak",
                chunk_id="chunk-pack-weak",
                text="W" * 260,
                distance=0.01,
                conversation_id="conv-pack-weak",
                date="2025-06-01",
            ),
            _make_result(
                uid="uid-pack-strong",
                chunk_id="chunk-pack-strong",
                text="S" * 260,
                distance=0.22,
                conversation_id="conv-pack-strong",
                date="2025-06-02",
            ),
        ]


class _BudgetStrengthDB:
    conn = None

    def get_emails_full_batch(self, uids):
        return {
            "uid-pack-weak": {
                "uid": "uid-pack-weak",
                "body_text": "Source-shell message with no recoverable visible body text." + (" W" * 180),
                "normalized_body_source": "source_shell_summary",
                "forensic_body_text": "",
                "forensic_body_source": "",
                "conversation_id": "conv-pack-weak",
                "body_kind": "content",
                "body_empty_reason": "source_shell_only",
                "recovery_strategy": "source_shell_summary",
                "recovery_confidence": 0.2,
            },
            "uid-pack-strong": {
                "uid": "uid-pack-strong",
                "body_text": "Please approve the updated budget before Friday." + (" S" * 180),
                "normalized_body_source": "body_text",
                "forensic_body_text": "Please approve the updated budget before Friday." + (" S" * 220),
                "forensic_body_source": "raw_body_text",
                "conversation_id": "conv-pack-strong",
            },
        }


@pytest.mark.asyncio
async def test_email_answer_context_groups_by_inferred_thread_when_canonical_missing(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    retriever, email_db = _inferred_thread_dependencies()
    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(retriever, email_db))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="What happened in the inferred thread?", max_results=2)
    )
    data = json.loads(payload)

    group = data["conversation_groups"][0]
    assert group["conversation_id"] == ""
    assert group["inferred_thread_id"] == "thread-inferred-1"
    assert group["thread_group_id"] == "thread-inferred-1"
    assert group["thread_group_source"] == "inferred"
    assert group["top_uid"] == "uid-inferred-2"
    assert group["message_count"] == 2
    assert group["participants"] == ["bob@example.com", "employee@example.test"]
    assert data["candidates"][0]["conversation_context"]["thread_group_source"] == "inferred"
    assert data["answer_quality"]["top_conversation_id"] == ""
    assert data["answer_quality"]["top_thread_group_id"] == "thread-inferred-1"
    assert data["answer_quality"]["top_thread_group_source"] == "inferred"


@pytest.mark.asyncio
async def test_email_answer_context_deduplicates_repeated_evidence(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-pack-1",
                    chunk_id="chunk-pack-1",
                    text="Please send the updated budget by Friday.",
                    distance=0.08,
                ),
                _make_result(
                    uid="uid-pack-1",
                    chunk_id="chunk-pack-1b",
                    text="Please send the updated budget by Friday.",
                    distance=0.09,
                ),
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-pack-1": {
                    "uid": "uid-pack-1",
                    "body_text": "Please send the updated budget by Friday. Thanks.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                }
            }

        conn = None

    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(DummyRetriever(), DummyDB()))
    payload = await search_mod.email_answer_context(
        EmailAnswerContextInput(question="Who asked for the updated budget?", max_results=2)
    )
    data = json.loads(payload)

    assert data["count"] == 1
    assert len(data["candidates"]) == 1
    assert data["_packed"]["applied"] is True
    assert data["_packed"]["deduplicated"]["body_candidates"] == 1
    assert data["_packed"]["truncated"]["body_candidates"] == 0


@pytest.mark.asyncio
async def test_email_answer_context_explicitly_truncates_to_budget(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "3000")
    get_settings.cache_clear()
    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(_BudgetTruncationRetriever(), _BudgetTruncationDB()))
    try:
        payload = await search_mod.email_answer_context(
            EmailAnswerContextInput(question="How did the budget discussion evolve?", max_results=3)
        )
    finally:
        get_settings.cache_clear()

    data = json.loads(payload)

    assert data["_packed"]["applied"] is True
    assert data["_packed"]["budget_chars"] == 3000
    assert data["_packed"]["truncated"]["body_candidates"] >= 1
    assert data["_packed"]["estimated_chars_after"] <= data["_packed"]["estimated_chars_before"]
    assert data["count"] < 3
    if "conversation_groups" in data:
        assert len(data["conversation_groups"]) <= 1
    if "timeline" in data:
        assert data["timeline"]["event_count"] >= 1
    assert data["final_answer"]["citations"] == [data["candidates"][0]["provenance"]["evidence_handle"]]


@pytest.mark.asyncio
async def test_email_answer_context_packing_keeps_stronger_nonweak_evidence(monkeypatch):
    import mailarium.tools.search as search_mod
    from mailarium.mcp_models import EmailAnswerContextInput

    monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "1650")
    get_settings.cache_clear()
    monkeypatch.setattr(search_mod, "_deps", _AnswerContextDeps(_BudgetStrengthRetriever(), _BudgetStrengthDB()))
    try:
        payload = await search_mod.email_answer_context(
            EmailAnswerContextInput(question="What exactly did the sender write about the budget?", max_results=2)
        )
    finally:
        get_settings.cache_clear()

    data = json.loads(payload)

    assert data["_packed"]["applied"] is True
    assert data["count"] == 1
    assert data["candidates"][0]["uid"] == "uid-pack-strong"
    assert data["answer_policy"]["verification_mode"] == "verify_forensic"
    assert data["candidates"][0]["provenance"]["visible_excerpt_compacted"] is True
    assert data["candidates"][0]["provenance"]["visible_excerpt_end"] > 0
