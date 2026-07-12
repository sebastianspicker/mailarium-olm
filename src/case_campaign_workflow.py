"""Shared wave-execution workflow exposed through both CLI and MCP."""
# pylint: disable=too-many-arguments,too-many-locals

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from .case_analysis import build_case_analysis_payload
from .evidence_harvest import harvest_wave_payload
from .mcp_models import EmailCaseAnalysisInput
from .question_execution_waves import (
    derive_wave_query_lane_specs,
    derive_wave_query_lanes,
    get_wave_definition,
    list_wave_definitions,
)

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto


_SHARED_CAMPAIGN_OWNER = "case_campaign_workflow"
_CAMPAIGN_COMPLETION_RULE = "campaign_closure_allowed_when_results_control_is_current"


def build_execution_authority(*, surface: str, case_action: str) -> dict[str, str]:
    """Return normalized execution-authority metadata for case workflows."""
    normalized_action = str(case_action or "").strip()
    if normalized_action in {"execute-wave", "execute-all-waves", "gather-evidence"}:
        return {
            "surface": surface,
            "case_action": normalized_action,
            "status": "shared_campaign_execution_surface",
            "shared_owner": _SHARED_CAMPAIGN_OWNER,
            "authoritative_scope": "evidence_harvest" if normalized_action == "gather-evidence" else "wave_execution",
            "completion_rule": _CAMPAIGN_COMPLETION_RULE,
            "parity_surface": "mcp_server" if surface == "repository_cli" else "repository_cli",
        }
    if normalized_action in {"refresh-active-run", "archive-results"}:
        return {
            "surface": surface,
            "case_action": normalized_action,
            "status": "supported_results_control_surface",
            "shared_owner": "investigation_results_workspace",
            "authoritative_scope": "results_control",
            "completion_rule": "maintains_machine_readable_results_state",
        }
    return {
        "surface": surface,
        "case_action": normalized_action,
        "status": "non_authoritative_cli_wrapper" if surface == "repository_cli" else "mcp_governed_analysis_surface",
        "authoritative_surface": "mcp_server",
        "completion_rule": "dedicated_legal_support_products_remain_mcp_governed",
    }


def stamp_execution_payload(
    payload: dict[str, Any],
    *,
    surface: str,
    case_action: str,
) -> dict[str, Any]:
    """Attach normalized execution-authority metadata to a JSON-like payload."""
    stamped = dict(payload)
    stamped["execution_authority"] = build_execution_authority(surface=surface, case_action=case_action)
    return stamped


def derive_wave_scan_id(*, scan_id_prefix: str | None, wave_id: str) -> str:
    """Return the canonical scan-session id for one wave."""
    prefix = str(scan_id_prefix or "").strip()
    if not prefix:
        prefix = f"wave-run-{int(time.time() * 1000)}"
    return f"{prefix}:{wave_id}"


def build_wave_case_params(
    params: EmailCaseAnalysisInput,
    *,
    wave_id: str,
    scan_id_prefix: str | None = None,
) -> tuple[EmailCaseAnalysisInput, dict[str, Any]]:
    """Return a wave-specialized case-analysis input plus stable wave metadata."""
    definition = get_wave_definition(wave_id)
    explicit_query_lanes = _normalized_query_lanes(params.query_lanes)
    query_lane_specs = [] if explicit_query_lanes else derive_wave_query_lane_specs(params, definition.wave_id)
    payload = params.model_dump(mode="json")
    payload["wave_id"] = definition.wave_id
    payload["query_lanes"] = _resolved_query_lanes(params, definition.wave_id, explicit_query_lanes, query_lane_specs)
    payload["scan_id"] = derive_wave_scan_id(
        scan_id_prefix=(scan_id_prefix or payload.get("scan_id")),
        wave_id=definition.wave_id,
    )
    if not payload.get("analysis_query") and payload["query_lanes"]:
        payload["analysis_query"] = payload["query_lanes"][0]
    return EmailCaseAnalysisInput.model_validate(payload), {
        "wave_id": definition.wave_id,
        "label": definition.label,
        "questions": list(definition.question_ids),
        "query_lanes": list(payload["query_lanes"]),
        "query_lane_classes": [spec.lane_class for spec in query_lane_specs],
        "scan_id": str(payload["scan_id"]),
    }


def _normalized_query_lanes(query_lanes: list[str]) -> list[str]:
    return [" ".join(str(item or "").split()).strip() for item in query_lanes if str(item or "").strip()]


def _resolved_query_lanes(params: EmailCaseAnalysisInput, wave_id: str, explicit: list[str], specs: list[Any]) -> list[str]:
    return explicit or [spec.query for spec in specs] or derive_wave_query_lanes(params, wave_id)


