# mypy: disable-error-code=name-defined
# pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments


# pylint: disable=E0602  # cross-module names injected by compatibility facade
"""Split helpers for single-lane search answer-context runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# isort: off
from ..scan_session import filter_seen
from .search_answer_context_runtime_lanes import _segment_search_results
from .search_answer_context_runtime_ranking import (
    _bank_entry,
    _evidence_bank_keys_with_lane_diversity,
    _evidence_bank_keys_with_support_diversity,
    _lane_expansion_terms,
    _lane_recovered_expansion_terms,
    _result_competition_key,
    _result_identity_key,
    _support_type_for_result,
)
# isort: on


@dataclass(slots=True)
class LaneDiagnosticsInput:
    lane_id: str
    query: str
    executed_query: str
    results: list[Any]
    scan_id: str | None
    scan_meta: dict[str, Any] | None
    lane_search_top_k: int
    expansion_terms: list[str]
    debug: dict[str, Any]
    segment_diag: dict[str, Any]


@dataclass(slots=True)
class SingleLanePayloadInput:
    ranked_results: list[tuple[str, Any]]
    combined_results: dict[str, Any]
    lane_queries_by_key: dict[str, list[str]]
    bank_keys: list[str]
    query: str
    expansion_terms: list[str]
    recovered_terms: list[str]
    recovered_key_count: int
    bank_limit: int
    lane_search_top_k: int
    top_k: int


def _apply_filter_seen(scan_id: str | None, results: list[Any]) -> tuple[list[Any], dict[str, Any] | None]:
    if scan_id:
        return filter_seen(scan_id, results)
    return results, None


def _build_lane_diagnostics_item(context: LaneDiagnosticsInput) -> dict[str, Any]:
    item: dict[str, Any] = {
        "lane_id": context.lane_id,
        "query": context.query,
        "executed_query": context.executed_query,
        "result_count": len(context.results),
        "used_query_expansion": bool(context.debug.get("used_query_expansion")),
        "scan_id": context.scan_id or "",
        "excluded_count": int((context.scan_meta or {}).get("excluded_count") or 0),
        "search_top_k": context.lane_search_top_k,
        "expansion_terms": context.expansion_terms,
    }
    item.update(context.segment_diag)
    return item


def _build_evidence_bank(
    bank_keys: list[str],
    combined: dict[str, Any],
    lane_hits: dict[str, list[str]],
    lane_queries_by_key: dict[str, list[str]],
    *,
    is_single_lane: bool = False,
    single_query: str = "",
) -> list[dict[str, Any]]:
    evidence_bank = []
    for key in bank_keys:
        result = combined[key]
        matched_lanes = ["lane_1"] if is_single_lane else lane_hits.get(key, [])
        matched_queries = lane_queries_by_key.get(key, [single_query]) if is_single_lane else lane_queries_by_key.get(key, [])
        evidence_bank.append(
            _bank_entry(
                result=result,
                key=key,
                matched_query_lanes=matched_lanes,
                matched_query_queries=matched_queries,
            )
        )
    return evidence_bank


def _compute_support_type_counts(
    bank_keys: list[str],
    combined: dict[str, Any],
    lane_queries_by_key: dict[str, list[str]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in bank_keys:
        support_type = _support_type_for_result(combined[key], matched_queries=lane_queries_by_key.get(key, []))
        counts[support_type] = int(counts.get(support_type, 0)) + 1
    return counts


def _single_lane_search_kwargs(search_kwargs: dict[str, Any], *, query: str, lane_search_top_k: int) -> dict[str, Any]:
    return {
        key: value
        for key, value in {**search_kwargs, "query": query, "top_k": lane_search_top_k}.items()
        if not str(key).startswith("_")
    }


def _merge_single_lane_results(results: list[Any], *, exact_wording: bool) -> dict[str, Any]:
    combined_results: dict[str, Any] = {}
    for result in results:
        key = _result_identity_key(result, fallback="lane_1")
        existing = combined_results.get(key)
        if existing is None or _result_competition_key(result, exact_wording=exact_wording) > _result_competition_key(
            existing,
            exact_wording=exact_wording,
        ):
            combined_results[key] = result
    return combined_results


def _annotate_single_lane_results(ranked_results: list[tuple[str, Any]], *, query: str) -> dict[str, list[str]]:
    for _key, result in ranked_results:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        metadata["matched_query_lanes"] = ["lane_1"]
        metadata["matched_query_queries"] = [query]
    return {key: [query] for key, _result in ranked_results}


def _single_lane_bank_keys(
    *,
    ranked_results: list[tuple[str, Any]],
    lane_queries_by_key: dict[str, list[str]],
    bank_limit: int,
) -> list[str]:
    bank_keys = _evidence_bank_keys_with_lane_diversity(
        ranked=ranked_results,
        lane_hits={key: ["lane_1"] for key, _result in ranked_results},
        bank_limit=bank_limit,
        reserve_per_lane=1,
    )
    return _evidence_bank_keys_with_support_diversity(
        ranked=ranked_results,
        selected_keys=bank_keys,
        lane_queries_by_key=lane_queries_by_key,
        bank_limit=bank_limit,
    )


def _single_lane_payload(context: SingleLanePayloadInput) -> dict[str, Any]:
    support_type_counts = _compute_support_type_counts(
        bank_keys=context.bank_keys,
        combined=context.combined_results,
        lane_queries_by_key=context.lane_queries_by_key,
    )
    evidence_bank = _build_evidence_bank(
        bank_keys=context.bank_keys,
        combined=context.combined_results,
        lane_hits={},
        lane_queries_by_key=context.lane_queries_by_key,
        is_single_lane=True,
        single_query=context.query,
    )
    return {
        "candidate_pool_count": len(context.ranked_results),
        "selected_result_count": min(len(context.ranked_results), context.top_k),
        "lane_top_k": context.lane_search_top_k,
        "merge_budget": context.bank_limit,
        "support_diversity": {
            "selected_support_types": sorted(support_type_counts.keys()),
            "counts_by_support_type": support_type_counts,
        },
        "expansion_attribution": [
            {
                "lane_id": "lane_1",
                "query": context.query,
                "new_key_count": len(context.ranked_results),
                "expansion_terms": context.expansion_terms,
                "recovered_expansion_terms": context.recovered_terms,
                "recovered_expansion_key_count": context.recovered_key_count,
            }
        ],
        "evidence_bank": evidence_bank[: context.bank_limit],
        "evidence_results": [result for _key, result in context.ranked_results[: context.bank_limit]],
    }


def _single_lane_runtime_context(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query: str,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    results = retriever.search_filtered(
        **_single_lane_search_kwargs(search_kwargs, query=query, lane_search_top_k=lane_search_top_k)
    )
    results, scan_meta = _apply_filter_seen(scan_id, results)
    debug = dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)) or {})
    executed_query = str(debug.get("executed_query") or query)
    expansion_terms = _lane_expansion_terms(
        base_query=query,
        lane_query=query,
        executed_query=executed_query,
        query_expansion_suffix=str(debug.get("query_expansion_suffix") or ""),
    )
    segment_results, segment_diag = _segment_search_results(
        retriever=retriever,
        lane_query=query,
        lane_id="lane_1",
        limit=max(4, min(bank_limit, lane_search_top_k // 2 or 4)),
        scan_id=scan_id,
    )
    lane_diagnostics = [
        _build_lane_diagnostics_item(
            LaneDiagnosticsInput(
                lane_id="lane_1",
                query=query,
                executed_query=executed_query,
                results=results,
                scan_id=scan_id,
                scan_meta=scan_meta,
                lane_search_top_k=lane_search_top_k,
                expansion_terms=expansion_terms,
                debug=debug,
                segment_diag=segment_diag,
            )
        )
    ]
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    combined_results = _merge_single_lane_results([*results, *segment_results], exact_wording=exact_wording)
    return combined_results, lane_diagnostics, expansion_terms


def _search_single_lane(
    *,
    retriever: Any,
    search_kwargs: dict[str, Any],
    query_lanes: list[str],
    top_k: int,
    scan_id: str | None,
    lane_search_top_k: int,
    bank_limit: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    query = query_lanes[0]
    combined_results, lane_diagnostics, expansion_terms = _single_lane_runtime_context(
        retriever=retriever,
        search_kwargs=search_kwargs,
        query=query,
        scan_id=scan_id,
        lane_search_top_k=lane_search_top_k,
        bank_limit=bank_limit,
    )
    return _assemble_single_lane_results(
        combined_results=combined_results,
        exact_wording=exact_wording,
        lane_diagnostics=lane_diagnostics,
        expansion_terms=expansion_terms,
        query_lanes=query_lanes,
        top_k=top_k,
        bank_limit=bank_limit,
        lane_search_top_k=lane_search_top_k,
    )


def _assemble_single_lane_results(
    *,
    combined_results: dict[str, Any],
    exact_wording: bool,
    lane_diagnostics: list[dict[str, Any]],
    expansion_terms: list[str],
    query_lanes: list[str],
    top_k: int,
    bank_limit: int,
    lane_search_top_k: int,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any]]:
    ranked_results = sorted(
        combined_results.items(),
        key=lambda item: _result_competition_key(item[1], exact_wording=exact_wording),
        reverse=True,
    )
    lane_diagnostics[0]["new_key_count"] = len(ranked_results)
    recovered_terms, recovered_key_count = _lane_recovered_expansion_terms(
        expansion_terms=expansion_terms,
        new_keys=[key for key, _result in ranked_results],
        result_lookup=combined_results,
    )
    lane_diagnostics[0]["recovered_expansion_terms"] = recovered_terms
    lane_diagnostics[0]["recovered_expansion_key_count"] = recovered_key_count
    query = query_lanes[0]
    lane_queries_by_key = _annotate_single_lane_results(ranked_results, query=query)
    bank_keys = _single_lane_bank_keys(
        ranked_results=ranked_results,
        lane_queries_by_key=lane_queries_by_key,
        bank_limit=bank_limit,
    )
    return (
        [result for _key, result in ranked_results[:top_k]],
        lane_diagnostics,
        _single_lane_payload(
            SingleLanePayloadInput(
                ranked_results=ranked_results,
                combined_results=combined_results,
                lane_queries_by_key=lane_queries_by_key,
                bank_keys=bank_keys,
                query=query,
                expansion_terms=expansion_terms,
                recovered_terms=recovered_terms,
                recovered_key_count=recovered_key_count,
                bank_limit=bank_limit,
                lane_search_top_k=lane_search_top_k,
                top_k=top_k,
            )
        ),
    )


__all__ = [
    "LaneDiagnosticsInput",
    "SingleLanePayloadInput",
    "_apply_filter_seen",
    "_assemble_single_lane_results",
    "_build_evidence_bank",
    "_build_lane_diagnostics_item",
    "_compute_support_type_counts",
    "_search_single_lane",
    "_single_lane_runtime_context",
]
