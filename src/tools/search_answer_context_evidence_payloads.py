"""Payload-shaping helpers for answer-context evidence output."""

from __future__ import annotations

from typing import Any

from src._utils import _as_dict, _as_list

from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_budget import _estimated_json_chars
from .search_answer_context_rendering import _resolve_exact_wording_requested


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _strings(values: Any, limit: int | None = None) -> list[str]:
    items = _as_list(values)
    if limit is not None:
        items = items[:limit]
    return [str(item) for item in items if str(item).strip()]


def _dicts(values: Any, limit: int | None = None) -> list[dict[str, Any]]:
    items = _as_list(values)
    if limit is not None:
        items = items[:limit]
    return [dict(item) for item in items if isinstance(item, dict)]


def _set_optional_filters(kwargs: dict[str, Any], params: EmailAnswerContextInput) -> None:
    for key in ("sender", "subject", "folder", "has_attachments", "email_type"):
        value = getattr(params, key)
        if value is not None:
            kwargs[key] = value


def _set_date_filters(kwargs: dict[str, Any], params: EmailAnswerContextInput) -> None:
    scope = params.case_scope
    date_from = params.date_from if params.date_from is not None else getattr(scope, "date_from", None)
    date_to = params.date_to if params.date_to is not None else getattr(scope, "date_to", None)
    if date_from is not None:
        kwargs["date_from"] = date_from
    if date_to is not None:
        kwargs["date_to"] = date_to


def _answer_context_search_kwargs(params: EmailAnswerContextInput, top_k: int) -> dict[str, Any]:
    """Build ``search_filtered`` kwargs for the answer-context tool."""
    exact = _resolve_exact_wording_requested(
        question=params.question,
        explicit=getattr(params, "exact_wording_requested", None),
    )
    kwargs: dict[str, Any] = {"query": params.question, "top_k": top_k, "_exact_wording_requested": exact}
    _set_optional_filters(kwargs, params)
    _set_date_filters(kwargs, params)
    if params.rerank:
        kwargs["rerank"] = True
    if params.hybrid or params.case_scope is not None:
        kwargs["hybrid"] = True
    if params.case_scope is not None and not exact:
        kwargs["expand_query"] = True
    return kwargs


def _compact_trigger(event: dict[str, Any]) -> dict[str, Any]:
    assessment = _as_dict(event.get("assessment"))
    return {
        "trigger_type": _text(event.get("trigger_type")),
        "date": _text(event.get("date")),
        "assessment": {
            "status": _text(assessment.get("status")),
            "analysis_quality": _text(assessment.get("analysis_quality")),
            "confounder_signals": _strings(assessment.get("confounder_signals")),
        },
    }


def _compact_retaliation_analysis_payload(retaliation_analysis: dict[str, Any]) -> dict[str, Any]:
    """Return a compact retaliation payload for tight case-evidence budgets."""
    timeline = _as_dict(retaliation_analysis.get("retaliation_timeline_assessment"))
    return {
        "version": _text(retaliation_analysis.get("version")),
        "trigger_event_count": int(retaliation_analysis.get("trigger_event_count") or 0),
        "trigger_events": [_compact_trigger(event) for event in _dicts(retaliation_analysis.get("trigger_events"), 2)],
        "retaliation_timeline_assessment": {
            "version": _text(timeline.get("version")),
            "protected_activity_timeline": _dicts(timeline.get("protected_activity_timeline"), 1),
            "temporal_correlation_analysis": _dicts(timeline.get("temporal_correlation_analysis"), 1),
            "overall_evidentiary_rating": dict(_as_dict(timeline.get("overall_evidentiary_rating"))),
        },
    }


def _lane_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "lane_id": _text(item.get("lane_id")),
        "query": _text(item.get("query")),
        "executed_query": _text(item.get("executed_query")),
        "result_count": int(item.get("result_count") or 0),
        "used_query_expansion": bool(item.get("used_query_expansion")),
        "scan_id": _text(item.get("scan_id")),
        "excluded_count": int(item.get("excluded_count") or 0),
        "search_top_k": int(item.get("search_top_k") or 0),
        "new_key_count": int(item.get("new_key_count") or 0),
        "expansion_terms": _strings(item.get("expansion_terms")),
        "recovered_expansion_terms": _strings(item.get("recovered_expansion_terms")),
        "recovered_expansion_key_count": int(item.get("recovered_expansion_key_count") or 0),
    }


def _archive_harvest_payload(context: dict[str, Any]) -> dict[str, Any]:
    coverage = _as_dict(context.get("coverage_gate"))
    expansion = _as_dict(context.get("expansion_diagnostics"))
    source_basis = _as_dict(context.get("source_basis"))
    return {
        "candidate_pool_count": int(context.get("candidate_pool_count") or 0),
        "selected_result_count": int(context.get("selected_result_count") or 0),
        "raw_candidate_count": int(context.get("raw_candidate_count") or 0),
        "compact_candidate_count": int(context.get("compact_candidate_count") or 0),
        "harvest_run_status": _text(context.get("harvest_run_status"), "completed"),
        "lane_top_k": int(context.get("lane_top_k") or 0),
        "merge_budget": int(context.get("merge_budget") or 0),
        "coverage_gate": {"status": _text(coverage.get("status")), "reasons": _strings(coverage.get("reasons"))},
        "quality_gate": dict(_as_dict(context.get("quality_gate"))),
        "actor_discovery": dict(_as_dict(context.get("actor_discovery"))),
        "expansion_diagnostics": {
            "status": _text(expansion.get("status"), "ok"),
            "error_count": int(expansion.get("error_count") or 0),
        },
        "source_basis": {"primary_source": _text(source_basis.get("primary_source"))},
        "support_diversity": dict(_as_dict(context.get("support_diversity"))),
        "expansion_attribution": _dicts(context.get("expansion_attribution")),
        "later_round_only_evidence_handles": _strings(context.get("later_round_only_evidence_handles")),
    }


