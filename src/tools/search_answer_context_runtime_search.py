# mypy: disable-error-code=name-defined
# pylint: disable=too-many-arguments


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split dispatcher for search answer-context runtime (search_answer_context_runtime_search)."""

from __future__ import annotations

from typing import Any

from .search_answer_context_runtime_single_lane import _search_single_lane


def _search_across_query_lanes(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None = None,
    lane_top_k: int | None = None,
    reserve_per_lane: int = 1,
    bank_limit: int = 20,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    if not query_lanes:
        return (
            [],
            [],
            {
                "candidate_pool_count": 0,
                "selected_result_count": 0,
                "lane_top_k": 0,
                "merge_budget": bank_limit,
                "evidence_bank": [],
                "evidence_results": [],
            },
        )
    lane_search_top_k = max(top_k, int(lane_top_k or top_k))
    if len(query_lanes) == 1:
        return _search_single_lane(
            retriever=retriever,
            search_kwargs=search_kwargs,
            query_lanes=query_lanes,
            top_k=top_k,
            scan_id=scan_id,
            lane_search_top_k=lane_search_top_k,
            bank_limit=bank_limit,
        )
    from .search_answer_context_runtime_multi_lane import _search_multi_lane

    return _search_multi_lane(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query_lanes=query_lanes,
        top_k=top_k,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
        reserve_per_lane=reserve_per_lane,
    )


__all__ = [
    "_search_across_query_lanes",
]
