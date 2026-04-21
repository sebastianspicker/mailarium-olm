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
    _timeline_summary,
)


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


def build_payload(
    *,
    params: Any,
    effective_top_k: int,
    settings: Any,
    retrieval_diagnostics: dict[str, Any],
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    answer_quality: dict[str, Any],
    timeline: dict[str, Any],
    answer_policy: dict[str, Any],
    final_answer_contract: dict[str, Any],
    final_answer: dict[str, Any],
    case_bundle: dict[str, Any] | None,
    actor_graph: dict[str, Any],
    power_context: dict[str, Any] | None,
    case_patterns: dict[str, Any] | None,
    retaliation_analysis: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    communication_graph: dict[str, Any] | None,
    multi_source_case_bundle: dict[str, Any] | None,
    finding_evidence_index: dict[str, Any],
    evidence_table: dict[str, Any],
    behavioral_strength_rubric: dict[str, Any],
    investigation_report: dict[str, Any] | None,
    compact_policy_contract: bool = False,
    compact_search: bool = False,
    compact_report_only: bool = False,
    compact_case_evidence: bool = False,
    packing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one public answer-context payload."""
    scope = params.case_scope
    scope_date_from = scope.date_from if scope is not None else None
    scope_date_to = scope.date_to if scope is not None else None

    def _public_item(item: dict[str, Any]) -> dict[str, Any]:
        public = dict(item)
        public.pop("thread_group_id", None)
        public.pop("thread_group_source", None)
        public.pop("inferred_thread_id", None)
        if compact_case_evidence:
            if isinstance(public.get("language_rhetoric"), dict):
                public["language_rhetoric"] = _compact_language_rhetoric_payload(public.get("language_rhetoric"))
            if isinstance(public.get("message_findings"), dict):
                public["message_findings"] = _compact_message_findings_payload(public.get("message_findings"))
        if packing is not None and bool(packing.get("applied")):
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

    if compact_policy_contract:
        answer_policy_payload = {
            "decision": str(answer_policy.get("decision") or ""),
            "verification_mode": str(answer_policy.get("verification_mode") or ""),
            "max_citations": int(answer_policy.get("max_citations") or 0),
            "cite_candidate_uids": [str(uid) for uid in answer_policy.get("cite_candidate_uids", []) if uid],
            "cite_candidate_references": _citation_reference_payloads(answer_policy.get("cite_candidate_references")),
            "refuse_to_overclaim": bool(answer_policy.get("refuse_to_overclaim", True)),
        }
        final_answer_contract_payload = {
            "decision": str(final_answer_contract.get("decision") or ""),
            "answer_shape": str((final_answer_contract.get("answer_format") or {}).get("shape") or ""),
            "citation_style": str((final_answer_contract.get("citation_format") or {}).get("style") or ""),
            "required_citation_uids": [str(uid) for uid in final_answer_contract.get("required_citation_uids", []) if uid],
            "required_citation_handles": [
                str(handle) for handle in final_answer_contract.get("required_citation_handles", []) if handle
            ],
            "verification_mode": str(final_answer_contract.get("verification_mode") or ""),
            "refuse_to_overclaim": bool(final_answer_contract.get("refuse_to_overclaim", True)),
        }
    else:
        answer_policy_payload = answer_policy
        final_answer_contract_payload = final_answer_contract

    if compact_search:
        search_payload: dict[str, Any] = {
            "top_k": effective_top_k,
            "date_from": params.date_from if params.date_from is not None else scope_date_from,
            "date_to": params.date_to if params.date_to is not None else scope_date_to,
            "hybrid": (
                bool(retrieval_diagnostics.get("use_hybrid"))
                if "use_hybrid" in retrieval_diagnostics
                else (params.hybrid or scope is not None)
            ),
            "expand_query": (
                bool(retrieval_diagnostics.get("expand_query_requested"))
                if "expand_query_requested" in retrieval_diagnostics
                else scope is not None
            ),
            "retrieval_diagnostics": _public_retrieval_diagnostics(
                retrieval_diagnostics,
                compact_search=True,
            ),
        }
    else:
        search_payload = {
            "top_k": effective_top_k,
            "sender": params.sender,
            "subject": params.subject,
            "folder": params.folder,
            "has_attachments": params.has_attachments,
            "email_type": params.email_type,
            "date_from": params.date_from if params.date_from is not None else scope_date_from,
            "date_to": params.date_to if params.date_to is not None else scope_date_to,
            "rerank": params.rerank,
            "hybrid": (
                bool(retrieval_diagnostics.get("use_hybrid"))
                if "use_hybrid" in retrieval_diagnostics
                else (params.hybrid or scope is not None)
            ),
            "expand_query": (
                bool(retrieval_diagnostics.get("expand_query_requested"))
                if "expand_query_requested" in retrieval_diagnostics
                else scope is not None
            ),
            "retrieval_diagnostics": _public_retrieval_diagnostics(
                retrieval_diagnostics,
                compact_search=False,
            ),
        }

    payload: dict[str, Any] = {
        "question": params.question,
        "count": len(candidates) + len(attachment_candidates),
        "counts": {
            "body": len(candidates),
            "attachments": len(attachment_candidates),
            "total": len(candidates) + len(attachment_candidates),
        },
        "candidates": [_public_item(candidate) for candidate in candidates],
        "attachment_candidates": [_public_item(candidate) for candidate in attachment_candidates],
        "conversation_groups": groups,
        "answer_quality": answer_quality,
        "timeline": timeline,
        "answer_policy": answer_policy_payload,
        "final_answer_contract": final_answer_contract_payload,
        "final_answer": final_answer,
        "evidence_mode": {
            "requested": params.evidence_mode,
        },
        "search": search_payload,
    }
    if case_bundle is not None:
        payload["case_bundle"] = _compact_case_bundle_payload(case_bundle) if compact_case_evidence else case_bundle
        if compact_case_evidence:
            finding_evidence_payload = {
                "version": str(finding_evidence_index.get("version") or ""),
                "finding_count": int(finding_evidence_index.get("finding_count") or 0),
                "findings": [
                    {
                        "finding_id": str(finding.get("finding_id") or ""),
                        "finding_scope": str(finding.get("finding_scope") or ""),
                        "finding_label": str(finding.get("finding_label") or ""),
                        "supporting_uids": [str(uid) for uid in list(finding.get("supporting_uids") or [])[:3] if uid],
                        "supporting_citation_ids": [
                            str(uid) for uid in list(finding.get("supporting_citation_ids") or [])[:3] if uid
                        ],
                        "evidence_strength": dict(finding.get("evidence_strength") or {}),
                        "confidence_split": dict(finding.get("confidence_split") or {}),
                        "alternative_explanations": [
                            str(item) for item in list(finding.get("alternative_explanations") or [])[:5] if item
                        ],
                    }
                    for finding in list(finding_evidence_index.get("findings") or [])
                    if isinstance(finding, dict)
                ],
                "summary": {
                    "finding_ids": [
                        str(finding.get("finding_id") or "")
                        for finding in list(finding_evidence_index.get("findings") or [])[:3]
                        if isinstance(finding, dict)
                    ],
                },
            }
            evidence_table_payload = {
                "version": str(evidence_table.get("version") or ""),
                "row_count": int(evidence_table.get("row_count") or 0),
                "rows": [
                    {
                        "finding_id": str(row.get("finding_id") or ""),
                        "evidence_strength": str(row.get("evidence_strength") or ""),
                    }
                    for row in list(evidence_table.get("rows") or [])
                    if isinstance(row, dict)
                ],
                "summary": dict(evidence_table.get("summary") or {}),
            }
            strength_rubric_payload = {
                "version": str(behavioral_strength_rubric.get("version") or ""),
                "labels": list(behavioral_strength_rubric.get("labels") or []),
            }
        else:
            finding_evidence_payload = finding_evidence_index
            evidence_table_payload = evidence_table
            strength_rubric_payload = behavioral_strength_rubric
        investigation_report_payload = investigation_report
        if (compact_case_evidence or compact_report_only) and investigation_report is not None:
            investigation_report_payload = compact_investigation_report(investigation_report)
        multi_source_payload = multi_source_case_bundle
        if compact_case_evidence and multi_source_case_bundle is not None:
            multi_source_payload = compact_multi_source_case_bundle(multi_source_case_bundle)
        payload["actor_identity_graph"] = (
            _compact_actor_identity_graph_payload(actor_graph)
            if compact_case_evidence
            else {
                "actors": actor_graph.get("actors", []),
                "unresolved_references": actor_graph.get("unresolved_references", []),
                "stats": actor_graph.get("stats", {}),
            }
        )
        payload["power_context"] = power_context
        payload["behavioral_taxonomy"] = behavioral_taxonomy_payload(
            allegation_focus=list(params.case_scope.allegation_focus) if params.case_scope is not None else []
        )
        payload["case_patterns"] = _compact_case_patterns_payload(case_patterns) if compact_case_evidence else case_patterns
        payload["retaliation_analysis"] = (
            _compact_retaliation_analysis_payload(retaliation_analysis)
            if compact_case_evidence and isinstance(retaliation_analysis, dict)
            else retaliation_analysis
        )
        payload["comparative_treatment"] = (
            _compact_comparative_treatment_payload(comparative_treatment) if compact_case_evidence else comparative_treatment
        )
        payload["communication_graph"] = communication_graph
        payload["multi_source_case_bundle"] = multi_source_payload
        payload["finding_evidence_index"] = finding_evidence_payload
        payload["evidence_table"] = evidence_table_payload
        payload["behavioral_strength_rubric"] = strength_rubric_payload
        payload["quote_attribution_metrics"] = _quote_attribution_metrics(candidates)
        payload["investigation_report"] = investigation_report_payload
    if not candidates and not attachment_candidates:
        payload["message"] = "No candidate evidence found for the question."
    if effective_top_k < params.max_results:
        payload["_capped"] = {
            "requested": params.max_results,
            "effective": effective_top_k,
            "profile": settings.mcp_model_profile,
        }
    if packing is not None:
        payload["_packed"] = packing
    return payload


__all__ = [
    "_compact_optional_case_surfaces",
    "build_payload",
    "rebuild_sections",
]
