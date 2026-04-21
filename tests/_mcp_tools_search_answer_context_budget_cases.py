# ruff: noqa: F401
import json
import sqlite3

import pytest
from pydantic import ValidationError

from src.config import get_settings

from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result, _patch_search_deps


@pytest.mark.asyncio
async def test_email_answer_context_groups_by_inferred_thread_when_canonical_missing(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-inferred-2",
                    chunk_id="chunk-inferred-2",
                    text="Follow-up from the inferred-only thread.",
                    distance=0.07,
                    conversation_id="",
                    date="2025-06-05",
                ),
                _make_result(
                    uid="uid-inferred-1",
                    chunk_id="chunk-inferred-1",
                    text="Original inferred-only message.",
                    distance=0.09,
                    conversation_id="",
                    date="2025-06-04",
                ),
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-inferred-1": {
                    "uid": "uid-inferred-1",
                    "body_text": "Original inferred-only message.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                    "inferred_parent_uid": "",
                },
                "uid-inferred-2": {
                    "uid": "uid-inferred-2",
                    "body_text": "Follow-up from the inferred-only thread.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                    "inferred_parent_uid": "uid-inferred-1",
                    "inferred_match_reason": "base_subject,participants",
                    "inferred_match_confidence": 0.87,
                },
            }

        def get_inferred_thread_emails(self, inferred_thread_id):
            assert inferred_thread_id == "thread-inferred-1"
            return [
                {
                    "uid": "uid-inferred-1",
                    "subject": "Budget Review",
                    "sender_email": "employee@example.test",
                    "sender_name": "Alice",
                    "date": "2025-06-04",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                },
                {
                    "uid": "uid-inferred-2",
                    "subject": "Budget Review",
                    "sender_email": "bob@example.com",
                    "sender_name": "Bob",
                    "date": "2025-06-05",
                    "conversation_id": "",
                    "inferred_thread_id": "thread-inferred-1",
                },
            ]

        conn = None

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        @staticmethod
        def get_email_db():
            return DummyDB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

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
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        @staticmethod
        def get_email_db():
            return DummyDB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

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
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
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

    class DummyDB:
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

        conn = None

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        @staticmethod
        def get_email_db():
            return DummyDB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

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

    monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "3000")
    get_settings.cache_clear()
    monkeypatch.setattr(search_mod, "_deps", DummyDeps)
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
    import src.tools.search as search_mod
    from src.config import get_settings
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
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

    class DummyDB:
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

        conn = None

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        @staticmethod
        def get_email_db():
            return DummyDB()

        @staticmethod
        async def offload(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

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

    monkeypatch.setenv("MCP_MAX_JSON_RESPONSE_CHARS", "1650")
    get_settings.cache_clear()
    monkeypatch.setattr(search_mod, "_deps", DummyDeps)
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
