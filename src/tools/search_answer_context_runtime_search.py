# mypy: disable-error-code=name-defined
"""Split helpers for search answer-context runtime (search_answer_context_runtime_search)."""

from __future__ import annotations

import re
from typing import Any

from ..actor_resolution import resolve_actor_graph
from ..behavioral_evidence_chains import build_behavioral_evidence_chains
from ..behavioral_strength import apply_behavioral_strength
from ..case_intake import build_case_bundle
from ..communication_graph import build_communication_graph
from ..comparative_treatment import build_comparative_treatment
from ..cross_message_patterns import build_case_patterns
from ..formatting import weak_message_semantics
from ..investigation_report import build_investigation_report
from ..mcp_models import EmailAnswerContextInput
from ..multi_source_case_bundle import build_multi_source_case_bundle
from ..power_context import apply_power_context_to_actor_graph, build_power_context
from ..trigger_retaliation import build_retaliation_analysis
from . import search_answer_context_impl as impl
from .search_answer_context_budget import (
    _compact_snippets_for_budget,
    _compact_timeline_events,
    _dedupe_evidence_items,
    _estimated_json_chars,
    _reindex_evidence,
    _strip_optional_evidence_fields,
    _summarize_conversation_groups_for_budget,
    _summarize_timeline_for_budget,
    _weakest_evidence_target,
)
from .search_answer_context_case_payloads import _apply_actor_ids_to_candidates, _apply_actor_ids_to_case_bundle
from .search_answer_context_rendering import (
    _answer_policy,
    _answer_quality,
    _final_answer_contract,
    _render_final_answer,
    _resolve_exact_wording_requested,
)
from .search_answer_context_runtime_payload import _compact_optional_case_surfaces, build_payload, rebuild_sections
from .utils import ToolDepsProto, json_response