def _wave_summary_row(
    payload: dict[str, Any],
    *,
    wave_meta: dict[str, Any],
) -> dict[str, Any]:
    retrieval_plan = _dict_value(payload, "retrieval_plan")
    wave_local = _dict_value(payload, "wave_local_views")
    archive_harvest = _dict_value(payload, "archive_harvest")
    evidence_harvest = _dict_value(payload, "evidence_harvest")
    return {
        "wave_id": wave_meta["wave_id"],
        "label": wave_meta["label"],
        "questions": list(wave_meta["questions"]),
        "query_lanes": list(wave_meta["query_lanes"]),
        "query_lane_classes": list(wave_meta.get("query_lane_classes", [])),
        "scan_id": wave_meta["scan_id"],
        "retrieval_plan": {
            "effective_max_results": retrieval_plan.get("effective_max_results"),
            "query_lane_count": retrieval_plan.get("effective_query_lane_count"),
        },
        "archive_harvest": _archive_harvest_summary(archive_harvest),
        "wave_local_views": _surface_counts(wave_local),
        "evidence_harvest": _evidence_harvest_summary(evidence_harvest),
    }


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _surface_counts(payload: dict[str, Any]) -> dict[str, int]:
    return {key: int(value) for key, value in _dict_value(payload, "surface_counts").items() if isinstance(value, int | float)}


def _evidence_harvest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": _str_value(payload, "status"),
        "candidate_count": _int_value(payload, "candidate_count"),
        "promoted_count": _int_value(payload, "promoted_count"),
        "exact_body_candidate_count": _int_value(payload, "exact_body_candidate_count"),
    }


def _archive_harvest_summary(harvest: dict[str, Any]) -> dict[str, Any]:
    coverage = _dict_value(harvest, "coverage_gate")
    quality = _dict_value(harvest, "quality_gate")
    basis = _dict_value(harvest, "source_basis")
    metrics = _dict_value(harvest, "coverage_metrics")
    mixed = _dict_value(harvest, "mixed_source_metrics")
    actors = _dict_value(harvest, "actor_discovery")
    return {
        "status": _str_value(coverage, "status"),
        "quality_status": _str_value(quality, "status"),
        "quality_score": _float_value(quality, "score"),
        "primary_source": _str_value(basis, "primary_source"),
        "unique_hits": _int_value(metrics, "unique_hits"),
        "unique_threads": _int_value(metrics, "unique_threads"),
        "unique_months": _int_value(metrics, "unique_months"),
        "verified_exact_hits": _int_value(metrics, "verified_exact_hits"),
        "attachment_candidates": _int_value(metrics, "attachment_candidate_count"),
        "non_email_sources": _int_value(mixed, "non_email_source_count"),
        "linked_non_email_sources": _int_value(mixed, "linked_non_email_source_count"),
        "document_only_actors": _int_value(actors, "document_only_actor_count"),
    }


def _str_value(payload: dict[str, Any], key: str) -> str:
    return str(payload.get(key) or "")


def _int_value(payload: dict[str, Any], key: str) -> int:
    return int(payload.get(key) or 0)


def _float_value(payload: dict[str, Any], key: str) -> float:
    return float(payload.get(key) or 0.0)


async def execute_wave_payload(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    *,
    wave_id: str,
    scan_id_prefix: str | None = None,
) -> dict[str, Any]:
    """Execute one wave against the shared case-analysis runtime."""
    wave_params, wave_meta = build_wave_case_params(
        params,
        wave_id=wave_id,
        scan_id_prefix=scan_id_prefix,
    )
    payload = await build_case_analysis_payload(deps, wave_params)
    wave_execution_raw = payload.get("wave_execution")
    if isinstance(wave_execution_raw, dict):
        wave_execution = dict(wave_execution_raw)
        wave_execution.update(wave_meta)
    else:
        wave_execution = {**wave_meta, "status": "completed"}
    result = dict(payload)
    result["wave_execution"] = wave_execution
    return result


async def execute_all_waves_payload(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    *,
    scan_id_prefix: str | None = None,
    include_payloads: bool = False,
) -> dict[str, Any]:
    """Execute all waves through the shared case-analysis runtime."""
    resolved_scan_id_prefix = scan_id_prefix or f"wave-run-{int(time.time() * 1000)}"
    summaries: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for definition in list_wave_definitions():
        payload = await execute_wave_payload(
            deps,
            params,
            wave_id=definition.wave_id,
            scan_id_prefix=resolved_scan_id_prefix,
        )
        wave_execution_raw = payload.get("wave_execution")
        wave_meta = (
            dict(wave_execution_raw)
            if isinstance(wave_execution_raw, dict)
            else {
                "wave_id": definition.wave_id,
                "label": definition.label,
                "questions": list(definition.question_ids),
                "query_lanes": [],
                "scan_id": derive_wave_scan_id(scan_id_prefix=resolved_scan_id_prefix, wave_id=definition.wave_id),
            }
        )
        summaries.append(_wave_summary_row(payload, wave_meta=wave_meta))
        if include_payloads:
            payloads.append(payload)

    result: dict[str, Any] = {
        "workflow": "case_execute_all_waves",
        "status": "completed",
        "wave_count": len(summaries),
        "scan_id_prefix": resolved_scan_id_prefix,
        "waves": summaries,
    }
    if include_payloads:
        result["wave_payloads"] = payloads
    return result