def _attach_query_diagnostics(payload: dict[str, Any], context: dict[str, Any], debug: dict[str, Any]) -> None:
    original = _text(context.get("original_query") or debug.get("original_query")).strip()
    executed = _text(context.get("executed_query") or debug.get("executed_query")).strip()
    suffix = _text(debug.get("query_expansion_suffix")).strip()
    if original:
        payload["original_query"] = original
    if executed:
        payload["executed_query"] = executed
    if executed and executed != original:
        payload["query_changed"] = True
    if suffix:
        payload["query_expansion_suffix"] = suffix


def _retrieval_diagnostics(
    retriever: Any,
    *,
    candidate_count: int,
    attachment_candidate_count: int,
    lane_diagnostics: list[dict[str, Any]] | None = None,
    harvest_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return visible retrieval diagnostics for answer-context callers."""
    debug = _as_dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)))
    profile = _as_dict(debug.get("legal_support_profile"))
    payload: dict[str, Any] = {
        "used_query_expansion": bool(debug.get("used_query_expansion")),
        "expand_query_requested": bool(debug.get("expand_query_requested")),
        "use_hybrid": bool(debug.get("use_hybrid")),
        "use_rerank": bool(debug.get("use_rerank")),
        "fetch_size": int(debug.get("fetch_size") or 0),
        "legal_support_profile": {
            "is_legal_support": bool(profile.get("is_legal_support")),
            "intents": _strings(profile.get("intents")),
            "suggested_terms": _strings(profile.get("suggested_terms"), 3),
        },
        "result_mix": {
            "body_candidates": candidate_count,
            "attachment_candidates": attachment_candidate_count,
            "total_candidates": candidate_count + attachment_candidate_count,
        },
    }
    context = _as_dict(harvest_context)
    _attach_query_diagnostics(payload, context, debug)
    if lane_diagnostics:
        payload["query_lane_count"] = len(lane_diagnostics)
        payload["query_lanes"] = [_lane_diagnostic(item) for item in lane_diagnostics if isinstance(item, dict)]
    if context:
        payload["archive_harvest"] = _archive_harvest_payload(context)
    if bool(profile.get("is_legal_support")) and candidate_count + attachment_candidate_count == 0:
        payload["suspected_failure_mode"] = "retrieval_recall_gap"
        payload["review_note"] = "No evidence candidates were retrieved; review retrieval before downstream analysis."
    return payload


def _copy_if_truthy(source: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if source.get(key):
            target[key] = source[key]


def _public_archive_harvest(source: dict[str, Any]) -> dict[str, Any]:
    payload = _archive_harvest_payload(source)
    payload["coverage_gate"] = dict(_as_dict(source.get("coverage_gate")))
    payload["source_basis"] = dict(_as_dict(source.get("source_basis")))
    return payload


def _public_retrieval_diagnostics(retrieval_diagnostics: dict[str, Any], *, compact_search: bool) -> dict[str, Any]:
    """Return a budget-safe retrieval diagnostics payload for answer-context output."""
    profile = _as_dict(retrieval_diagnostics.get("legal_support_profile"))
    payload: dict[str, Any] = {
        "used_query_expansion": bool(retrieval_diagnostics.get("used_query_expansion")),
        "use_hybrid": bool(retrieval_diagnostics.get("use_hybrid")),
    }
    keys = ("query_lane_count", "query_lanes", "original_query", "executed_query", "query_expansion_suffix")
    _copy_if_truthy(retrieval_diagnostics, payload, keys)
    if not compact_search:
        _copy_if_truthy(retrieval_diagnostics, payload, ("expand_query_requested", "use_rerank", "fetch_size", "query_changed"))
    if bool(profile.get("is_legal_support")):
        public_profile = {"is_legal_support": True, "intents": _strings(profile.get("intents"))}
        if not compact_search:
            public_profile["suggested_terms"] = _strings(profile.get("suggested_terms"), 3)
        payload["legal_support_profile"] = public_profile
    failure = _text(retrieval_diagnostics.get("suspected_failure_mode"))
    if failure:
        payload["suspected_failure_mode"] = failure
        if not compact_search:
            payload["review_note"] = _text(retrieval_diagnostics.get("review_note"))
    archive = _as_dict(retrieval_diagnostics.get("archive_harvest"))
    if archive:
        payload["archive_harvest"] = _public_archive_harvest(archive)
    return payload


def _compact_optional_case_surfaces(payload: dict[str, Any], *, budget: int) -> int:
    """Drop lowest-priority case-analysis sidecars until the payload fits the budget."""
    removed = 0
    keys = (
        "investigation_report",
        "quote_attribution_metrics",
        "communication_graph",
        "retaliation_analysis",
        "comparative_treatment",
        "behavioral_strength_rubric",
        "evidence_table",
        "finding_evidence_index",
        "multi_source_case_bundle",
    )
    for key in keys:
        if _estimated_json_chars(payload) <= budget:
            break
        if key in payload:
            payload.pop(key, None)
            removed += 1
    if removed > 0:
        payload["_case_surface_compaction"] = {"status": "omitted_optional_case_surfaces", "removed_count": removed}
    return removed
