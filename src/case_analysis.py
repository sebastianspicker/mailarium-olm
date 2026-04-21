"""Dedicated workplace case-analysis wrapper over the answer-context pipeline."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from .case_analysis_common import as_dict
from .case_analysis_coverage import matter_coverage_ledger
from .case_analysis_harvest import augment_mixed_source_harvest_summary, build_archive_harvest_bundle
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


_MAX_ANSWER_CONTEXT_QUESTION_CHARS = 500
_MAX_ANSWER_CONTEXT_RESULTS = 15


def _normalize_answer_context_question(question: str) -> str:
    """Keep derived case-analysis queries within answer-context limits."""
    normalized = " ".join(question.split()).strip()
    if len(normalized) <= _MAX_ANSWER_CONTEXT_QUESTION_CHARS:
        return normalized
    clipped = normalized[: _MAX_ANSWER_CONTEXT_QUESTION_CHARS - 3].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return f"{clipped}..."


def _normalize_answer_context_max_results(max_results: int) -> int:
    """Clamp exhaustive case-analysis breadth to the answer-context contract."""
    return min(max_results, _MAX_ANSWER_CONTEXT_RESULTS)


def _retrieval_plan(max_results: int) -> dict[str, Any]:
    """Return explicit retrieval-cap metadata for the case-analysis run."""
    effective = _normalize_answer_context_max_results(max_results)
    return {
        "requested_max_results": max_results,
        "effective_max_results": effective,
        "capped": effective < max_results,
        "cap_reason": "email_answer_context_contract" if effective < max_results else "",
    }


def _supports_durable_snapshot_persistence(review_mode: str) -> bool:
    """Only exhaustive matter-review flows may refresh shared snapshot state."""
    return review_mode == "exhaustive_matter_review"


async def build_case_analysis_payload(deps: ToolDepsProto, params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Build the dedicated case-analysis payload as a Python object."""
    from .tools.search_answer_context import build_answer_context_payload

    query_lanes = derive_case_analysis_query_lanes(params)
    selected_top_k = _normalize_answer_context_max_results(params.max_results)
    archive_harvest = await build_archive_harvest_bundle(
        deps,
        params,
        query_lanes=query_lanes,
        selected_top_k=selected_top_k,
    )
    answer_params = EmailAnswerContextInput(
        question=_normalize_answer_context_question(derive_case_analysis_query(params)),
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
    effective_query_lanes = [
        str(item) for item in archive_harvest["summary"].get("effective_query_lanes", []) if str(item).strip()
    ]
    answer_payload["retrieval_plan"] = _retrieval_plan(params.max_results)
    answer_payload["retrieval_plan"]["requested_query_lane_count"] = len(query_lanes)
    answer_payload["retrieval_plan"]["effective_query_lane_count"] = len(effective_query_lanes or query_lanes)
    answer_payload["retrieval_plan"]["query_lanes"] = query_lanes
    answer_payload["retrieval_plan"]["effective_query_lanes"] = effective_query_lanes or list(query_lanes)
    if params.wave_id:
        answer_payload["retrieval_plan"]["query_lane_classes"] = [
            spec.lane_class for spec in derive_wave_query_lane_specs(params, params.wave_id)
        ]
    answer_payload["retrieval_plan"]["archive_harvest"] = {
        "candidate_pool_count": int(archive_harvest["summary"].get("candidate_pool_count") or 0),
        "selected_result_count": int(archive_harvest["summary"].get("selected_result_count") or 0),
        "raw_candidate_count": int(archive_harvest["summary"].get("raw_candidate_count") or 0),
        "compact_candidate_count": int(archive_harvest["summary"].get("compact_candidate_count") or 0),
        "harvest_run_status": str(archive_harvest["summary"].get("harvest_run_status") or "completed"),
        "lane_top_k": int(archive_harvest["summary"].get("lane_top_k") or 0),
        "merge_budget": int(archive_harvest["summary"].get("merge_budget") or 0),
        "adaptive_breadth": dict(as_dict(archive_harvest["summary"].get("adaptive_breadth"))),
        "coverage_gate": dict(as_dict(archive_harvest["summary"].get("coverage_gate"))),
        "quality_gate": dict(as_dict(archive_harvest["summary"].get("quality_gate"))),
        "actor_discovery": dict(as_dict(archive_harvest["summary"].get("actor_discovery"))),
        "source_basis": dict(as_dict(archive_harvest["summary"].get("source_basis"))),
        "expansion_diagnostics": {
            "status": str(as_dict(archive_harvest["summary"].get("expansion_diagnostics")).get("status") or "ok"),
            "error_count": int(as_dict(archive_harvest["summary"].get("expansion_diagnostics")).get("error_count") or 0),
        },
    }
    if params.wave_id:
        answer_payload["retrieval_plan"]["wave_id"] = params.wave_id
    if params.scan_id:
        answer_payload["retrieval_plan"]["scan_id"] = params.scan_id
    normalized_chat_log_entries = [entry.model_dump(mode="json") for entry in params.chat_log_entries]
    if params.chat_exports:
        chat_export_ingestion_report = ingest_chat_exports([entry.model_dump(mode="json") for entry in params.chat_exports])
        answer_payload["chat_export_ingestion_report"] = chat_export_ingestion_report
        normalized_chat_log_entries.extend(
            [entry for entry in chat_export_ingestion_report.get("entries", []) if isinstance(entry, dict)]
        )
    if normalized_chat_log_entries:
        answer_payload["multi_source_case_bundle"] = append_chat_log_sources(
            answer_payload.get("multi_source_case_bundle"),
            chat_log_entries=normalized_chat_log_entries,
        )
    if params.matter_manifest is not None:
        manifest_dict = params.matter_manifest.model_dump(mode="json")
        manifest_payload = enrich_matter_manifest(
            manifest_dict,
            approved_roots=infer_matter_manifest_authorized_roots(manifest_dict),
        )
        answer_payload["multi_source_case_bundle"] = append_manifest_sources(
            answer_payload.get("multi_source_case_bundle"),
            matter_manifest=manifest_payload,
        )
        answer_payload["matter_ingestion_report"] = build_matter_ingestion_report(
            review_mode=params.review_mode,
            matter_manifest=manifest_payload,
            multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        )
    else:
        answer_payload["matter_ingestion_report"] = build_matter_ingestion_report(
            review_mode=params.review_mode,
            matter_manifest=None,
            multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        )
    if normalized_chat_log_entries or params.matter_manifest is not None:
        answer_payload["retaliation_analysis"] = augment_retaliation_analysis_with_sources(
            answer_payload.get("retaliation_analysis"),
            case_scope=params.case_scope,
            multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        )
        answer_payload["comparative_treatment"] = augment_comparative_treatment_with_sources(
            answer_payload.get("comparative_treatment"),
            case_bundle=answer_payload.get("case_bundle"),
            multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        )
    archive_harvest["summary"] = augment_mixed_source_harvest_summary(
        summary=dict(archive_harvest["summary"]),
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        params=params,
    )
    answer_payload["retrieval_plan"]["archive_harvest"] = {
        **dict(answer_payload["retrieval_plan"].get("archive_harvest") or {}),
        "mixed_source_metrics": dict(archive_harvest["summary"].get("mixed_source_metrics") or {}),
        "coverage_gate": dict(archive_harvest["summary"].get("coverage_gate") or {}),
        "quality_gate": dict(archive_harvest["summary"].get("quality_gate") or {}),
        "actor_discovery": dict(archive_harvest["summary"].get("actor_discovery") or {}),
        "harvest_run_status": str(archive_harvest["summary"].get("harvest_run_status") or "completed"),
        "expansion_diagnostics": {
            "status": str(as_dict(archive_harvest["summary"].get("expansion_diagnostics")).get("status") or "ok"),
            "error_count": int(as_dict(archive_harvest["summary"].get("expansion_diagnostics")).get("error_count") or 0),
        },
    }
    transformed = transform_case_analysis_payload(answer_payload, params)
    transformed["archive_harvest"] = dict(archive_harvest["summary"])
    transformed["candidates"] = list(answer_payload.get("candidates") or [])
    transformed["attachment_candidates"] = list(answer_payload.get("attachment_candidates") or [])
    transformed["wave_execution"] = {
        "wave_id": str(params.wave_id or ""),
        "scan_id": str(params.scan_id or ""),
        "query_lane_count": len(query_lanes),
        "query_lanes": query_lanes,
        "status": "completed",
        "archive_harvest_status": str(as_dict(archive_harvest["summary"].get("coverage_gate")).get("status") or ""),
        "archive_harvest_quality_status": str(as_dict(archive_harvest["summary"].get("quality_gate")).get("status") or ""),
    }
    if isinstance(transformed.get("wave_local_views"), dict):
        transformed["wave_execution"]["local_view_counts"] = {
            str(key): int(value)
            for key, value in dict(transformed["wave_local_views"].get("surface_counts") or {}).items()
            if isinstance(value, (int, float))
        }
    transformed = annotate_reviewable_items(transformed)
    transformed["persistence_mode"] = "not_persisted"

    workspace_id = str(as_dict(as_dict(transformed.get("matter_workspace"))).get("workspace_id") or "")
    overrides: list[dict[str, Any]] = []
    get_email_db = getattr(deps, "get_email_db", None)
    email_db = get_email_db() if callable(get_email_db) else None
    email_db_any = cast(Any, email_db)
    list_review_overrides = cast(
        Callable[..., list[dict[str, Any]]] | None,
        getattr(email_db_any, "list_matter_review_overrides", None),
    )
    if workspace_id and list_review_overrides is not None:
        overrides = list_review_overrides(
            workspace_id=workspace_id,
            apply_on_refresh_only=True,
        )
        transformed = apply_review_overrides(transformed, overrides)
    transformed["review_governance"] = review_governance_payload(
        workspace_id=workspace_id,
        overrides=overrides,
    )
    matter_persistence: dict[str, Any] | None = None
    persist_matter_snapshot = cast(
        Callable[..., dict[str, Any] | None] | None,
        getattr(email_db_any, "persist_matter_snapshot", None),
    )
    if _supports_durable_snapshot_persistence(params.review_mode) and persist_matter_snapshot is not None:
        matter_persistence = persist_matter_snapshot(
            payload=transformed,
            review_mode=params.review_mode,
            source_scope=params.source_scope,
        )
        transformed["matter_persistence"] = matter_persistence
        transformed["persistence_mode"] = "durable_snapshot"
    report = transformed.get("investigation_report")
    if isinstance(report, dict):
        report["review_governance"] = dict(transformed["review_governance"])
        report["persistence_mode"] = transformed["persistence_mode"]
        if matter_persistence is not None:
            report["matter_persistence"] = dict(matter_persistence)
    return transformed


async def build_case_analysis(deps: ToolDepsProto, params: EmailCaseAnalysisInput) -> str:
    """Build the dedicated case-analysis payload."""
    transformed = await build_case_analysis_payload(deps, params)
    return json.dumps(transformed, indent=2)


_matter_coverage_ledger = matter_coverage_ledger
