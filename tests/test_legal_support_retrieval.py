from __future__ import annotations

import json

import pytest

from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput, EmailAnswerContextInput
from src.query_expander import legal_support_query_profile
from src.retriever import SearchResult
from src.retriever_hybrid import _legal_support_result_boost, merge_hybrid_impl
from src.tools.search_answer_context import _answer_context_search_kwargs


def test_answer_context_search_kwargs_enable_hybrid_and_query_expansion_for_case_scope() -> None:
    params = EmailAnswerContextInput(
        question="What contradictions appear after the complaint?",
        max_results=5,
        case_scope=BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.org"),
            allegation_focus=["retaliation"],
            analysis_goal="lawyer_briefing",
            date_from="2026-02-01",
            date_to="2026-02-28",
        ),
    )

    kwargs = _answer_context_search_kwargs(params, 5)

    assert kwargs["hybrid"] is True
    assert kwargs["expand_query"] is True
    assert kwargs["date_from"] == "2026-02-01"
    assert kwargs["date_to"] == "2026-02-28"


def test_answer_context_search_kwargs_disable_auto_expansion_for_exact_wording_case_scope() -> None:
    params = EmailAnswerContextInput(
        question="What did they say exactly about the complaint?",
        max_results=5,
        case_scope=BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.org"),
            allegation_focus=["retaliation"],
            analysis_goal="lawyer_briefing",
            date_from="2026-02-01",
            date_to="2026-02-28",
        ),
    )

    kwargs = _answer_context_search_kwargs(params, 5)

    assert kwargs["hybrid"] is True
    assert "expand_query" not in kwargs
    assert kwargs["date_from"] == "2026-02-01"
    assert kwargs["date_to"] == "2026-02-28"


def test_answer_context_search_kwargs_disable_auto_expansion_for_german_exact_wording() -> None:
    params = EmailAnswerContextInput(
        question="Was war der genaue Wortlaut der Nachricht?",
        max_results=5,
        case_scope=BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.org"),
            allegation_focus=["retaliation"],
            analysis_goal="lawyer_briefing",
            date_from="2026-02-01",
            date_to="2026-02-28",
        ),
    )

    kwargs = _answer_context_search_kwargs(params, 5)

    assert kwargs["hybrid"] is True
    assert "expand_query" not in kwargs


def test_answer_context_search_kwargs_keep_expansion_for_explicit_case_lanes() -> None:
    params = EmailAnswerContextInput(
        question="Which records support the retaliation timeline?",
        max_results=5,
        query_lanes=["retaliation timeline", "meeting note chronology"],
        case_scope=BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example", email="alex@example.org"),
            allegation_focus=["retaliation"],
            analysis_goal="lawyer_briefing",
            date_from="2026-02-01",
            date_to="2026-02-28",
        ),
    )

    kwargs = _answer_context_search_kwargs(params, 5)

    assert kwargs["hybrid"] is True
    assert kwargs["expand_query"] is True


def test_legal_support_result_boost_prefers_participation_records() -> None:
    participation_result = SearchResult(
        chunk_id="participation",
        text="SBV participation record and consultation note",
        metadata={"attachment_filename": "sbv_record.pdf"},
        distance=0.4,
    )
    neutral_result = SearchResult(
        chunk_id="neutral",
        text="General scheduling note",
        metadata={},
        distance=0.1,
    )

    participation_boost = _legal_support_result_boost("Need SBV participation timeline", participation_result)
    neutral_boost = _legal_support_result_boost("Need SBV participation timeline", neutral_result)

    assert participation_boost > neutral_boost


