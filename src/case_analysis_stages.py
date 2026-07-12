"""Typed, behaviour-preserving stages for the case-analysis orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .case_analysis_common import as_dict
from .case_analysis_harvest import augment_mixed_source_harvest_summary
from .case_analysis_review import annotate_reviewable_items, apply_review_overrides, review_governance_payload
from .case_analysis_scope import derive_case_analysis_query, derive_case_analysis_query_lanes
from .case_analysis_transform import transform_case_analysis_payload
from .case_operator_intake import ingest_chat_exports
from .comparative_treatment import augment_comparative_treatment_with_sources
from .matter_file_ingestion import enrich_matter_manifest, infer_matter_manifest_authorized_roots
from .matter_ingestion import build_matter_ingestion_report
from .mcp_models import EmailAnswerContextInput, EmailCaseAnalysisInput
from .multi_source_case_bundle import append_chat_log_sources, append_manifest_sources
from .question_execution_waves import derive_wave_query_lane_specs
from .trigger_retaliation import augment_retaliation_analysis_with_sources

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto


@dataclass(slots=True)
class CaseAnalysisRuntime:
    """Intermediate state shared by the explicit analysis pipeline stages."""

    query_lanes: list[str]
    archive_harvest: dict[str, Any]
    answer_payload: dict[str, Any]


def _answer_context_question(question: str) -> str:
    normalized = " ".join(question.split()).strip()
    if len(normalized) <= 500:
        return normalized
    clipped = normalized[:497].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return f"{clipped}..."


def _selected_top_k(max_results: int) -> int:
    return min(max_results, 15)


async def build_runtime(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    *,
    harvest_builder: Callable[..., Awaitable[dict[str, Any]]],
) -> CaseAnalysisRuntime:
    """Run archive collection and answer-context construction as one typed stage."""
    from .tools.search_answer_context import build_answer_context_payload

    query_lanes = derive_case_analysis_query_lanes(params)
    selected_top_k = _selected_top_k(params.max_results)
    archive_harvest = await harvest_builder(deps, params, query_lanes=query_lanes, selected_top_k=selected_top_k)
    answer_params = EmailAnswerContextInput(
        question=_answer_context_question(derive_case_analysis_query(params)),
        max_results=selected_top_k,
        evidence_mode=params.evidence_mode,
        case_scope=params.case_scope,
        query_lanes=query_lanes,
        scan_id=params.scan_id,
    )
    answer_payload = await build_answer_context_payload(
        deps,
        answer_params,
        preloaded_results=archive_harvest["selected_results"],
        preloaded_evidence_rows=archive_harvest.get("promoted_evidence_rows"),
        lane_diagnostics_override=archive_harvest["lane_diagnostics"],
        retrieval_context_override=archive_harvest["summary"],
    )
    return CaseAnalysisRuntime(query_lanes, archive_harvest, answer_payload)


def _harvest_summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_pool_count": int(summary.get("candidate_pool_count") or 0),
        "selected_result_count": int(summary.get("selected_result_count") or 0),
        "raw_candidate_count": int(summary.get("raw_candidate_count") or 0),
        "compact_candidate_count": int(summary.get("compact_candidate_count") or 0),
        "harvest_run_status": str(summary.get("harvest_run_status") or "completed"),
        "lane_top_k": int(summary.get("lane_top_k") or 0),
        "merge_budget": int(summary.get("merge_budget") or 0),
        "adaptive_breadth": dict(as_dict(summary.get("adaptive_breadth"))),
        "coverage_gate": dict(as_dict(summary.get("coverage_gate"))),
        "quality_gate": dict(as_dict(summary.get("quality_gate"))),
        "actor_discovery": dict(as_dict(summary.get("actor_discovery"))),
        "source_basis": dict(as_dict(summary.get("source_basis"))),
        "expansion_diagnostics": _expansion_diagnostics(summary),
    }


def _expansion_diagnostics(summary: dict[str, Any]) -> dict[str, Any]:
    diagnostics = as_dict(summary.get("expansion_diagnostics"))
    return {
        "status": str(diagnostics.get("status") or "ok"),
        "error_count": int(diagnostics.get("error_count") or 0),
    }


def add_retrieval_plan(runtime: CaseAnalysisRuntime, params: EmailCaseAnalysisInput) -> None:
    """Attach output-stable retrieval plan metadata to the answer payload."""
    effective_lanes = [
        str(item) for item in runtime.archive_harvest["summary"].get("effective_query_lanes", []) if str(item).strip()
    ]
    selected_top_k = _selected_top_k(params.max_results)
    plan: dict[str, Any] = {
        "requested_max_results": params.max_results,
        "effective_max_results": selected_top_k,
        "capped": selected_top_k < params.max_results,
        "cap_reason": "email_answer_context_contract" if selected_top_k < params.max_results else "",
        "requested_query_lane_count": len(runtime.query_lanes),
        "effective_query_lane_count": len(effective_lanes or runtime.query_lanes),
        "query_lanes": runtime.query_lanes,
        "effective_query_lanes": effective_lanes or list(runtime.query_lanes),
        "archive_harvest": _harvest_summary_payload(runtime.archive_harvest["summary"]),
    }
    if params.wave_id:
        plan["query_lane_classes"] = [spec.lane_class for spec in derive_wave_query_lane_specs(params, params.wave_id)]
        plan["wave_id"] = params.wave_id
    if params.scan_id:
        plan["scan_id"] = params.scan_id
    runtime.answer_payload["retrieval_plan"] = plan


def add_mixed_source_inputs(runtime: CaseAnalysisRuntime, params: EmailCaseAnalysisInput) -> bool:
    """Ingest and append optional chat and manifest evidence without changing order."""
    chat_entries = [entry.model_dump(mode="json") for entry in params.chat_log_entries]
    if params.chat_exports:
        report = ingest_chat_exports([entry.model_dump(mode="json") for entry in params.chat_exports])
        runtime.answer_payload["chat_export_ingestion_report"] = report
        chat_entries.extend(entry for entry in report.get("entries", []) if isinstance(entry, dict))
    if chat_entries:
        runtime.answer_payload["multi_source_case_bundle"] = append_chat_log_sources(
            runtime.answer_payload.get("multi_source_case_bundle"), chat_log_entries=chat_entries
        )
    manifest_payload = _append_manifest(runtime.answer_payload, params)
    runtime.answer_payload["matter_ingestion_report"] = build_matter_ingestion_report(
        review_mode=params.review_mode,
        matter_manifest=manifest_payload,
        multi_source_case_bundle=runtime.answer_payload.get("multi_source_case_bundle"),
    )
    return bool(chat_entries) or manifest_payload is not None


def _append_manifest(payload: dict[str, Any], params: EmailCaseAnalysisInput) -> dict[str, Any] | None:
    if params.matter_manifest is None:
        return None
    manifest = params.matter_manifest.model_dump(mode="json")
    enriched = enrich_matter_manifest(manifest, approved_roots=infer_matter_manifest_authorized_roots(manifest))
    payload["multi_source_case_bundle"] = append_manifest_sources(
        payload.get("multi_source_case_bundle"), matter_manifest=enriched
    )
    return enriched


def add_mixed_source_analyses(runtime: CaseAnalysisRuntime, params: EmailCaseAnalysisInput, has_sources: bool) -> None:
    """Refresh source-aware analyses and harvest metrics after source assembly."""
    bundle = runtime.answer_payload.get("multi_source_case_bundle")
    if has_sources:
        runtime.answer_payload["retaliation_analysis"] = augment_retaliation_analysis_with_sources(
            runtime.answer_payload.get("retaliation_analysis"), case_scope=params.case_scope, multi_source_case_bundle=bundle
        )
        runtime.answer_payload["comparative_treatment"] = augment_comparative_treatment_with_sources(
            runtime.answer_payload.get("comparative_treatment"),
            case_bundle=runtime.answer_payload.get("case_bundle"),
            multi_source_case_bundle=bundle,
        )
    summary = augment_mixed_source_harvest_summary(
        summary=dict(runtime.archive_harvest["summary"]), multi_source_case_bundle=bundle, params=params
    )
    runtime.archive_harvest["summary"] = summary
    runtime.answer_payload["retrieval_plan"]["archive_harvest"] = {
        **dict(runtime.answer_payload["retrieval_plan"].get("archive_harvest") or {}),
        "mixed_source_metrics": dict(summary.get("mixed_source_metrics") or {}),
        "coverage_gate": dict(summary.get("coverage_gate") or {}),
        "quality_gate": dict(summary.get("quality_gate") or {}),
        "actor_discovery": dict(summary.get("actor_discovery") or {}),
        "harvest_run_status": str(summary.get("harvest_run_status") or "completed"),
        "expansion_diagnostics": _expansion_diagnostics(summary),
    }


def _wave_execution(runtime: CaseAnalysisRuntime, params: EmailCaseAnalysisInput) -> dict[str, Any]:
    summary = runtime.archive_harvest["summary"]
    return {
        "wave_id": str(params.wave_id or ""),
        "scan_id": str(params.scan_id or ""),
        "query_lane_count": len(runtime.query_lanes),
        "query_lanes": runtime.query_lanes,
        "status": "completed",
        "archive_harvest_status": str(as_dict(summary.get("coverage_gate")).get("status") or ""),
        "archive_harvest_quality_status": str(as_dict(summary.get("quality_gate")).get("status") or ""),
    }


def transform_runtime(runtime: CaseAnalysisRuntime, params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Transform stable answer data to the case report projection."""
    transformed = transform_case_analysis_payload(runtime.answer_payload, params)
    transformed["archive_harvest"] = dict(runtime.archive_harvest["summary"])
    transformed["candidates"] = list(runtime.answer_payload.get("candidates") or [])
    transformed["attachment_candidates"] = list(runtime.answer_payload.get("attachment_candidates") or [])
    transformed["wave_execution"] = _wave_execution(runtime, params)
    local_views = transformed.get("wave_local_views")
    if isinstance(local_views, dict):
        transformed["wave_execution"]["local_view_counts"] = {
            str(key): int(value)
            for key, value in dict(local_views.get("surface_counts") or {}).items()
            if isinstance(value, int | float)
        }
    return annotate_reviewable_items(transformed)


