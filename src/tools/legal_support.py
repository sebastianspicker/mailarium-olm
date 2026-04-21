"""Durable legal-support MCP tools backed by the shared case-analysis workflow."""

from __future__ import annotations

from typing import Any

from ..case_analysis import build_case_analysis_payload
from ..comparative_treatment import shared_comparator_points
from ..legal_support_exporter import LegalSupportExporter
from ..mcp_models import EmailLegalSupportExportInput, EmailLegalSupportInput
from .utils import ToolDepsProto, get_deps, json_response, run_serialized_case_tool

_deps: ToolDepsProto | None = None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _d() -> ToolDepsProto:
    return get_deps(_deps)


def _require_exhaustive_legal_support(params: EmailLegalSupportInput) -> None:
    """Refuse bounded review modes for dedicated legal-support product tools."""
    if params.review_mode != "exhaustive_matter_review":
        raise ValueError(
            "Dedicated legal-support tools require review_mode='exhaustive_matter_review' with matter_manifest. "
            "Use email_case_analysis_exploratory (or the compatibility alias email_case_analysis) "
            "for retrieval-bounded exploratory review."
        )
    if params.matter_manifest is None:
        raise ValueError(
            "Dedicated legal-support tools require matter_manifest so counsel-facing products are backed by full "
            "supplied-artifact accounting."
        )


async def _payload(params: EmailLegalSupportInput) -> dict[str, Any]:
    _require_exhaustive_legal_support(params)
    full_params = params.model_copy(update={"output_mode": "full_report"})
    return await build_case_analysis_payload(_d(), full_params)


def _response(
    *,
    payload: dict[str, Any],
    product: str,
    product_payload: Any,
) -> str:
    return json_response(
        {
            "workflow": "legal_support_product",
            "source_workflow": "case_analysis",
            "product": product,
            "review_mode": str(payload.get("review_mode") or ""),
            "review_classification": payload.get("review_classification"),
            "analysis_query": str(payload.get("analysis_query") or ""),
            "bilingual_workflow": payload.get("bilingual_workflow"),
            "privacy_guardrails": payload.get("privacy_guardrails"),
            "case_scope_quality": payload.get("case_scope_quality"),
            "matter_ingestion_report": payload.get("matter_ingestion_report"),
            "analysis_limits": payload.get("analysis_limits"),
            "refresh_behavior": (
                "Rerun this tool with the same case scope and source scope to refresh the product "
                "from the shared matter entities and current evidence bundle."
            ),
            product: product_payload,
        }
    )


def _comparator_matrix(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a standalone comparator matrix surface from comparative-treatment payloads."""
    comparative = _as_dict(payload.get("comparative_treatment"))
    rows = shared_comparator_points(comparative)
    insufficiency = _as_dict(comparative.get("insufficiency"))
    if not insufficiency:
        summary = _as_dict(comparative.get("summary"))
        missing_inputs = [str(item) for item in summary.get("missing_inputs") or [] if str(item).strip()]
        status = str(summary.get("status") or "")
        if status == "insufficient_comparator_scope" or missing_inputs:
            reason = str(summary.get("insufficiency_reason") or "") or (
                "Comparator analysis is not yet supported on the current record."
            )
            recommended_next_inputs: list[str] = []
            if "comparator_actors" in missing_inputs:
                recommended_next_inputs.append("Add named comparator actors tied to the same manager, policy, or decision path.")
            if "target_person" in missing_inputs:
                recommended_next_inputs.append("Clarify the target person identity before comparing treatment.")
            insufficiency = {
                "status": "insufficient_comparator_scope",
                "reason": reason,
                "missing_inputs": missing_inputs,
                "recommended_next_inputs": recommended_next_inputs,
            }
    return {
        "version": "2",
        "row_count": len(rows),
        "summary": comparative.get("summary"),
        "insufficiency": insufficiency or None,
        "rows": rows,
    }


async def email_case_issue_matrix(params: EmailLegalSupportInput) -> str:
    """Return the durable lawyer-usable issue matrix for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_issue_matrix_impl(params))


async def _email_case_issue_matrix_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(payload=payload, product="lawyer_issue_matrix", product_payload=payload.get("lawyer_issue_matrix"))


async def email_case_skeptical_review(params: EmailLegalSupportInput) -> str:
    """Return the employer-side stress test and repair guidance for one matter."""
    return await run_serialized_case_tool(lambda: _email_case_skeptical_review_impl(params))


async def _email_case_skeptical_review_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(
        payload=payload,
        product="skeptical_employer_review",
        product_payload=payload.get("skeptical_employer_review"),
    )


async def email_case_document_request_checklist(params: EmailLegalSupportInput) -> str:
    """Return the records-request and preservation checklist for one matter."""
    return await run_serialized_case_tool(lambda: _email_case_document_request_checklist_impl(params))