def test_merge_hybrid_boosts_participation_result_to_front() -> None:
    class FakeCollection:
        def get(self, ids, include):
            return {"ids": [], "documents": [], "metadatas": []}

    class FakeRetriever:
        collection = FakeCollection()

        @staticmethod
        def _get_sparse_results(query, top_k):
            return ["neutral", "participation"]

        @staticmethod
        def _get_bm25_results(query, top_k):
            return None

    semantic_results = [
        SearchResult(chunk_id="neutral", text="General scheduling note", metadata={}, distance=0.1),
        SearchResult(
            chunk_id="participation",
            text="SBV participation record and consultation note",
            metadata={"attachment_filename": "sbv_record.pdf"},
            distance=0.3,
        ),
    ]

    merged = merge_hybrid_impl(FakeRetriever(), "Need SBV participation timeline", semantic_results, 5)

    assert merged[0].chunk_id == "participation"


def test_legal_support_result_boost_does_not_treat_generic_summary_language_as_contradiction() -> None:
    generic_summary = SearchResult(
        chunk_id="generic-summary",
        text="Status summary agreed by everyone.",
        metadata={},
        distance=0.4,
    )

    assert _legal_support_result_boost("What contradiction appears after the complaint?", generic_summary) == 0


def test_legal_support_query_profile_expands_german_workplace_terms() -> None:
    profile = legal_support_query_profile(
        "Vergleichsperson Ungleichbehandlung BEM Maßregelung fehlender Nachweis Gedächtnisprotokoll"
    )

    assert profile["is_legal_support"] is True
    assert "chronology" in profile["intents"]
    assert "comparator" in profile["intents"]
    assert "participation" in profile["intents"]
    assert "document_request" in profile["intents"]
    assert "retaliation" in profile["intents"]
    assert "zeitlinie" in profile["suggested_terms"]
    assert "sbv" in profile["suggested_terms"]
    assert "vergleichsgruppe" in profile["suggested_terms"]
    assert "massregelung" in profile["suggested_terms"]


@pytest.mark.asyncio
async def test_email_answer_context_exposes_retrieval_diagnostics_for_legal_support_queries(monkeypatch):
    import src.tools.search as search_mod

    class DummyRetriever:
        def __init__(self) -> None:
            self._last_search_debug = {}

        def search_filtered(self, **kwargs):
            self._last_search_debug = {
                "original_query": kwargs["query"],
                "executed_query": kwargs["query"] + " contradiction timeline sbv",
                "used_query_expansion": True,
                "expand_query_requested": kwargs.get("expand_query", False),
                "use_hybrid": kwargs.get("hybrid", False),
                "use_rerank": kwargs.get("rerank", False),
                "fetch_size": 40,
                "legal_support_profile": {
                    "is_legal_support": True,
                    "intents": ["chronology", "contradiction", "participation"],
                    "suggested_terms": ["timeline", "sbv", "contradiction"],
                },
            }
            return []

    class DummyDB:
        def get_emails_full_batch(self, uids):
            return {}

    class DummyDeps:
        DB_UNAVAILABLE = json.dumps({"error": "SQLite database not available."})

        _retriever = DummyRetriever()

        @classmethod
        def get_retriever(cls):
            return cls._retriever

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
            question="What participation contradiction appears after the complaint?",
            max_results=3,
            case_scope=BehavioralCaseScopeInput(
                target_person=CasePartyInput(name="Alex Example", email="alex@example.org"),
                allegation_focus=["retaliation"],
                analysis_goal="lawyer_briefing",
                date_from="2026-02-01",
                date_to="2026-02-28",
            ),
        )
    )
    data = json.loads(payload)
    diagnostics = data["search"]["retrieval_diagnostics"]

    assert data["search"]["hybrid"] is True
    assert data["search"]["expand_query"] is True
    assert diagnostics["used_query_expansion"] is True
    assert diagnostics["original_query"] == "What participation contradiction appears after the complaint?"
    assert diagnostics["executed_query"].endswith("contradiction timeline sbv")
    assert diagnostics["legal_support_profile"]["is_legal_support"] is True
    assert diagnostics["suspected_failure_mode"] == "retrieval_recall_gap"
