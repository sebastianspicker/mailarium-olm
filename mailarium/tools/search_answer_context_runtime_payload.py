"""Payload-building helpers for generic answer-context assembly."""

from __future__ import annotations

from typing import Any

from .search_answer_context_evidence import _public_retrieval_diagnostics
from .search_answer_context_rendering import (
    _answer_policy,
    _answer_quality,
    _citation_reference_payloads,
    _final_answer_contract,
    _render_final_answer,
    _timeline_summary,
)
from .search_answer_context_runtime_state import AnswerContextPayloadState


def rebuild_sections(
    *,
    db: Any,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    params: Any,
    conversation_group_summaries: Any,
    attach_conversation_context: Any,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Recompute group, quality, timeline, and answer-policy sections."""
    groups, by_id = conversation_group_summaries(
        db,
        candidates=candidates,
        attachment_candidates=attachment_candidates,
    )
    attach_conversation_context([*candidates, *attachment_candidates], by_id)
    answer_quality = _answer_quality(
        candidates=candidates,
        attachment_candidates=attachment_candidates,
        conversation_groups=groups,
    )
    answer_policy = _answer_policy(
        question=params.question,
        evidence_mode=params.evidence_mode,
        candidates=candidates,
        attachment_candidates=attachment_candidates,
        answer_quality=answer_quality,
        exact_wording_requested=getattr(params, "exact_wording_requested", None),
    )
    return (
        groups,
        answer_quality,
        _timeline_summary(candidates=candidates, attachment_candidates=attachment_candidates),
        answer_policy,
        _final_answer_contract(answer_policy=answer_policy),
    )


def rebuild_runtime_sections(
    runtime: Any,
    *,
    conversation_group_summaries: Any,
    attach_conversation_context: Any,
) -> None:
    """Recompute and assign every derived analysis section on one runtime."""
    (
        runtime.conversation_groups,
        runtime.answer_quality,
        runtime.timeline,
        runtime.answer_policy,
        runtime.final_answer_contract,
    ) = rebuild_sections(
        db=runtime.db,
        candidates=runtime.candidates,
        attachment_candidates=runtime.attachment_candidates,
        params=runtime.params,
        conversation_group_summaries=conversation_group_summaries,
        attach_conversation_context=attach_conversation_context,
    )


def _public_item(item: dict[str, Any], state: AnswerContextPayloadState) -> dict[str, Any]:
    """Remove internal thread fields and compact provenance further when response packing was applied."""
    public = dict(item)
    for key in ("thread_group_id", "thread_group_source", "inferred_thread_id"):
        public.pop(key, None)
    if bool(state.runtime.packing.get("applied")):
        public.pop("conversation_context", None)
        public.pop("match_reason", None)
        provenance = public.get("provenance")
        if isinstance(provenance, dict):
            public["provenance"] = {
                "evidence_handle": provenance.get("evidence_handle"),
                "visible_excerpt_start": provenance.get("visible_excerpt_start"),
                "visible_excerpt_end": provenance.get("visible_excerpt_end"),
                "visible_excerpt_compacted": provenance.get("visible_excerpt_compacted"),
            }
    return public


def _text(value: Any) -> str:
    return str(value) if value else ""


def _nonempty_strings(values: Any) -> list[str]:
    """Normalize iterable values to strings while discarding empty entries."""
    return [str(item) for item in list(values or []) if item]


def _compact_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Compact policy to keep bounded tool responses useful."""
    return {
        "decision": _text(policy.get("decision")),
        "verification_mode": _text(policy.get("verification_mode")),
        "max_citations": int(policy.get("max_citations") or 0),
        "cite_candidate_uids": _nonempty_strings(policy.get("cite_candidate_uids")),
        "cite_candidate_references": _citation_reference_payloads(policy.get("cite_candidate_references")),
        "refuse_to_overclaim": bool(policy.get("refuse_to_overclaim", True)),
    }


def _compact_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Compact contract to keep bounded tool responses useful."""
    return {
        "decision": _text(contract.get("decision")),
        "answer_shape": _text((contract.get("answer_format") or {}).get("shape")),
        "citation_style": _text((contract.get("citation_format") or {}).get("style")),
        "required_citation_uids": _nonempty_strings(contract.get("required_citation_uids")),
        "required_citation_handles": _nonempty_strings(contract.get("required_citation_handles")),
        "verification_mode": _text(contract.get("verification_mode")),
        "refuse_to_overclaim": bool(contract.get("refuse_to_overclaim", True)),
    }


def _policy_payloads(state: AnswerContextPayloadState) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return full policy contracts unless response budgeting explicitly requires compact forms."""
    runtime = state.runtime
    if not runtime.compact_policy_contract:
        return runtime.answer_policy, runtime.final_answer_contract
    return _compact_policy(runtime.answer_policy), _compact_contract(runtime.final_answer_contract)


def _search_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    """Expose effective search settings and public retrieval diagnostics, including scope when present."""
    runtime = state.runtime
    params = runtime.params
    diagnostics = runtime.retrieval_diagnostics
    payload: dict[str, Any] = {
        "top_k": runtime.effective_top_k,
        "date_from": params.date_from,
        "date_to": params.date_to,
        "hybrid": bool(diagnostics.get("use_hybrid", params.hybrid)),
        "expand_query": bool(diagnostics.get("expand_query_requested", False)),
        "retrieval_diagnostics": _public_retrieval_diagnostics(
            diagnostics,
            compact_search=runtime.compact_search,
        ),
    }
    if params.scope is not None:
        payload["scope"] = params.scope
    if not runtime.compact_search:
        payload.update(
            sender=params.sender,
            subject=params.subject,
            folder=params.folder,
            has_attachments=params.has_attachments,
            email_type=params.email_type,
            rerank=params.rerank,
        )
    return payload


def _base_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    """Assemble counts, public candidates, conversation groups, timeline, policy, and answer contract."""
    runtime = state.runtime
    policy, contract = _policy_payloads(state)
    total = len(runtime.candidates) + len(runtime.attachment_candidates)
    return {
        "question": runtime.params.question,
        "count": total,
        "counts": {
            "body": len(runtime.candidates),
            "attachments": len(runtime.attachment_candidates),
            "total": total,
        },
        "candidates": [_public_item(item, state) for item in runtime.candidates],
        "attachment_candidates": [_public_item(item, state) for item in runtime.attachment_candidates],
        "conversation_groups": runtime.conversation_groups,
        "answer_quality": runtime.answer_quality,
        "timeline": runtime.timeline,
        "answer_policy": policy,
        "final_answer_contract": contract,
        "final_answer": _render_final_answer(
            candidates=runtime.candidates,
            attachment_candidates=runtime.attachment_candidates,
            answer_policy=runtime.answer_policy,
            final_answer_contract=runtime.final_answer_contract,
        ),
        "evidence_mode": {"requested": runtime.params.evidence_mode},
        "search": _search_payload(state),
    }


def _final_budget_fields(payload: dict[str, Any], state: AnswerContextPayloadState) -> None:
    """Render budget fields in the response format consumed by callers."""
    runtime = state.runtime
    if not runtime.candidates and not runtime.attachment_candidates:
        payload["message"] = "No candidate evidence found for the question."
    if runtime.effective_top_k < runtime.params.max_results:
        payload["_capped"] = {
            "requested": runtime.params.max_results,
            "effective": runtime.effective_top_k,
            "profile": runtime.settings.mcp_model_profile,
        }
    payload["_packed"] = runtime.packing


def build_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    """Build one public answer-context payload from typed runtime state."""
    payload = _base_payload(state)
    _final_budget_fields(payload, state)
    return payload


__all__ = ["build_payload", "rebuild_runtime_sections", "rebuild_sections"]