def apply_review_and_persistence(
    deps: ToolDepsProto, params: EmailCaseAnalysisInput, transformed: dict[str, Any]
) -> dict[str, Any]:
    """Apply persisted review overrides and allowed snapshot persistence."""
    transformed["persistence_mode"] = "not_persisted"
    workspace_id = str(as_dict(as_dict(transformed.get("matter_workspace"))).get("workspace_id") or "")
    email_db = _email_db(deps)
    overrides = _review_overrides(email_db, workspace_id)
    if overrides:
        transformed = apply_review_overrides(transformed, overrides)
    transformed["review_governance"] = review_governance_payload(workspace_id=workspace_id, overrides=overrides)
    persistence = _persist_snapshot(email_db, params, transformed)
    if persistence is not None:
        transformed["matter_persistence"] = persistence
        transformed["persistence_mode"] = "durable_snapshot"
    _update_report_metadata(transformed, persistence)
    return transformed


def _email_db(deps: ToolDepsProto) -> Any:
    getter = getattr(deps, "get_email_db", None)
    return getter() if callable(getter) else None


def _review_overrides(email_db: Any, workspace_id: str) -> list[dict[str, Any]]:
    getter = cast(Any, getattr(email_db, "list_matter_review_overrides", None))
    if not workspace_id or not callable(getter):
        return []
    return getter(workspace_id=workspace_id, apply_on_refresh_only=True)


def _persist_snapshot(email_db: Any, params: EmailCaseAnalysisInput, payload: dict[str, Any]) -> dict[str, Any] | None:
    saver = cast(Any, getattr(email_db, "persist_matter_snapshot", None))
    if params.review_mode != "exhaustive_matter_review" or not callable(saver):
        return None
    return saver(payload=payload, review_mode=params.review_mode, source_scope=params.source_scope)


def _update_report_metadata(payload: dict[str, Any], persistence: dict[str, Any] | None) -> None:
    report = payload.get("investigation_report")
    if not isinstance(report, dict):
        return
    report["review_governance"] = dict(payload["review_governance"])
    report["persistence_mode"] = payload["persistence_mode"]
    if persistence is not None:
        report["matter_persistence"] = dict(persistence)
