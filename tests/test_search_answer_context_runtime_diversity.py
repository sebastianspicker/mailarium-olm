from __future__ import annotations

from src.retriever_models import SearchResult
from src.tools.search_answer_context_runtime import _search_across_query_lanes, _support_type_for_result


class _FakeRetriever:
    def __init__(self, lane_results):
        self._lane_results = lane_results
        self.email_db = None
        self.last_search_debug = {}

    def search_filtered(self, **kwargs):
        query = str(kwargs.get("query") or "")
        self.last_search_debug = {
            "executed_query": query,
            "used_query_expansion": False,
            "expand_query_requested": False,
        }
        return list(self._lane_results.get(query, []))


def test_search_across_query_lanes_reports_support_diversity_and_expansion_attribution() -> None:
    lane_results = {
        "lane body": [
            SearchResult(
                chunk_id="uid-1__0",
                text="Body evidence",
                metadata={"uid": "uid-1", "subject": "Body", "score_kind": "semantic"},
                distance=0.05,
            ),
            SearchResult(
                chunk_id="uid-2__att_0__0",
                text="Attachment evidence",
                metadata={"uid": "uid-2", "attachment_filename": "scan.pdf", "filename": "scan.pdf"},
                distance=0.06,
            ),
        ],
        "lane calendar": [
            SearchResult(
                chunk_id="uid-3__0",
                text="Calendar invite",
                metadata={"uid": "uid-3", "is_calendar_message": True, "subject": "Meeting"},
                distance=0.07,
            ),
            SearchResult(
                chunk_id="uid-4__segment_1",
                text="Segment evidence",
                metadata={"uid": "uid-4", "score_kind": "segment_sql", "segment_type": "authored_body"},
                distance=0.08,
            ),
        ],
    }
    retriever = _FakeRetriever(lane_results)

    _merged, lane_diagnostics, retrieval_context = _search_across_query_lanes(
        retriever=retriever,
        search_kwargs={"query": "base"},
        query_lanes=["lane body", "lane calendar"],
        top_k=3,
        lane_top_k=3,
        reserve_per_lane=1,
        bank_limit=6,
    )

    support_diversity = retrieval_context.get("support_diversity") or {}
    selected_support_types = set(support_diversity.get("selected_support_types") or [])
    assert "body" in selected_support_types
    assert "attachment" in selected_support_types
    assert "calendar" in selected_support_types

    expansion_attribution = retrieval_context.get("expansion_attribution") or []
    assert len(expansion_attribution) == 2
    assert int(expansion_attribution[0].get("new_key_count") or 0) >= 1
    assert int(expansion_attribution[1].get("new_key_count") or 0) >= 1
    assert isinstance(expansion_attribution[1].get("expansion_terms"), list)
    assert isinstance(expansion_attribution[1].get("recovered_expansion_terms"), list)
    assert int(expansion_attribution[1].get("recovered_expansion_key_count") or 0) >= 0
    assert int(lane_diagnostics[0].get("new_key_count") or 0) >= 1


def test_support_type_uses_content_not_only_query_lane_hints() -> None:
    result = SearchResult(
        chunk_id="uid-5__0",
        text="Neutral status update ohne inhaltliche Wertung.",
        metadata={"uid": "uid-5", "subject": "Update"},
        distance=0.05,
    )

    support_type = _support_type_for_result(result, matched_queries=["vergleich peer comparator"])

    assert support_type == "body"


def test_support_type_detects_comparator_and_counterevidence_from_content() -> None:
    comparator_result = SearchResult(
        chunk_id="uid-6__0",
        text="Vergleich mit Kollegin zeigt ungleiche Behandlung bei derselben Aufgabe.",
        metadata={"uid": "uid-6", "subject": "Vergleich"},
        distance=0.05,
    )
    counterevidence_result = SearchResult(
        chunk_id="uid-7__0",
        text="Widerspruch zur frueheren Zusage und dokumentierte Unterlassung der Antwort.",
        metadata={"uid": "uid-7", "subject": "Widerspruch"},
        distance=0.05,
    )

    assert _support_type_for_result(comparator_result, matched_queries=[]) == "comparator"
    assert _support_type_for_result(counterevidence_result, matched_queries=[]) == "counterevidence"
