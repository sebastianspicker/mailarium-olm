"""Payload-building helpers for answer-context runtime assembly."""

from __future__ import annotations

from typing import Any

from ..behavioral_taxonomy import behavioral_taxonomy_payload
from ..investigation_report import compact_investigation_report
from ..multi_source_case_bundle import compact_multi_source_case_bundle
from .search_answer_context_case_payloads import (
    _compact_actor_identity_graph_payload,
    _compact_case_bundle_payload,
    _compact_case_patterns_payload,
    _compact_comparative_treatment_payload,
    _compact_language_rhetoric_payload,
    _compact_message_findings_payload,
    _quote_attribution_metrics,
)
from .search_answer_context_evidence import (
    _compact_optional_case_surfaces,
    _compact_retaliation_analysis_payload,
    _public_retrieval_diagnostics,
)
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
    """Recompute group, quality, timeline, and answer-policy sections after compaction."""
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
        _timeline_summary(
            candidates=candidates,
            attachment_candidates=attachment_candidates,
        ),
        answer_policy,
        _final_answer_contract(answer_policy=answer_policy),
    )


def _public_item(item: dict[str, Any], state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    public = dict(item)
    for key in ("thread_group_id", "thread_group_source", "inferred_thread_id"):
        public.pop(key, None)
    if runtime.compact_case_evidence:
        if isinstance(public.get("language_rhetoric"), dict):
            public["language_rhetoric"] = _compact_language_rhetoric_payload(public.get("language_rhetoric"))
        if isinstance(public.get("message_findings"), dict):
            public["message_findings"] = _compact_message_findings_payload(public.get("message_findings"))
    if bool(runtime.packing.get("applied")):
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


def _nonempty_strings(values: Any, *, limit: int | None = None) -> list[str]:
    items = list(values or [])
    if limit is not None:
        items = items[:limit]
    return [str(item) for item in items if item]


def _compact_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision": _text(policy.get("decision")),
        "verification_mode": _text(policy.get("verification_mode")),
        "max_citations": int(policy.get("max_citations") or 0),
        "cite_candidate_uids": _nonempty_strings(policy.get("cite_candidate_uids")),
        "cite_candidate_references": _citation_reference_payloads(policy.get("cite_candidate_references")),
        "refuse_to_overclaim": bool(policy.get("refuse_to_overclaim", True)),
    }


def _compact_contract(contract: dict[str, Any]) -> dict[str, Any]:
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
    runtime = state.runtime
    if not runtime.compact_policy_contract:
        return runtime.answer_policy, runtime.final_answer_contract
    return _compact_policy(runtime.answer_policy), _compact_contract(runtime.final_answer_contract)


def _search_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    params = runtime.params
    scope = params.case_scope
    diagnostics = runtime.retrieval_diagnostics
    payload: dict[str, Any] = {"top_k": runtime.effective_top_k}
    if not runtime.compact_search:
        payload.update(
            sender=params.sender,
            subject=params.subject,
            folder=params.folder,
            has_attachments=params.has_attachments,
            email_type=params.email_type,
            rerank=params.rerank,
        )
    payload["date_from"] = params.date_from if params.date_from is not None else getattr(scope, "date_from", None)
    payload["date_to"] = params.date_to if params.date_to is not None else getattr(scope, "date_to", None)
    payload["hybrid"] = bool(diagnostics["use_hybrid"]) if "use_hybrid" in diagnostics else bool(params.hybrid or scope)
    payload["expand_query"] = (
        bool(diagnostics["expand_query_requested"]) if "expand_query_requested" in diagnostics else scope is not None
    )
    payload["retrieval_diagnostics"] = _public_retrieval_diagnostics(
        diagnostics,
        compact_search=runtime.compact_search,
    )
    return payload


def _base_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    policy, contract = _policy_payloads(state)
    total = len(runtime.candidates) + len(runtime.attachment_candidates)
    return {
        "question": runtime.params.question,
        "count": total,
        "counts": {"body": len(runtime.candidates), "attachments": len(runtime.attachment_candidates), "total": total},
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


def _compact_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": _text(finding.get("finding_id")),
        "finding_scope": _text(finding.get("finding_scope")),
        "finding_label": _text(finding.get("finding_label")),
        "supporting_uids": _nonempty_strings(finding.get("supporting_uids"), limit=3),
        "supporting_citation_ids": _nonempty_strings(finding.get("supporting_citation_ids"), limit=3),
        "evidence_strength": dict(finding.get("evidence_strength") or {}),
        "confidence_split": dict(finding.get("confidence_split") or {}),
        "alternative_explanations": _nonempty_strings(finding.get("alternative_explanations"), limit=5),
    }