async def gather_evidence_payload(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    *,
    run_id: str,
    phase_id: str,
    scan_id_prefix: str | None = None,
    harvest_limit_per_wave: int = 12,
    promote_limit_per_wave: int = 4,
    include_payloads: bool = False,
) -> dict[str, Any]:
    """Execute all waves and persist harvested evidence candidates plus exact quote promotions."""
    resolved_scan_id_prefix = scan_id_prefix or f"wave-run-{int(time.time() * 1000)}"
    get_email_db = getattr(deps, "get_email_db", None)
    db = get_email_db() if callable(get_email_db) else None

    if db is None:
        return _db_unavailable_payload(run_id, phase_id, resolved_scan_id_prefix)

    summaries, payloads, wave_harvests, aggregate = await _gather_wave_harvests(
        deps,
        params,
        db,
        run_id=run_id,
        phase_id=phase_id,
        scan_id_prefix=resolved_scan_id_prefix,
        harvest_limit=harvest_limit_per_wave,
        promote_limit=promote_limit_per_wave,
        include_payloads=include_payloads,
    )

    db_any: Any = db
    evidence_candidate_stats = getattr(db_any, "evidence_candidate_stats", None)
    evidence_stats_fn = getattr(db_any, "evidence_stats", None)
    candidate_stats = evidence_candidate_stats(run_id=run_id, phase_id=phase_id) if callable(evidence_candidate_stats) else {}
    evidence_stats = evidence_stats_fn() if callable(evidence_stats_fn) else {}

    result: dict[str, Any] = {
        "workflow": "case_gather_evidence",
        "status": "completed" if db is not None else "db_unavailable",
        "run_id": run_id,
        "phase_id": phase_id,
        "scan_id_prefix": resolved_scan_id_prefix,
        "wave_count": len(summaries),
        "waves": summaries,
        "evidence_harvest": {
            **aggregate,
            "wave_harvests": wave_harvests,
            "candidate_stats": candidate_stats,
        },
        "evidence_stats": evidence_stats,
    }
    if include_payloads:
        result["wave_payloads"] = payloads
    return result


def _empty_harvest_totals() -> dict[str, int]:
    return dict.fromkeys(
        (
            "candidate_count",
            "body_candidate_count",
            "attachment_candidate_count",
            "exact_body_candidate_count",
            "duplicate_candidate_count",
            "promoted_count",
            "linked_existing_evidence_count",
        ),
        0,
    )


def _db_unavailable_payload(run_id: str, phase_id: str, scan_id_prefix: str) -> dict[str, Any]:
    return {
        "workflow": "case_gather_evidence",
        "status": "db_unavailable",
        "run_id": run_id,
        "phase_id": phase_id,
        "scan_id_prefix": scan_id_prefix,
        "wave_count": 0,
        "waves": [],
        "evidence_harvest": {**_empty_harvest_totals(), "wave_harvests": [], "candidate_stats": {}},
        "evidence_stats": {},
    }


async def _gather_wave_harvests(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    db: Any,
    *,
    run_id: str,
    phase_id: str,
    scan_id_prefix: str,
    harvest_limit: int,
    promote_limit: int,
    include_payloads: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    summaries: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    harvests: list[dict[str, Any]] = []
    aggregate = _empty_harvest_totals()
    for definition in list_wave_definitions():
        payload = await execute_wave_payload(deps, params, wave_id=definition.wave_id, scan_id_prefix=scan_id_prefix)
        harvest = harvest_wave_payload(
            db,
            payload=payload,
            run_id=run_id,
            phase_id=phase_id,
            harvest_limit_per_wave=harvest_limit,
            promote_limit_per_wave=promote_limit,
        )
        payload["evidence_harvest"] = harvest
        summaries.append(_wave_summary_row(payload, wave_meta=_wave_meta(payload, definition, scan_id_prefix)))
        harvests.append(harvest)
        if include_payloads:
            payloads.append(payload)
        for key in aggregate:
            aggregate[key] += int(harvest.get(key) or 0)
    return summaries, payloads, harvests, aggregate


def _wave_meta(payload: dict[str, Any], definition: Any, scan_id_prefix: str) -> dict[str, Any]:
    execution = payload.get("wave_execution")
    if isinstance(execution, dict):
        return dict(execution)
    return {
        "wave_id": definition.wave_id,
        "label": definition.label,
        "questions": list(definition.question_ids),
        "query_lanes": [],
        "scan_id": derive_wave_scan_id(scan_id_prefix=scan_id_prefix, wave_id=definition.wave_id),
    }
