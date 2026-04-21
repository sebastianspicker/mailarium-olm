# ruff: noqa: F401
import json
import sqlite3

import pytest
from pydantic import ValidationError

from src.config import get_settings

from .helpers.mcp_tool_fakes import _BasicRetriever, _make_result, _patch_search_deps


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
            assert kwargs["sender"] == "employee@example.test"
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
        sender="employee@example.test",
    )
    payload = await search_mod.email_answer_context(params)
    data = json.loads(payload)

    assert data["question"] == "Who asked for the updated budget?"
    assert data["count"] == 1
    assert data["candidates"][0]["rank"] == 1
    assert data["candidates"][0]["score"] == pytest.approx(0.85)
    assert data["candidates"][0]["snippet"] == "Please send the updated budget by Friday."
    assert data["candidates"][0]["follow_up"]["tool"] == "email_deep_context"
    assert data["search"]["sender"] == "employee@example.test"
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
async def test_email_answer_context_merges_query_lanes(monkeypatch):
    import src.tools.search as search_mod
    from src.mcp_models import EmailAnswerContextInput

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            if "Protokoll" in query:
                self._last_search_debug = {
                    "executed_query": query,
                    "used_query_expansion": False,
                    "expand_query_requested": False,
                    "use_hybrid": False,
                    "use_rerank": False,
                    "top_k": top_k,
                    "fetch_size": top_k,
                    "legal_support_profile": {"is_legal_support": True, "intents": ["chronology"], "suggested_terms": []},
                }
                return [_make_result(uid="uid-wave-1", chunk_id="chunk-wave-1", text="PR-Sitzung mit Protokoll.", distance=0.1)]
            self._last_search_debug = {
                "executed_query": query,
                "used_query_expansion": False,
                "expand_query_requested": False,
                "use_hybrid": False,
                "use_rerank": False,
                "top_k": top_k,
                "fetch_size": top_k,
                "legal_support_profile": {"is_legal_support": True, "intents": ["chronology"], "suggested_terms": []},
            }
            return [
                _make_result(
                    uid="uid-wave-2",
                    chunk_id="chunk-wave-2",
                    text="Mobiles Arbeiten wurde gestrichen.",
                    distance=0.12,
                )
            ]

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {
                "uid-wave-1": {
                    "uid": "uid-wave-1",
                    "body_text": "PR-Sitzung mit Protokoll.",
                    "normalized_body_source": "body_text",
                },
                "uid-wave-2": {
                    "uid": "uid-wave-2",
                    "body_text": "Mobiles Arbeiten wurde gestrichen.",
                    "normalized_body_source": "body_text",
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
        EmailAnswerContextInput(
            question="Welche Widersprüche gibt es?",
            max_results=2,
            query_lanes=["17.12.2024 Protokoll PR-Sitzung", "mobiles Arbeiten spontanes Streichen"],
        )
    )
    data = json.loads(payload)

    assert data["count"] == 2
    assert data["search"]["retrieval_diagnostics"]["query_lane_count"] == 2
    assert len(data["search"]["retrieval_diagnostics"]["query_lanes"]) == 2


def test_search_across_query_lanes_preserves_unique_lane_hits_with_scan_state() -> None:
    from src.tools.search_answer_context_runtime import _search_across_query_lanes

    class DummyRetriever(_BasicRetriever):
        def search_filtered(self, query, top_k=10, **kwargs):
            self._last_search_debug = {
                "executed_query": query,
                "used_query_expansion": False,
            }
            if query == "lane one":
                return [
                    _make_result(uid="uid-shared", chunk_id="chunk-shared", text="shared", distance=0.05),
                    _make_result(uid="uid-lane-one", chunk_id="chunk-lane-one", text="lane one", distance=0.06),
                ]
            return [
                _make_result(uid="uid-shared", chunk_id="chunk-shared-second", text="shared", distance=0.04),
                _make_result(uid="uid-lane-two", chunk_id="chunk-lane-two", text="lane two", distance=0.07),
            ]

    retriever = DummyRetriever()
    results, diagnostics, search_meta = _search_across_query_lanes(
        retriever=retriever,
        search_kwargs={"hybrid": True},
        query_lanes=["lane one", "lane two"],
        top_k=2,
        lane_top_k=4,
        reserve_per_lane=1,
        scan_id="wave:test",
    )

    uids = [result.metadata.get("uid") for result in results]
    assert "uid-shared" in uids
    assert "uid-lane-two" in uids
    assert len(results) == 2
    assert diagnostics[0]["scan_id"] == "wave:test"
    assert diagnostics[0]["search_top_k"] == 4
    assert diagnostics[1]["excluded_count"] >= 1
    assert search_meta["candidate_pool_count"] >= 2
    assert search_meta["lane_top_k"] == 4
    assert search_meta["selected_result_count"] == 2
    assert any(item["uid"] == "uid-lane-two" for item in search_meta["evidence_bank"])


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