# ruff: noqa: F401,F821


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
    lane_diagnostics: list[dict[str, Any]] = []
    exact_wording = bool(search_kwargs.get("_exact_wording_requested"))
    if not query_lanes:
        return (
            [],
            lane_diagnostics,
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
    base_lane_query = str(query_lanes[0] or "")
    if len(query_lanes) == 1:
        results = retriever.search_filtered(
            **{
                key: value
                for key, value in {**search_kwargs, "query": query_lanes[0], "top_k": lane_search_top_k}.items()
                if not str(key).startswith("_")
            }
        )
        scan_meta: dict[str, Any] | None = None
        if scan_id:
            from ..scan_session import filter_seen

            results, scan_meta = filter_seen(scan_id, results)
        debug = dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)) or {})
        executed_query = str(debug.get("executed_query") or query_lanes[0])
        expansion_terms = _lane_expansion_terms(
            base_query=query_lanes[0],
            lane_query=query_lanes[0],
            executed_query=executed_query,
            query_expansion_suffix=str(debug.get("query_expansion_suffix") or ""),
        )
        lane_diagnostics.append(
            {
                "lane_id": "lane_1",
                "query": query_lanes[0],
                "executed_query": executed_query,
                "result_count": len(results),
                "used_query_expansion": bool(debug.get("used_query_expansion")),
                "scan_id": scan_id or "",
                "excluded_count": int((scan_meta or {}).get("excluded_count") or 0),
                "search_top_k": lane_search_top_k,
                "expansion_terms": expansion_terms,
            }
        )
        segment_results, segment_diag = _segment_search_results(
            retriever=retriever,
            lane_query=query_lanes[0],
            lane_id="lane_1",
            limit=max(4, min(bank_limit, lane_search_top_k // 2 or 4)),
            scan_id=scan_id,
        )
        lane_diagnostics[0].update(segment_diag)
        combined_results: dict[str, Any] = {}
        for result in [*results, *segment_results]:
            key = _result_identity_key(result, fallback="lane_1")
            existing = combined_results.get(key)
            if existing is None or _result_competition_key(result, exact_wording=exact_wording) > _result_competition_key(
                existing,
                exact_wording=exact_wording,
            ):
                combined_results[key] = result
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
        for _key, result in ranked_results:
            metadata = result.metadata if isinstance(result.metadata, dict) else {}
            metadata["matched_query_lanes"] = ["lane_1"]
            metadata["matched_query_queries"] = [query_lanes[0]]
        lane_queries_by_key = {key: [query_lanes[0]] for key, _result in ranked_results}
        bank_keys = _evidence_bank_keys_with_lane_diversity(
            ranked=ranked_results,
            lane_hits={key: ["lane_1"] for key, _result in ranked_results},
            bank_limit=bank_limit,
            reserve_per_lane=1,
        )
        bank_keys = _evidence_bank_keys_with_support_diversity(
            ranked=ranked_results,
            selected_keys=bank_keys,
            lane_queries_by_key=lane_queries_by_key,
            bank_limit=bank_limit,
        )
        evidence_bank = []
        for key in bank_keys:
            result = combined_results[key]
            evidence_bank.append(
                _bank_entry(
                    result=result,
                    key=key,
                    matched_query_lanes=["lane_1"],
                    matched_query_queries=lane_queries_by_key.get(key, [query_lanes[0]]),
                )
            )
        support_type_counts: dict[str, int] = {}
        for key in bank_keys:
            support_type = _support_type_for_result(combined_results[key], matched_queries=lane_queries_by_key.get(key, []))
            support_type_counts[support_type] = int(support_type_counts.get(support_type, 0)) + 1
        return (
            [result for _key, result in ranked_results[:top_k]],
            lane_diagnostics,
            {
                "candidate_pool_count": len(ranked_results),
                "selected_result_count": min(len(ranked_results), top_k),
                "lane_top_k": lane_search_top_k,
                "merge_budget": bank_limit,
                "support_diversity": {
                    "selected_support_types": sorted(support_type_counts.keys()),
                    "counts_by_support_type": support_type_counts,
                },
                "expansion_attribution": [
                    {
                        "lane_id": "lane_1",
                        "query": query_lanes[0],
                        "new_key_count": len(ranked_results),
                        "expansion_terms": expansion_terms,
                        "recovered_expansion_terms": recovered_terms,
                        "recovered_expansion_key_count": recovered_key_count,
                    }
                ],
                "evidence_bank": evidence_bank[:bank_limit],
                "evidence_results": [result for _key, result in ranked_results[:bank_limit]],
            },
        )

    combined: dict[str, Any] = {}
    lane_hits: dict[str, list[str]] = {}
    lane_queries_by_key = {}
    reserved_keys: list[str] = []
    for index, lane_query in enumerate(query_lanes, start=1):
        lane_id = f"lane_{index}"
        lane_initial_keys = set(combined.keys())
        lane_kwargs = {
            key: value
            for key, value in {**search_kwargs, "query": lane_query, "top_k": lane_search_top_k}.items()
            if not str(key).startswith("_")
        }
        lane_results = retriever.search_filtered(**lane_kwargs)
        raw_lane_results = lane_results if isinstance(lane_results, list) else []
        for result in raw_lane_results:
            key = _result_identity_key(result, fallback=lane_id)
            _record_lane_match(
                key=key,
                lane_id=lane_id,
                lane_query=lane_query,
                lane_hits=lane_hits,
                lane_queries_by_key=lane_queries_by_key,
            )
        lane_scan_meta: dict[str, Any] | None = None
        if scan_id:
            from ..scan_session import filter_seen

            lane_results, lane_scan_meta = filter_seen(scan_id, lane_results)
        debug = dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)) or {})
        executed_query = str(debug.get("executed_query") or lane_query)
        expansion_terms = _lane_expansion_terms(
            base_query=base_lane_query,
            lane_query=lane_query,
            executed_query=executed_query,
            query_expansion_suffix=str(debug.get("query_expansion_suffix") or ""),
        )
        lane_diagnostics.append(
            {
                "lane_id": lane_id,
                "query": lane_query,
                "executed_query": executed_query,
                "result_count": len(lane_results),
                "used_query_expansion": bool(debug.get("used_query_expansion")),
                "scan_id": scan_id or "",
                "excluded_count": int((lane_scan_meta or {}).get("excluded_count") or 0),
                "search_top_k": lane_search_top_k,
                "expansion_terms": expansion_terms,
            }
        )
        segment_results, segment_diag = _segment_search_results(
            retriever=retriever,
            lane_query=lane_query,
            lane_id=lane_id,
            limit=max(4, min(bank_limit, lane_search_top_k // 2 or 4)),
            scan_id=scan_id,
        )
        lane_diagnostics[-1].update(segment_diag)
        lane_reserved_keys: list[str] = []
        for result in lane_results:
            key = _result_identity_key(result, fallback=lane_id)
            existing = combined.get(key)
            if existing is None or _result_competition_key(result, exact_wording=exact_wording) > _result_competition_key(
                existing,
                exact_wording=exact_wording,
            ):
                combined[key] = result
            if key not in lane_reserved_keys:
                lane_reserved_keys.append(key)
        for result in segment_results:
            key = _result_identity_key(result, fallback=lane_id)
            _record_lane_match(
                key=key,
                lane_id=lane_id,
                lane_query=lane_query,
                lane_hits=lane_hits,
                lane_queries_by_key=lane_queries_by_key,
            )
            existing = combined.get(key)
            if existing is None or _result_competition_key(result, exact_wording=exact_wording) > _result_competition_key(
                existing,
                exact_wording=exact_wording,
            ):
                combined[key] = result
            if key not in lane_reserved_keys:
                lane_reserved_keys.append(key)
        for key in lane_reserved_keys[: max(reserve_per_lane, 0)]:
            if key not in reserved_keys:
                reserved_keys.append(key)
        lane_new_keys = [key for key in combined if key not in lane_initial_keys]
        lane_diagnostics[-1]["new_key_count"] = len(lane_new_keys)
        recovered_terms, recovered_key_count = _lane_recovered_expansion_terms(
            expansion_terms=expansion_terms,
            new_keys=lane_new_keys,
            result_lookup=combined,
        )
        lane_diagnostics[-1]["recovered_expansion_terms"] = recovered_terms
        lane_diagnostics[-1]["recovered_expansion_key_count"] = recovered_key_count
    ranked = sorted(
        combined.items(), key=lambda item: _result_competition_key(item[1], exact_wording=exact_wording), reverse=True
    )
    merged_keys: list[str] = []
    for key in reserved_keys:
        if key in combined and key not in merged_keys:
            merged_keys.append(key)
        if len(merged_keys) >= top_k:
            break
    for key, _result in ranked:
        if key in merged_keys:
            continue
        merged_keys.append(key)
        if len(merged_keys) >= top_k:
            break
    merged = [combined[key] for key in merged_keys[:top_k]]
    for result in merged:
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        key = _result_identity_key(result, fallback="")
        metadata["matched_query_lanes"] = lane_hits.get(key, [])
        metadata["matched_query_queries"] = lane_queries_by_key.get(key, [])
    bank_keys = _evidence_bank_keys_with_lane_diversity(
        ranked=ranked,
        lane_hits=lane_hits,
        bank_limit=bank_limit,
        reserve_per_lane=reserve_per_lane,
    )
    bank_keys = _evidence_bank_keys_with_support_diversity(
        ranked=ranked,
        selected_keys=bank_keys,
        lane_queries_by_key=lane_queries_by_key,
        bank_limit=bank_limit,
    )
    evidence_bank = [
        _bank_entry(
            result=combined[key],
            key=key,
            matched_query_lanes=lane_hits.get(key, []),
            matched_query_queries=lane_queries_by_key.get(key, []),
        )
        for key in bank_keys
    ]
    support_type_counts = {}
    for key in bank_keys:
        support_type = _support_type_for_result(combined[key], matched_queries=lane_queries_by_key.get(key, []))
        support_type_counts[support_type] = int(support_type_counts.get(support_type, 0)) + 1
    return (
        merged,
        lane_diagnostics,
        {
            "candidate_pool_count": len(ranked),
            "selected_result_count": len(merged),
            "lane_top_k": lane_search_top_k,
            "merge_budget": bank_limit,
            "reserved_per_lane": reserve_per_lane,
            "reserved_key_count": len(reserved_keys),
            "support_diversity": {
                "selected_support_types": sorted(support_type_counts.keys()),
                "counts_by_support_type": support_type_counts,
            },
            "expansion_attribution": [
                {
                    "lane_id": str(item.get("lane_id") or ""),
                    "query": str(item.get("query") or ""),
                    "new_key_count": int(item.get("new_key_count") or 0),
                    "expansion_terms": [str(term) for term in item.get("expansion_terms", []) if str(term).strip()],
                    "recovered_expansion_terms": [
                        str(term) for term in item.get("recovered_expansion_terms", []) if str(term).strip()
                    ],
                    "recovered_expansion_key_count": int(item.get("recovered_expansion_key_count") or 0),
                }
                for item in lane_diagnostics
                if isinstance(item, dict)
            ],
            "evidence_bank": evidence_bank,
            "evidence_results": [combined[key] for key in bank_keys],
        },
    )


__all__ = [
    "_search_across_query_lanes",
]
