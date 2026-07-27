"""Payload-shaping helpers for answer-context evidence output."""

from __future__ import annotations

from typing import Any

from mailarium._utils import _as_dict, _as_list

from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_rendering import _resolve_exact_wording_requested


def _text(value: Any, default: str = "") -> str:
    return str(value) if value else default


def _strings(values: Any, limit: int | None = None) -> list[str]:
    items = _as_list(values)
    if limit is not None:
        items = items[:limit]
    return [str(item) for item in items if str(item).strip()]


def _set_optional_filters(kwargs: dict[str, Any], params: EmailAnswerContextInput) -> None:
    """Copy explicitly supplied mailbox filters into retriever keyword arguments."""
    for key in ("sender", "subject", "folder", "has_attachments", "email_type"):
        value = getattr(params, key)
        if value is not None:
            kwargs[key] = value


def _set_date_filters(kwargs: dict[str, Any], params: EmailAnswerContextInput) -> None:
    """Copy inclusive date bounds only when the caller supplied them."""
    if params.date_from is not None:
        kwargs["date_from"] = params.date_from
    if params.date_to is not None:
        kwargs["date_to"] = params.date_to


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
    if params.hybrid:
        kwargs["hybrid"] = True
    if params.scope is not None:
        kwargs["scope"] = params.scope
    return kwargs


def _lane_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    """Project internal lane execution data onto the stable public diagnostics schema."""
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


def _attach_query_diagnostics(payload: dict[str, Any], context: dict[str, Any], debug: dict[str, Any]) -> None:
    """Apply query diagnostics while retaining source diagnostics."""
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
    retrieval_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return visible retrieval diagnostics for answer-context callers."""
    debug = _as_dict(getattr(retriever, "last_search_debug", getattr(retriever, "_last_search_debug", None)))
    policy = _as_dict(debug.get("retrieval_policy"))
    fusion = _as_dict(debug.get("fusion"))
    payload: dict[str, Any] = {
        "used_query_expansion": bool(debug.get("used_query_expansion")),
        "expand_query_requested": bool(debug.get("expand_query_requested")),
        "use_hybrid": bool(debug.get("use_hybrid")),
        "use_rerank": bool(debug.get("use_rerank")),
        "fetch_size": int(debug.get("fetch_size") or 0),
        "result_mix": {
            "body_candidates": candidate_count,
            "attachment_candidates": attachment_candidate_count,
            "total_candidates": candidate_count + attachment_candidate_count,
        },
    }
    if policy:
        payload["retrieval_policy"] = policy
    if fusion:
        payload["fusion"] = fusion
    context = _as_dict(retrieval_context)
    _attach_query_diagnostics(payload, context, debug)
    if lane_diagnostics:
        payload["query_lane_count"] = len(lane_diagnostics)
        payload["query_lanes"] = [_lane_diagnostic(item) for item in lane_diagnostics if isinstance(item, dict)]
    return payload


def _copy_if_truthy(source: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...]) -> None:
    """Copy selected diagnostic fields only when their values carry useful information."""
    for key in keys:
        if source.get(key):
            target[key] = source[key]


def _public_retrieval_diagnostics(retrieval_diagnostics: dict[str, Any], *, compact_search: bool) -> dict[str, Any]:
    """Return a budget-safe retrieval diagnostics payload for answer-context output."""
    payload: dict[str, Any] = {
        "used_query_expansion": bool(retrieval_diagnostics.get("used_query_expansion")),
        "use_hybrid": bool(retrieval_diagnostics.get("use_hybrid")),
    }
    policy = _as_dict(retrieval_diagnostics.get("retrieval_policy"))
    if policy:
        payload["retrieval_policy"] = policy
    fusion = _as_dict(retrieval_diagnostics.get("fusion"))
    if fusion and not compact_search:
        payload["fusion"] = fusion
    keys = ("query_lane_count", "query_lanes", "original_query", "executed_query", "query_expansion_suffix")
    _copy_if_truthy(retrieval_diagnostics, payload, keys)
    if not compact_search:
        _copy_if_truthy(retrieval_diagnostics, payload, ("expand_query_requested", "use_rerank", "fetch_size", "query_changed"))
    failure = _text(retrieval_diagnostics.get("suspected_failure_mode"))
    if failure:
        payload["suspected_failure_mode"] = failure
        if not compact_search:
            payload["review_note"] = _text(retrieval_diagnostics.get("review_note"))
    return payload