async def _email_case_document_request_checklist_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(
        payload=payload,
        product="document_request_checklist",
        product_payload=payload.get("document_request_checklist"),
    )


async def email_case_actor_witness_map(params: EmailLegalSupportInput) -> str:
    """Return the actor map and witness map for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_actor_witness_map_impl(params))


async def _email_case_actor_witness_map_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return json_response(
        {
            "workflow": "legal_support_product",
            "source_workflow": "case_analysis",
            "product": "actor_and_witness_map",
            "review_mode": str(payload.get("review_mode") or ""),
            "review_classification": payload.get("review_classification"),
            "analysis_query": str(payload.get("analysis_query") or ""),
            "bilingual_workflow": payload.get("bilingual_workflow"),
            "privacy_guardrails": payload.get("privacy_guardrails"),
            "case_scope_quality": payload.get("case_scope_quality"),
            "matter_ingestion_report": payload.get("matter_ingestion_report"),
            "analysis_limits": payload.get("analysis_limits"),
            "refresh_behavior": (
                "Rerun this tool with the same case scope and source scope to refresh the actor and witness maps "
                "from the shared matter entities and current chronology."
            ),
            "actor_map": payload.get("actor_map"),
            "witness_map": payload.get("witness_map"),
        }
    )


async def email_case_promise_contradictions(params: EmailLegalSupportInput) -> str:
    """Return the promise-versus-action, omission, and contradiction analysis."""
    return await run_serialized_case_tool(lambda: _email_case_promise_contradictions_impl(params))


async def _email_case_promise_contradictions_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(
        payload=payload,
        product="promise_contradiction_analysis",
        product_payload=payload.get("promise_contradiction_analysis"),
    )


async def email_case_lawyer_briefing_memo(params: EmailLegalSupportInput) -> str:
    """Return the compact lawyer briefing memo for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_lawyer_briefing_memo_impl(params))


async def _email_case_lawyer_briefing_memo_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(
        payload=payload,
        product="lawyer_briefing_memo",
        product_payload=payload.get("lawyer_briefing_memo"),
    )


async def email_case_draft_preflight(params: EmailLegalSupportInput) -> str:
    """Return the framing preflight for controlled factual drafting."""
    return await run_serialized_case_tool(lambda: _email_case_draft_preflight_impl(params))


async def _email_case_draft_preflight_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    drafting = payload.get("controlled_factual_drafting") if isinstance(payload, dict) else None
    return _response(
        payload=payload,
        product="draft_preflight",
        product_payload=_as_dict(drafting).get("framing_preflight") if isinstance(drafting, dict) else None,
    )


async def email_case_controlled_draft(params: EmailLegalSupportInput) -> str:
    """Return the controlled factual draft for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_controlled_draft_impl(params))


async def _email_case_controlled_draft_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    drafting = payload.get("controlled_factual_drafting") if isinstance(payload, dict) else None
    drafting_dict = _as_dict(drafting)
    controlled_draft = _as_dict(drafting_dict.get("controlled_draft"))
    preflight_ready = bool(_as_dict(drafting_dict.get("summary")).get("preflight_ready")) or bool(
        controlled_draft.get("preflight_ready")
    )
    release_status = str(
        _as_dict(_as_dict(drafting_dict.get("framing_preflight")).get("allegation_ceiling")).get("release_status") or ""
    )
    if not preflight_ready and release_status != "ready_for_controlled_draft":
        raise ValueError(
            "Controlled factual draft is not ready for release. Run email_case_draft_preflight first and resolve "
            "the framing or evidence-discipline blockers before requesting the draft."
        )
    return _response(
        payload=payload,
        product="controlled_factual_draft",
        product_payload=controlled_draft,
    )


async def email_case_retaliation_timeline(params: EmailLegalSupportInput) -> str:
    """Return the structured retaliation timeline assessment for one matter."""
    return await run_serialized_case_tool(lambda: _email_case_retaliation_timeline_impl(params))


async def _email_case_retaliation_timeline_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(
        payload=payload,
        product="retaliation_timeline_assessment",
        product_payload=payload.get("retaliation_timeline_assessment"),
    )


async def email_case_dashboard(params: EmailLegalSupportInput) -> str:
    """Return the compact refreshable dashboard for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_dashboard_impl(params))


async def _email_case_dashboard_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(payload=payload, product="case_dashboard", product_payload=payload.get("case_dashboard"))


async def email_case_evidence_index(params: EmailLegalSupportInput) -> str:
    """Return the standalone exhibit-centric evidence index for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_evidence_index_impl(params))


async def _email_case_evidence_index_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(
        payload=payload,
        product="matter_evidence_index",
        product_payload=payload.get("matter_evidence_index"),
    )


async def email_case_master_chronology(params: EmailLegalSupportInput) -> str:
    """Return the standalone master chronology for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_master_chronology_impl(params))


