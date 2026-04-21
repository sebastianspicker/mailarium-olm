"""Payload-shaping helpers for answer-context evidence output."""

from __future__ import annotations

from typing import Any

from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_budget import _estimated_json_chars
from .search_answer_context_evidence_helpers import _as_dict, _as_list
from .search_answer_context_rendering import _resolve_exact_wording_requested


def _answer_context_search_kwargs(params: EmailAnswerContextInput, top_k: int) -> dict[str, Any]:
    """Build ``search_filtered`` kwargs for the answer-context tool."""
    exact_wording = _resolve_exact_wording_requested(
        question=params.question,
        explicit=getattr(params, "exact_wording_requested", None),
    )
    auto_case_scope_recall = params.case_scope is not None and not exact_wording
    kwargs: dict[str, Any] = {
        "query": params.question,
        "top_k": top_k,
        "_exact_wording_requested": exact_wording,
    }
    if params.sender is not None:
        kwargs["sender"] = params.sender
    if params.subject is not None:
        kwargs["subject"] = params.subject
    if params.folder is not None:
        kwargs["folder"] = params.folder
    if params.has_attachments is not None:
        kwargs["has_attachments"] = params.has_attachments
    if params.email_type is not None:
        kwargs["email_type"] = params.email_type
    if params.date_from is not None:
        kwargs["date_from"] = params.date_from
    elif params.case_scope is not None and params.case_scope.date_from is not None:
        kwargs["date_from"] = params.case_scope.date_from
    if params.date_to is not None:
        kwargs["date_to"] = params.date_to
    elif params.case_scope is not None and params.case_scope.date_to is not None:
        kwargs["date_to"] = params.case_scope.date_to
    if params.rerank:
        kwargs["rerank"] = True
    if params.hybrid or params.case_scope is not None:
        kwargs["hybrid"] = True
    if auto_case_scope_recall:
        kwargs["expand_query"] = True
    return kwargs


def _compact_retaliation_analysis_payload(retaliation_analysis: dict[str, Any]) -> dict[str, Any]:
    """Return a compact retaliation payload for tight case-evidence budgets."""
    timeline_assessment = (
        (retaliation_analysis.get("retaliation_timeline_assessment") or {}) if isinstance(retaliation_analysis, dict) else {}
    )
    return {
        "version": str(retaliation_analysis.get("version") or ""),
        "trigger_event_count": int(retaliation_analysis.get("trigger_event_count") or 0),
        "trigger_events": [
            {
                "trigger_type": str(event.get("trigger_type") or ""),
                "date": str(event.get("date") or ""),
                "assessment": {
                    "status": str(_as_dict(event.get("assessment")).get("status") or ""),
                    "analysis_quality": str(_as_dict(event.get("assessment")).get("analysis_quality") or ""),
                    "confounder_signals": [
                        str(item) for item in _as_list(_as_dict(event.get("assessment")).get("confounder_signals")) if item
                    ],
                },
            }
            for event in _as_list(retaliation_analysis.get("trigger_events"))[:2]
            if isinstance(event, dict)
        ],
        "retaliation_timeline_assessment": {
            "version": str(_as_dict(timeline_assessment).get("version") or ""),
            "protected_activity_timeline": [
                dict(entry)
                for entry in _as_list(_as_dict(timeline_assessment).get("protected_activity_timeline"))[:1]
                if isinstance(entry, dict)
            ],
            "temporal_correlation_analysis": [
                dict(entry)
                for entry in _as_list(_as_dict(timeline_assessment).get("temporal_correlation_analysis"))[:1]
                if isinstance(entry, dict)
            ],
            "overall_evidentiary_rating": dict(_as_dict(timeline_assessment).get("overall_evidentiary_rating") or {}),
        },
    }


