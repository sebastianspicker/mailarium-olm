import json
import sqlite3

import pytest
from pydantic import ValidationError

from src.config import get_settings


def _make_result(chunk_id="x", text="hello", distance=0.25, uid="uid-1", conversation_id="conv-1", date="2025-06-01"):
    from src.retriever import SearchResult

    return SearchResult(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "uid": uid,
            "subject": "Hi",
            "sender_email": "a@example.com",
            "conversation_id": conversation_id,
            "date": date,
        },
        distance=distance,
    )


class _BasicRetriever:
    """Minimal dummy retriever sufficient for most tool tests."""

    def search_filtered(self, query, top_k=10, **kwargs):
        return [_make_result()]

    def serialize_results(self, query, results):
        return {
            "query": query,
            "count": len(results),
            "results": [r.to_dict() for r in results],
        }

    def format_results_for_llm(self, results):
        return "formatted results"


def _patch_search_deps(monkeypatch, retriever):
    import src.tools.search as search_mod

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return retriever

        @staticmethod
        def get_email_db():
            return None

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


@pytest.mark.asyncio
async def test_email_search_structured_tool_returns_json(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    _patch_search_deps(monkeypatch, _BasicRetriever())

    params = EmailSearchStructuredInput(query="hello", top_k=5)
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert data["query"] == "hello"
    assert data["count"] == 1
    assert data["results"][0]["chunk_id"] == "x"


@pytest.mark.asyncio
async def test_email_answer_context_returns_ranked_evidence_bundle(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            assert query == "Who asked for the updated budget?"
            assert top_k == 3
            assert kwargs["sender"] == "alice@example.com"
            return [
                _make_result(
                    uid="uid-ctx-1",
                    chunk_id="chunk-1",
                    text="Please send the updated budget by Friday.",
                    distance=0.15,
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-ctx-1": {
                    "uid": "uid-ctx-1",
                    "body_text": "Intro. Please send the updated budget by Friday. Thanks.",
                    "normalized_body_source": "body_text_html",
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

    params = EmailAnswerContextInput(
        question="Who asked for the updated budget?",
        max_results=3,
        sender="alice@example.com",
    )
    payload = await search_mod.email_answer_context(params)
    data = json.loads(payload)

    assert data["question"] == "Who asked for the updated budget?"
    assert data["count"] == 1
    assert data["candidates"][0]["rank"] == 1
    assert data["candidates"][0]["score"] == pytest.approx(0.85)
    assert data["candidates"][0]["snippet"] == "Please send the updated budget by Friday."
    assert data["candidates"][0]["follow_up"]["tool"] == "email_deep_context"
    assert data["search"]["sender"] == "alice@example.com"
    assert data["candidates"][0]["body_render_mode"] == "retrieval"
    assert data["candidates"][0]["body_render_source"] == "body_text_html"
    assert data["candidates"][0]["provenance"]["uid"] == "uid-ctx-1"
    assert data["candidates"][0]["provenance"]["snippet_start"] == 7
    assert data["candidates"][0]["provenance"]["snippet_end"] == 48
    assert data["candidates"][0]["provenance"]["segment_ordinal"] is None
    assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-ctx-1:retrieval:body_text_html:7:48")


@pytest.mark.asyncio
async def test_email_answer_context_forensic_mode_uses_forensic_body(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-forensic-1",
                    chunk_id="chunk-1",
                    text="Please send the updated budget by Friday.",
                    distance=0.15,
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-forensic-1": {
                    "uid": "uid-forensic-1",
                    "body_text": "Intro. Please send the updated budget by Friday. Thanks.",
                    "normalized_body_source": "body_text_html",
                    "forensic_body_text": "Quoted header\nPlease send the updated budget by Friday.\nRegards",
                    "forensic_body_source": "raw_body_html",
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
        EmailAnswerContextInput(
            question="Who asked for the updated budget?",
            evidence_mode="forensic",
        )
    )
    data = json.loads(payload)

    assert data["evidence_mode"]["requested"] == "forensic"
    assert data["candidates"][0]["body_render_mode"] == "forensic"
    assert data["candidates"][0]["body_render_source"] == "raw_body_html"
    assert data["candidates"][0]["snippet"] == "Please send the updated budget by Friday."
    assert data["candidates"][0]["verification_status"] == "forensic_exact"
    assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-forensic-1:forensic:raw_body_html:")


@pytest.mark.asyncio
async def test_email_answer_context_hybrid_mode_falls_back_explicitly_when_forensic_missing(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [
                _make_result(
                    uid="uid-hybrid-1",
                    chunk_id="chunk-1",
                    text="Please send the updated budget by Friday.",
                    distance=0.15,
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-hybrid-1": {
                    "uid": "uid-hybrid-1",
                    "body_text": "Intro. Please send the updated budget by Friday. Thanks.",
                    "normalized_body_source": "body_text_html",
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
        EmailAnswerContextInput(
            question="Who asked for the updated budget?",
            evidence_mode="hybrid",
        )
    )
    data = json.loads(payload)

    assert data["evidence_mode"]["requested"] == "hybrid"
    assert data["candidates"][0]["body_render_mode"] == "retrieval"
    assert data["candidates"][0]["verification_status"] == "hybrid_fallback_retrieval"
    assert data["candidates"][0]["provenance"]["evidence_handle"].startswith("email:uid-hybrid-1:retrieval:body_text_html:")


@pytest.mark.asyncio
async def test_email_answer_context_handles_no_results(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return []

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        @staticmethod
        def get_email_db():
            return None

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

    params = EmailAnswerContextInput(question="Was there any update on the rack move?")
    payload = await search_mod.email_answer_context(params)
    data = json.loads(payload)

    assert data["question"] == "Was there any update on the rack move?"
    assert data["count"] == 0
    assert data["candidates"] == []
    assert data["attachment_candidates"] == []
    assert "message" in data


@pytest.mark.asyncio
async def test_email_answer_context_separates_attachment_candidates(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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
    payload = await search_mod.email_answer_context(EmailAnswerContextInput(question="What does the budget spreadsheet say?"))
    data = json.loads(payload)

    assert data["count"] == 1
    assert data["candidates"] == []
    assert data["counts"] == {"body": 0, "attachments": 1, "total": 1}
    assert len(data["attachment_candidates"]) == 1
    candidate = data["attachment_candidates"][0]
    assert candidate["uid"] == "uid-att-1"
    assert candidate["attachment"]["filename"] == "budget.xlsx"
    assert candidate["attachment"]["mime_type"].startswith("application/vnd.openxmlformats")
    assert candidate["attachment"]["size"] == 2048
    assert candidate["attachment"]["extraction_state"] == "text_extracted"
    assert candidate["attachment"]["text_available"] is True
    assert candidate["attachment"]["ocr_used"] is False
    assert candidate["attachment"]["failure_reason"] is None
    assert candidate["attachment"]["evidence_strength"] == "strong_text"
    assert candidate["attachment"]["is_inline"] is False
    assert candidate["provenance"]["evidence_handle"].startswith("attachment:uid-att-1:budget.xlsx:")


@pytest.mark.asyncio
async def test_email_answer_context_marks_binary_only_attachment_as_weak(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
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

    class DummyDB:
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
                    "sender_email": "alice@example.com",
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
        EmailAnswerContextInput(question="What happened in the budget thread?", max_results=2)
    )
    data = json.loads(payload)

    assert len(data["conversation_groups"]) == 1
    group = data["conversation_groups"][0]
    assert group["conversation_id"] == "conv-1"
    assert group["top_uid"] == "uid-thread-2"
    assert group["message_count"] == 2
    assert group["participants"] == ["alice@example.com", "bob@example.com"]
    assert group["date_range"] == {"first": "2025-06-01", "last": "2025-06-02"}
    assert group["matched_uids"] == ["uid-thread-2", "uid-thread-1"]
    assert data["candidates"][0]["conversation_context"]["conversation_id"] == "conv-1"
    assert data["candidates"][0]["conversation_context"]["message_count"] == 2
    assert data["candidates"][0]["conversation_context"]["top_uid"] == "uid-thread-2"


@pytest.mark.asyncio
async def test_email_answer_context_reports_high_confidence_when_top_hit_is_clear(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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

    assert data["answer_quality"]["confidence_label"] == "high"
    assert data["answer_quality"]["ambiguity_reason"] == ""
    assert data["answer_quality"]["alternative_candidates"] == []
    assert data["answer_quality"]["top_candidate_uid"] == "uid-clear-1"
    assert data["answer_quality"]["top_conversation_id"] == "conv-1"


@pytest.mark.asyncio
async def test_email_answer_context_reports_ambiguity_when_top_hits_are_close(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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
        EmailAnswerContextInput(question="Which budget update matters?", max_results=2)
    )
    data = json.loads(payload)

    assert data["answer_quality"]["confidence_label"] == "ambiguous"
    assert data["answer_quality"]["ambiguity_reason"] == "close_top_scores"
    assert data["answer_quality"]["alternative_candidates"] == ["uid-amb-2"]
    assert data["answer_quality"]["top_candidate_uid"] == "uid-amb-1"


@pytest.mark.asyncio
async def test_email_answer_context_adds_timeline_summary(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
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

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-time-1": {
                    "uid": "uid-time-1",
                    "body_text": "Initial request for the rollout.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
                "uid-time-2": {
                    "uid": "uid-time-2",
                    "body_text": "Decision made on the rollout.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
                "uid-time-3": {
                    "uid": "uid-time-3",
                    "body_text": "Follow-up confirmation after rollout.",
                    "normalized_body_source": "body_text",
                    "forensic_body_text": "",
                    "forensic_body_source": "",
                },
            }

        def get_thread_emails(self, conversation_id):
            assert conversation_id == "conv-time"
            return [
                {
                    "uid": "uid-time-1",
                    "subject": "Rollout",
                    "sender_email": "alice@example.com",
                    "sender_name": "Alice",
                    "date": "2025-06-01",
                    "conversation_id": "conv-time",
                },
                {
                    "uid": "uid-time-2",
                    "subject": "Rollout",
                    "sender_email": "bob@example.com",
                    "sender_name": "Bob",
                    "date": "2025-06-03",
                    "conversation_id": "conv-time",
                },
                {
                    "uid": "uid-time-3",
                    "subject": "Rollout",
                    "sender_email": "carol@example.com",
                    "sender_name": "Carol",
                    "date": "2025-06-05",
                    "conversation_id": "conv-time",
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
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
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

    class DummyDB:
        def __init__(self):
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute(
                "CREATE TABLE message_segments ("
                "email_uid TEXT, ordinal INTEGER, segment_type TEXT, depth INTEGER, "
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
                {
                    "uid": "uid-speak-1",
                    "subject": "Figures",
                    "sender_email": "alice@example.com",
                    "sender_name": "Alice",
                    "date": "2025-06-03",
                    "conversation_id": "conv-speak",
                },
                {
                    "uid": "uid-speak-0",
                    "subject": "Figures",
                    "sender_email": "bob@example.com",
                    "sender_name": "Bob",
                    "date": "2025-06-02",
                    "conversation_id": "conv-speak",
                },
            ]

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        _db = DummyDB()

        @staticmethod
        def get_email_db():
            return DummyDeps._db

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
        EmailAnswerContextInput(question="Who said what about the figures?", max_results=1)
    )
    data = json.loads(payload)

    attribution = data["candidates"][0]["speaker_attribution"]
    assert attribution["authored_speaker"]["email"] == "alice@example.com"
    assert attribution["authored_speaker"]["source"] == "canonical_sender"
    assert attribution["quoted_blocks"][0]["speaker_email"] == "bob@example.com"
    assert attribution["quoted_blocks"][0]["source"] == "reply_context_from"
    assert attribution["quoted_blocks"][0]["confidence"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_email_answer_context_adds_thread_graph(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        _db = DummyDB()

        @staticmethod
        def get_email_db():
            return DummyDeps._db

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
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        _db = DummyDB()

        @staticmethod
        def get_email_db():
            return DummyDeps._db

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
        EmailAnswerContextInput(question="Which source-shell message discussed the certificate?", max_results=1)
    )
    data = json.loads(payload)

    weak_message = data["candidates"][0]["weak_message"]
    assert weak_message["code"] == "source_shell_only"
    assert weak_message["label"] == "Source-shell message"
    assert weak_message["body_empty_reason"] == "source_shell_only"


@pytest.mark.asyncio
async def test_email_answer_context_adds_answer_policy(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

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

    class DummyDeps:
        @staticmethod
        def get_retriever():
            return DummyRetriever()

        _db = DummyDB()

        @staticmethod
        def get_email_db():
            return DummyDeps._db

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
        EmailAnswerContextInput(question="What exactly did Alice write about the budget?", max_results=1)
    )
    data = json.loads(payload)

    policy = data["answer_policy"]
    assert policy["decision"] == "answer"
    assert policy["verification_mode"] == "verify_forensic"
    assert policy["max_citations"] == 1
    assert policy["cite_candidate_uids"] == ["uid-policy-1"]
    assert policy["refuse_to_overclaim"] is True
    contract = data["final_answer_contract"]
    assert contract["decision"] == "answer"
    assert contract["answer_format"]["shape"] == "single_paragraph"
    assert contract["citation_format"]["style"] == "inline_uid_brackets"
    assert contract["required_citation_uids"] == ["uid-policy-1"]
    final_answer = data["final_answer"]
    assert final_answer["decision"] == "answer"
    assert final_answer["citations"] == ["uid-policy-1"]
    assert final_answer["verification_mode"] == "verify_forensic"
    assert "[uid:uid-policy-1]" in final_answer["text"]


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
                    "sender_email": "alice@example.com",
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
    assert group["participants"] == ["alice@example.com", "bob@example.com"]
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
    assert len(data["conversation_groups"]) >= 1
    assert len(data["conversation_groups"]) <= 1
    assert len(data["timeline"]["events"]) >= 1
    assert data["final_answer"]["citations"] == [data["candidates"][0]["uid"]]


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


@pytest.mark.asyncio
async def test_email_search_structured_forwards_new_filters(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(
        query="hello",
        top_k=5,
        subject="approval",
        folder="inbox",
        cc="finance",
        min_score=0.8,
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["subject"] == "approval"
    assert captured["folder"] == "inbox"
    assert captured["cc"] == "finance"
    assert captured["min_score"] == 0.8
    assert data["filters"]["subject"] == "approval"
    assert data["filters"]["folder"] == "inbox"
    assert data["filters"]["cc"] == "finance"
    assert data["filters"]["min_score"] == 0.8


@pytest.mark.asyncio
async def test_email_search_structured_emits_strict_json(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            return [_make_result(distance=float("nan"))]

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(query="hello", top_k=5)
    payload = await email_search_structured(params)

    assert "NaN" not in payload
    assert "Infinity" not in payload


@pytest.mark.asyncio
async def test_email_list_senders_returns_json(monkeypatch):
    from src.mcp_models import ListSendersInput
    from src.tools.search import email_list_senders

    class DummyRetriever:
        def list_senders(self, limit=30):
            return [
                {
                    "name": "Alice",
                    "email": "alice@example.com",
                    "count": 3,
                }
            ]

    _patch_search_deps(monkeypatch, DummyRetriever())
    output = await email_list_senders(ListSendersInput(limit=10))
    data = json.loads(output)

    assert data["count"] == 1
    assert data["senders"][0]["name"] == "Alice"
    assert data["senders"][0]["count"] == 3


@pytest.mark.asyncio
async def test_email_list_folders_returns_json(monkeypatch):
    from src.tools.search import email_list_folders

    class DummyRetriever:
        def list_folders(self):
            return [
                {"folder": "Inbox", "count": 42},
                {"folder": "Archive", "count": 7},
            ]

    _patch_search_deps(monkeypatch, DummyRetriever())
    output = await email_list_folders()
    data = json.loads(output)

    assert data["count"] == 2
    assert data["folders"][0]["folder"] == "Inbox"
    assert data["folders"][0]["count"] == 42
    assert data["folders"][1]["folder"] == "Archive"


@pytest.mark.asyncio
async def test_email_list_folders_empty_archive(monkeypatch):
    from src.tools.search import email_list_folders

    class DummyRetriever:
        def list_folders(self):
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())
    output = await email_list_folders()
    data = json.loads(output)

    assert data["count"] == 0
    assert data["folders"] == []


@pytest.mark.asyncio
async def test_email_ingest_returns_stats_json(monkeypatch):
    from src.mcp_models import EmailIngestInput
    from src.tools.search import email_ingest

    fake_stats = {
        "emails_parsed": 10,
        "chunks_created": 15,
        "chunks_added": 15,
        "chunks_skipped": 0,
        "batches_written": 1,
        "total_in_db": 15,
        "dry_run": False,
        "elapsed_seconds": 1.2,
    }

    monkeypatch.setattr("src.ingest.ingest", lambda **kwargs: fake_stats)

    params = EmailIngestInput(olm_path="/tmp/test.olm")
    output = await email_ingest(params)
    data = json.loads(output)

    assert data["emails_parsed"] == 10
    assert data["chunks_added"] == 15


@pytest.mark.asyncio
async def test_email_ingest_handles_file_not_found(monkeypatch):
    from src.mcp_models import EmailIngestInput
    from src.tools.search import email_ingest

    def _raise(**kwargs):
        raise FileNotFoundError("not found")

    monkeypatch.setattr("src.ingest.ingest", _raise)

    params = EmailIngestInput(olm_path="/nonexistent.olm")
    output = await email_ingest(params)
    data = json.loads(output)

    assert "error" in data


def test_structured_input_rejects_invalid_dates():
    from src.mcp_models import EmailSearchStructuredInput

    with pytest.raises(ValidationError):
        EmailSearchStructuredInput(
            query="hello",
            date_from="2024/01/01",
        )


def test_structured_input_rejects_invalid_date_order():
    from src.mcp_models import EmailSearchStructuredInput

    with pytest.raises(ValidationError):
        EmailSearchStructuredInput(
            query="hello",
            date_from="2024-05-01",
            date_to="2024-01-01",
        )


def test_structured_input_rejects_invalid_min_score():
    from src.mcp_models import EmailSearchStructuredInput

    with pytest.raises(ValidationError):
        EmailSearchStructuredInput(
            query="hello",
            min_score=1.2,
        )


@pytest.mark.asyncio
async def test_email_search_structured_forwards_email_type(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(
        query="hello",
        email_type="reply",
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["email_type"] == "reply"
    assert data["filters"]["email_type"] == "reply"


def test_structured_input_accepts_email_type():
    from src.mcp_models import EmailSearchStructuredInput

    params = EmailSearchStructuredInput(
        query="hello",
        email_type="forward",
    )
    assert params.email_type == "forward"


def test_ingest_input_accepts_extract_attachments_and_embed_images():
    from src.mcp_models import EmailIngestInput

    params = EmailIngestInput(
        olm_path="/tmp/test.olm",
        extract_attachments=True,
        embed_images=True,
    )
    assert params.extract_attachments is True
    assert params.embed_images is True


@pytest.mark.asyncio
async def test_email_diagnostics_returns_json(monkeypatch):
    from src.config import get_settings
    from src.mcp_server import _offload
    from src.tools import diagnostics

    class DummyEmbedder:
        device = "cpu"
        _model = type("Model", (), {"__name__": "StubModel"})()
        has_sparse = False
        has_colbert = False

    class DummyRetriever:
        embedder = DummyEmbedder()
        _sparse_index = None

    class MockDeps:
        get_retriever = staticmethod(lambda: DummyRetriever())
        get_email_db = staticmethod(lambda: None)
        offload = staticmethod(_offload)

    monkeypatch.setattr(diagnostics, "_deps", MockDeps)
    monkeypatch.setenv("DEVICE", "auto")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "0")
    get_settings.cache_clear()

    try:
        output = await diagnostics.email_diagnostics(MockDeps)
        data = json.loads(output)

        assert "embedding_model" in data
        assert "resolved_device" in data
        assert "resolved_batch_size" in data
        assert "batch_size_setting" in data
        assert "embedder_device" in data
        assert "embedder_batch_size" in data
        assert "embedder_backend" in data
        assert "sparse_enabled" in data
        assert "colbert_rerank_enabled" in data
        assert "sparse_vector_count" in data
        assert "sparse_index_built" in data
    finally:
        get_settings.cache_clear()


def test_all_tool_modules_importable():
    """Smoke test: every tool module under src/tools/ imports cleanly."""
    from src.tools import (
        attachments,
        browse,
        data_quality,
        diagnostics,
        entities,
        evidence,
        network,
        reporting,
        temporal,
        threads,
        topics,
    )

    for module in [
        attachments,
        browse,
        data_quality,
        diagnostics,
        entities,
        evidence,
        network,
        reporting,
        temporal,
        threads,
        topics,
    ]:
        assert callable(module.register), f"{module.__name__} missing register()"


@pytest.mark.asyncio
async def test_offload_runs_sync_in_thread():
    """_offload should run a sync function without blocking the event loop."""
    from src.mcp_server import _offload

    result = await _offload(lambda: 42)
    assert result == 42


@pytest.mark.asyncio
async def test_email_search_structured_forwards_attachment_filters(monkeypatch):
    from src.mcp_models import EmailSearchStructuredInput
    from src.tools.search import email_search_structured

    captured = {}

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, **kwargs):
            captured.update(kwargs)
            return []

    _patch_search_deps(monkeypatch, DummyRetriever())

    params = EmailSearchStructuredInput(
        query="hello",
        attachment_name="report",
        attachment_type="pdf",
    )
    payload = await email_search_structured(params)
    data = json.loads(payload)

    assert captured["attachment_name"] == "report"
    assert captured["attachment_type"] == "pdf"
    assert data["filters"]["attachment_name"] == "report"
    assert data["filters"]["attachment_type"] == "pdf"


class TestAttachmentFilters:
    def test_matches_attachment_name_in_names(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": "report.pdf, budget.xlsx"}, distance=0.1)
        assert _matches_attachment_name(r, "report") is True
        assert _matches_attachment_name(r, "slides") is False
        assert _matches_attachment_name(r, None) is True

    def test_matches_attachment_name_in_filename(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_filename": "report.pdf"}, distance=0.1)
        assert _matches_attachment_name(r, "report") is True

    def test_matches_attachment_name_list_metadata(self):
        from src.result_filters import _matches_attachment_name
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": ["report.pdf", "budget.xlsx"]}, distance=0.1)
        assert _matches_attachment_name(r, "budget") is True

    def test_matches_attachment_type(self):
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": "report.pdf, budget.xlsx"}, distance=0.1)
        assert _matches_attachment_type(r, "pdf") is True
        assert _matches_attachment_type(r, "xlsx") is True
        assert _matches_attachment_type(r, "docx") is False
        assert _matches_attachment_type(r, None) is True

    def test_matches_attachment_type_with_dot(self):
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_filename": "slides.pptx"}, distance=0.1)
        assert _matches_attachment_type(r, ".pptx") is True
        assert _matches_attachment_type(r, "pptx") is True

    def test_matches_attachment_type_no_substring_false_positive(self):
        """Filtering for .doc should NOT match .docx files."""
        from src.result_filters import _matches_attachment_type
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"attachment_names": "report.docx"}, distance=0.1)
        assert _matches_attachment_type(r, "doc") is False
        assert _matches_attachment_type(r, "docx") is True

    def test_matches_category_no_substring_false_positive(self):
        """Filtering for 'urgent' should NOT match 'Non-Urgent'."""
        from src.result_filters import _matches_category
        from src.retriever import SearchResult

        r = SearchResult(chunk_id="x", text="", metadata={"categories": "Non-Urgent, Important"}, distance=0.1)
        assert _matches_category(r, "urgent") is False
        assert _matches_category(r, "Non-Urgent") is True
        assert _matches_category(r, "Important") is True
        assert _matches_category(r, "import") is False


@pytest.mark.asyncio
async def test_offload_with_args():
    """_offload passes positional and keyword arguments through."""
    from src.mcp_server import _offload

    result = await _offload(lambda x, y=0: x + y, 10, y=5)
    assert result == 15