async def _email_case_master_chronology_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(payload=payload, product="master_chronology", product_payload=payload.get("master_chronology"))


async def email_case_comparator_matrix(params: EmailLegalSupportInput) -> str:
    """Return the standalone comparator matrix for one workplace matter."""
    return await run_serialized_case_tool(lambda: _email_case_comparator_matrix_impl(params))


async def _email_case_comparator_matrix_impl(params: EmailLegalSupportInput) -> str:
    payload = await _payload(params)
    return _response(payload=payload, product="comparator_matrix", product_payload=_comparator_matrix(payload))


async def email_case_export(params: EmailLegalSupportExportInput) -> str:
    """Write a portable legal-support artifact for counsel handoff or internal review."""
    return await run_serialized_case_tool(lambda: _email_case_export_impl(params))


async def _email_case_export_impl(params: EmailLegalSupportExportInput) -> str:
    payload = await _payload(params)
    result = LegalSupportExporter().export_file(
        payload=payload,
        output_path=params.output_path,
        delivery_target=params.delivery_target,
        delivery_format=params.delivery_format,
    )
    persistence = _as_dict(payload.get("matter_persistence"))
    snapshot_id = str(persistence.get("snapshot_id") or "")
    workspace_id = str(persistence.get("workspace_id") or "")
    if snapshot_id and workspace_id:
        email_db = _d().get_email_db()
        if email_db is not None and hasattr(email_db, "record_matter_export"):
            result["recorded_export"] = email_db.record_matter_export(
                snapshot_id=snapshot_id,
                workspace_id=workspace_id,
                delivery_target=params.delivery_target,
                delivery_format=params.delivery_format,
                output_path=str(result.get("output_path") or params.output_path),
                review_state=str(persistence.get("review_state") or ""),
                details={"export_metadata": result.get("export_metadata")},
            )
    return json_response(result)


def register(mcp_instance: Any, deps: ToolDepsProto) -> None:
    """Register durable legal-support MCP tools."""
    global _deps
    _deps = deps
    mcp_instance.tool(name="email_case_issue_matrix", annotations=deps.idempotent_write_annotations("Case Issue Matrix"))(
        email_case_issue_matrix
    )
    mcp_instance.tool(name="email_case_evidence_index", annotations=deps.idempotent_write_annotations("Case Evidence Index"))(
        email_case_evidence_index
    )
    mcp_instance.tool(
        name="email_case_master_chronology",
        annotations=deps.idempotent_write_annotations("Case Master Chronology"),
    )(email_case_master_chronology)
    mcp_instance.tool(
        name="email_case_comparator_matrix",
        annotations=deps.idempotent_write_annotations("Case Comparator Matrix"),
    )(email_case_comparator_matrix)
    mcp_instance.tool(
        name="email_case_skeptical_review",
        annotations=deps.idempotent_write_annotations("Case Skeptical Review"),
    )(email_case_skeptical_review)
    mcp_instance.tool(
        name="email_case_document_request_checklist",
        annotations=deps.idempotent_write_annotations("Case Document Request Checklist"),
    )(email_case_document_request_checklist)
    mcp_instance.tool(
        name="email_case_actor_witness_map",
        annotations=deps.idempotent_write_annotations("Case Actor Witness Map"),
    )(email_case_actor_witness_map)
    mcp_instance.tool(
        name="email_case_promise_contradictions",
        annotations=deps.idempotent_write_annotations("Case Promise Contradictions"),
    )(email_case_promise_contradictions)
    mcp_instance.tool(
        name="email_case_lawyer_briefing_memo",
        annotations=deps.idempotent_write_annotations("Case Lawyer Memo"),
    )(email_case_lawyer_briefing_memo)
    mcp_instance.tool(
        name="email_case_draft_preflight",
        annotations=deps.idempotent_write_annotations("Case Draft Preflight"),
    )(email_case_draft_preflight)
    mcp_instance.tool(
        name="email_case_controlled_draft",
        annotations=deps.idempotent_write_annotations("Case Controlled Draft"),
    )(email_case_controlled_draft)
    mcp_instance.tool(
        name="email_case_retaliation_timeline",
        annotations=deps.idempotent_write_annotations("Case Retaliation Timeline"),
    )(email_case_retaliation_timeline)
    mcp_instance.tool(name="email_case_dashboard", annotations=deps.idempotent_write_annotations("Case Dashboard"))(
        email_case_dashboard
    )
    mcp_instance.tool(name="email_case_export", annotations=deps.idempotent_write_annotations("Case Export"))(email_case_export)