def _retrieval_diagnostics(
    retriever: Any,
    *,
    candidate_count: int,
    attachment_candidate_count: int,
    lane_diagnostics: list[dict[str, Any]] | None = None,
    harvest_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return visible retrieval diagnostics for answer-context and case-analysis callers."""
    debug = _as_dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)))
    profile = _as_dict(debug.get("legal_support_profile"))
    intents = [str(item) for item in _as_list(profile.get("intents")) if str(item).strip()]
    suggested_terms = [str(item) for item in _as_list(profile.get("suggested_terms")) if str(item).strip()][:3]
    diagnostics = {
        "used_query_expansion": bool(debug.get("used_query_expansion")),
        "expand_query_requested": bool(debug.get("expand_query_requested")),
        "use_hybrid": bool(debug.get("use_hybrid")),
        "use_rerank": bool(debug.get("use_rerank")),
        "fetch_size": int(debug.get("fetch_size") or 0),
        "legal_support_profile": {
            "is_legal_support": bool(profile.get("is_legal_support")),
            "intents": intents,
            "suggested_terms": suggested_terms,
        },
        "result_mix": {
            "body_candidates": candidate_count,
            "attachment_candidates": attachment_candidate_count,
            "total_candidates": candidate_count + attachment_candidate_count,
        },
    }
    harvest_context = _as_dict(harvest_context)
    executed_query = str(harvest_context.get("executed_query") or debug.get("executed_query") or "").strip()
    original_query = str(harvest_context.get("original_query") or debug.get("original_query") or "").strip()
    query_expansion_suffix = str(debug.get("query_expansion_suffix") or "").strip()
    if original_query:
        diagnostics["original_query"] = original_query
    if executed_query:
        diagnostics["executed_query"] = executed_query
    if executed_query and executed_query != original_query:
        diagnostics["query_changed"] = True
    if query_expansion_suffix:
        diagnostics["query_expansion_suffix"] = query_expansion_suffix
    if lane_diagnostics:
        diagnostics["query_lane_count"] = len(lane_diagnostics)
        diagnostics["query_lanes"] = [
            {
                "lane_id": str(item.get("lane_id") or ""),
                "query": str(item.get("query") or ""),
                "executed_query": str(item.get("executed_query") or ""),
                "result_count": int(item.get("result_count") or 0),
                "used_query_expansion": bool(item.get("used_query_expansion")),
                "scan_id": str(item.get("scan_id") or ""),
                "excluded_count": int(item.get("excluded_count") or 0),
                "search_top_k": int(item.get("search_top_k") or 0),
                "new_key_count": int(item.get("new_key_count") or 0),
                "expansion_terms": [str(term) for term in _as_list(item.get("expansion_terms")) if str(term).strip()],
                "recovered_expansion_terms": [
                    str(term) for term in _as_list(item.get("recovered_expansion_terms")) if str(term).strip()
                ],
                "recovered_expansion_key_count": int(item.get("recovered_expansion_key_count") or 0),
            }
            for item in lane_diagnostics
            if isinstance(item, dict)
        ]
    if harvest_context:
        coverage_gate = _as_dict(harvest_context.get("coverage_gate"))
        source_basis = _as_dict(harvest_context.get("source_basis"))
        diagnostics["archive_harvest"] = {
            "candidate_pool_count": int(harvest_context.get("candidate_pool_count") or 0),
            "selected_result_count": int(harvest_context.get("selected_result_count") or 0),
            "raw_candidate_count": int(harvest_context.get("raw_candidate_count") or 0),
            "compact_candidate_count": int(harvest_context.get("compact_candidate_count") or 0),
            "harvest_run_status": str(harvest_context.get("harvest_run_status") or "completed"),
            "lane_top_k": int(harvest_context.get("lane_top_k") or 0),
            "merge_budget": int(harvest_context.get("merge_budget") or 0),
            "coverage_gate": {
                "status": str(coverage_gate.get("status") or ""),
                "reasons": [str(item) for item in _as_list(coverage_gate.get("reasons")) if str(item).strip()],
            },
            "quality_gate": dict(_as_dict(harvest_context.get("quality_gate"))),
            "actor_discovery": dict(_as_dict(harvest_context.get("actor_discovery"))),
            "expansion_diagnostics": {
                "status": str(_as_dict(harvest_context.get("expansion_diagnostics")).get("status") or "ok"),
                "error_count": int(_as_dict(harvest_context.get("expansion_diagnostics")).get("error_count") or 0),
            },
            "source_basis": {
                "primary_source": str(source_basis.get("primary_source") or ""),
            },
            "support_diversity": dict(_as_dict(harvest_context.get("support_diversity"))),
            "expansion_attribution": [
                dict(item) for item in _as_list(harvest_context.get("expansion_attribution")) if isinstance(item, dict)
            ],
            "later_round_only_evidence_handles": [
                str(item) for item in _as_list(harvest_context.get("later_round_only_evidence_handles")) if str(item).strip()
            ],
        }
    legal_support_profile = _as_dict(diagnostics.get("legal_support_profile"))
    result_mix = _as_dict(diagnostics.get("result_mix"))
    if bool(legal_support_profile.get("is_legal_support")) and int(result_mix.get("total_candidates") or 0) == 0:
        diagnostics["suspected_failure_mode"] = "retrieval_recall_gap"
        diagnostics["review_note"] = "No evidence candidates were retrieved; review retrieval before downstream analysis."
    return diagnostics


def _public_retrieval_diagnostics(
    retrieval_diagnostics: dict[str, Any],
    *,
    compact_search: bool,
) -> dict[str, Any]:
    """Return a budget-safe retrieval diagnostics payload for answer-context output."""
    profile = _as_dict(retrieval_diagnostics.get("legal_support_profile"))
    payload: dict[str, Any] = {
        "used_query_expansion": bool(retrieval_diagnostics.get("used_query_expansion")),
        "use_hybrid": bool(retrieval_diagnostics.get("use_hybrid")),
    }
    original_query = str(retrieval_diagnostics.get("original_query") or "").strip()
    executed_query = str(retrieval_diagnostics.get("executed_query") or "").strip()
    query_expansion_suffix = str(retrieval_diagnostics.get("query_expansion_suffix") or "").strip()
    if compact_search:
        if retrieval_diagnostics.get("query_lane_count"):
            payload["query_lane_count"] = int(retrieval_diagnostics.get("query_lane_count") or 0)
        if retrieval_diagnostics.get("query_lanes"):
            payload["query_lanes"] = [
                dict(item) for item in _as_list(retrieval_diagnostics.get("query_lanes")) if isinstance(item, dict)
            ]
        if original_query:
            payload["original_query"] = original_query
        if executed_query:
            payload["executed_query"] = executed_query
        if query_expansion_suffix:
            payload["query_expansion_suffix"] = query_expansion_suffix
        if bool(profile.get("is_legal_support")):
            payload["legal_support_profile"] = {
                "is_legal_support": True,
                "intents": [str(item) for item in _as_list(profile.get("intents")) if str(item).strip()],
            }
        suspected_failure_mode = str(retrieval_diagnostics.get("suspected_failure_mode") or "")
        if suspected_failure_mode:
            payload["suspected_failure_mode"] = suspected_failure_mode
        archive_harvest = _as_dict(retrieval_diagnostics.get("archive_harvest"))
        if archive_harvest:
            payload["archive_harvest"] = {
                "candidate_pool_count": int(archive_harvest.get("candidate_pool_count") or 0),
                "selected_result_count": int(archive_harvest.get("selected_result_count") or 0),
                "raw_candidate_count": int(archive_harvest.get("raw_candidate_count") or 0),
                "compact_candidate_count": int(archive_harvest.get("compact_candidate_count") or 0),
                "harvest_run_status": str(archive_harvest.get("harvest_run_status") or "completed"),
                "lane_top_k": int(archive_harvest.get("lane_top_k") or 0),
                "merge_budget": int(archive_harvest.get("merge_budget") or 0),
                "coverage_gate": dict(_as_dict(archive_harvest.get("coverage_gate"))),
                "quality_gate": dict(_as_dict(archive_harvest.get("quality_gate"))),
                "actor_discovery": dict(_as_dict(archive_harvest.get("actor_discovery"))),
                "expansion_diagnostics": {
                    "status": str(_as_dict(archive_harvest.get("expansion_diagnostics")).get("status") or "ok"),
                    "error_count": int(_as_dict(archive_harvest.get("expansion_diagnostics")).get("error_count") or 0),
                },
                "source_basis": dict(_as_dict(archive_harvest.get("source_basis"))),
                "support_diversity": dict(_as_dict(archive_harvest.get("support_diversity"))),
                "expansion_attribution": [
                    dict(item) for item in _as_list(archive_harvest.get("expansion_attribution")) if isinstance(item, dict)
                ],
                "later_round_only_evidence_handles": [
                    str(item) for item in _as_list(archive_harvest.get("later_round_only_evidence_handles")) if str(item).strip()
                ],
            }
        return payload

    if retrieval_diagnostics.get("expand_query_requested"):
        payload["expand_query_requested"] = True
    if retrieval_diagnostics.get("use_rerank"):
        payload["use_rerank"] = True
    if retrieval_diagnostics.get("fetch_size"):
        payload["fetch_size"] = int(retrieval_diagnostics.get("fetch_size") or 0)
    if retrieval_diagnostics.get("query_changed"):
        payload["query_changed"] = True
    if retrieval_diagnostics.get("query_lane_count"):
        payload["query_lane_count"] = int(retrieval_diagnostics.get("query_lane_count") or 0)
    if retrieval_diagnostics.get("query_lanes"):
        payload["query_lanes"] = [
            dict(item) for item in _as_list(retrieval_diagnostics.get("query_lanes")) if isinstance(item, dict)
        ]
    if original_query:
        payload["original_query"] = original_query
    if executed_query:
        payload["executed_query"] = executed_query
    if query_expansion_suffix:
        payload["query_expansion_suffix"] = query_expansion_suffix

    is_legal_support = bool(profile.get("is_legal_support"))
    if is_legal_support:
        payload["legal_support_profile"] = {
            "is_legal_support": True,
            "intents": [str(item) for item in _as_list(profile.get("intents")) if str(item).strip()],
            "suggested_terms": [str(item) for item in _as_list(profile.get("suggested_terms")) if str(item).strip()][:3],
        }
    suspected_failure_mode = str(retrieval_diagnostics.get("suspected_failure_mode") or "")
    if suspected_failure_mode:
        payload["suspected_failure_mode"] = suspected_failure_mode
        payload["review_note"] = str(retrieval_diagnostics.get("review_note") or "")
    archive_harvest = _as_dict(retrieval_diagnostics.get("archive_harvest"))
    if archive_harvest:
        payload["archive_harvest"] = {
            "candidate_pool_count": int(archive_harvest.get("candidate_pool_count") or 0),
            "selected_result_count": int(archive_harvest.get("selected_result_count") or 0),
            "raw_candidate_count": int(archive_harvest.get("raw_candidate_count") or 0),
            "compact_candidate_count": int(archive_harvest.get("compact_candidate_count") or 0),
            "harvest_run_status": str(archive_harvest.get("harvest_run_status") or "completed"),
            "lane_top_k": int(archive_harvest.get("lane_top_k") or 0),
            "merge_budget": int(archive_harvest.get("merge_budget") or 0),
            "coverage_gate": dict(_as_dict(archive_harvest.get("coverage_gate"))),
            "quality_gate": dict(_as_dict(archive_harvest.get("quality_gate"))),
            "actor_discovery": dict(_as_dict(archive_harvest.get("actor_discovery"))),
            "expansion_diagnostics": {
                "status": str(_as_dict(archive_harvest.get("expansion_diagnostics")).get("status") or "ok"),
                "error_count": int(_as_dict(archive_harvest.get("expansion_diagnostics")).get("error_count") or 0),
            },
            "source_basis": dict(_as_dict(archive_harvest.get("source_basis"))),
            "support_diversity": dict(_as_dict(archive_harvest.get("support_diversity"))),
            "expansion_attribution": [
                dict(item) for item in _as_list(archive_harvest.get("expansion_attribution")) if isinstance(item, dict)
            ],
            "later_round_only_evidence_handles": [
                str(item) for item in _as_list(archive_harvest.get("later_round_only_evidence_handles")) if str(item).strip()
            ],
        }
    return payload


def _compact_optional_case_surfaces(payload: dict[str, Any], *, budget: int) -> int:
    """Drop lowest-priority case-analysis sidecars until the payload fits the budget."""
    removed = 0
    for key in (
        "investigation_report",
        "quote_attribution_metrics",
        "communication_graph",
        "retaliation_analysis",
        "comparative_treatment",
        "behavioral_strength_rubric",
        "evidence_table",
        "finding_evidence_index",
        "multi_source_case_bundle",
    ):
        if _estimated_json_chars(payload) <= budget:
            break
        if key in payload:
            payload.pop(key, None)
            removed += 1
    if removed > 0:
        payload["_case_surface_compaction"] = {
            "status": "omitted_optional_case_surfaces",
            "removed_count": removed,
        }
    return removed