def _compact_finding_index(state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    findings = [item for item in list(runtime.finding_evidence_index.get("findings") or []) if isinstance(item, dict)]
    return {
        "version": _text(runtime.finding_evidence_index.get("version")),
        "finding_count": int(runtime.finding_evidence_index.get("finding_count") or 0),
        "findings": [_compact_finding(item) for item in findings],
        "summary": {"finding_ids": [_text(item.get("finding_id")) for item in findings[:3]]},
    }


def _compact_evidence_table(state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    rows = [item for item in list(runtime.evidence_table.get("rows") or []) if isinstance(item, dict)]
    return {
        "version": _text(runtime.evidence_table.get("version")),
        "row_count": int(runtime.evidence_table.get("row_count") or 0),
        "rows": [
            {"finding_id": _text(row.get("finding_id")), "evidence_strength": _text(row.get("evidence_strength"))} for row in rows
        ],
        "summary": dict(runtime.evidence_table.get("summary") or {}),
    }


def _compact_strength_rubric(state: AnswerContextPayloadState) -> dict[str, Any]:
    rubric = state.runtime.behavioral_strength_rubric
    return {
        "version": _text(rubric.get("version")),
        "labels": list(rubric.get("labels") or []),
    }


def _compact_evidence_surfaces(state: AnswerContextPayloadState) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return _compact_finding_index(state), _compact_evidence_table(state), _compact_strength_rubric(state)


def _report_payload(state: AnswerContextPayloadState) -> dict[str, Any] | None:
    runtime = state.runtime
    report = runtime.investigation_report
    if report is not None and (runtime.compact_case_evidence or runtime.compact_report_only):
        return compact_investigation_report(report)
    return report


def _multi_source_payload(state: AnswerContextPayloadState) -> dict[str, Any] | None:
    runtime = state.runtime
    payload = runtime.multi_source_case_bundle
    if runtime.compact_case_evidence and payload is not None:
        return compact_multi_source_case_bundle(payload)
    return payload


def _actor_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    if runtime.compact_case_evidence:
        return _compact_actor_identity_graph_payload(runtime.actor_graph)
    return {
        "actors": runtime.actor_graph.get("actors", []),
        "unresolved_references": runtime.actor_graph.get("unresolved_references", []),
        "stats": runtime.actor_graph.get("stats", {}),
    }


def _case_evidence_payload(state: AnswerContextPayloadState) -> dict[str, Any]:
    runtime = state.runtime
    finding_payload, table_payload, rubric_payload = (
        _compact_evidence_surfaces(state)
        if runtime.compact_case_evidence
        else (runtime.finding_evidence_index, runtime.evidence_table, runtime.behavioral_strength_rubric)
    )
    return {
        "case_bundle": _compact_case_bundle_payload(runtime.case_bundle)
        if runtime.compact_case_evidence
        else runtime.case_bundle,
        "actor_identity_graph": _actor_payload(state),
        "power_context": runtime.power_context,
        "behavioral_taxonomy": behavioral_taxonomy_payload(
            allegation_focus=list(runtime.params.case_scope.allegation_focus) if runtime.params.case_scope is not None else []
        ),
        "case_patterns": _compact_case_patterns_payload(runtime.case_patterns)
        if runtime.compact_case_evidence
        else runtime.case_patterns,
        "retaliation_analysis": _compact_retaliation_analysis_payload(runtime.retaliation_analysis)
        if runtime.compact_case_evidence and isinstance(runtime.retaliation_analysis, dict)
        else runtime.retaliation_analysis,
        "comparative_treatment": _compact_comparative_treatment_payload(runtime.comparative_treatment)
        if runtime.compact_case_evidence
        else runtime.comparative_treatment,
        "communication_graph": runtime.communication_graph,
        "multi_source_case_bundle": _multi_source_payload(state),
        "finding_evidence_index": finding_payload,
        "evidence_table": table_payload,
        "behavioral_strength_rubric": rubric_payload,
        "quote_attribution_metrics": _quote_attribution_metrics(runtime.candidates),
        "investigation_report": _report_payload(state),
    }


def _final_budget_fields(payload: dict[str, Any], state: AnswerContextPayloadState) -> None:
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
    if state.runtime.case_bundle is not None:
        payload.update(_case_evidence_payload(state))
    _final_budget_fields(payload, state)
    return payload


__all__ = [
    "_compact_optional_case_surfaces",
    "build_payload",
    "rebuild_sections",
]
