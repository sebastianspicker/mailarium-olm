"""Typed stages for the adaptive archive-harvest bundle orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .case_analysis_harvest_common import (
    _EXPANSION_ERROR_SAMPLE_LIMIT,
    _adaptive_harvest_plan,
    _annotate_round,
    _archive_size_hint,
    _coverage_signature,
    _dedupe_evidence_rows,
    _mixed_source_harvest_inputs,
    _round_recovered_keys,
    _source_basis_summary,
)
from .case_analysis_harvest_coverage import (
    _coverage_gate,
    _coverage_metrics,
    _coverage_rerun_lanes,
    _coverage_thresholds,
    _split_evidence_bank_layers,
)
from .case_analysis_harvest_expansion import _enrich_evidence_bank
from .case_analysis_harvest_expansion_diagnostics import _aggregate_expansion_diagnostics
from .case_analysis_harvest_quality import _actor_discovery_summary, _harvest_quality_summary
from .case_analysis_scope import derive_case_analysis_query
from .mcp_models import EmailAnswerContextInput, EmailCaseAnalysisInput
from .multi_source_case_bundle import promotable_mixed_source_evidence_rows


@dataclass(slots=True)
class HarvestRoundRuntime:
    """Dependencies and stable request values used for each harvest round."""

    retriever: Any
    email_db: Any
    params: EmailCaseAnalysisInput
    answer_params: EmailAnswerContextInput
    search_kwargs: dict[str, Any]
    selected_top_k: int
    mixed_source_rows: list[dict[str, Any]]
    thresholds: dict[str, int]


@dataclass(slots=True)
class HarvestRoundResult:
    """All ordered outputs from one evaluated harvest round."""

    selected_results: list[Any]
    lane_diagnostics: list[dict[str, Any]]
    search_meta: dict[str, Any]
    evidence_bank: list[dict[str, Any]]
    direct_rows: list[dict[str, Any]]
    expanded_rows: list[dict[str, Any]]
    metrics: dict[str, Any]
    expanded_metrics: dict[str, Any]
    coverage_gate: dict[str, Any]
    actor_discovery: dict[str, Any]
    quality_gate: dict[str, Any]
    expansion_diagnostics: dict[str, Any]


@dataclass(slots=True)
class HarvestRoundsState:
    """Mutable adaptive state retained between bounded rerun rounds."""

    result: HarvestRoundResult
    effective_plan: dict[str, Any]
    effective_query_lanes: list[str]
    rerun_actions: list[str]
    rerun_rounds: list[dict[str, Any]]
    expansion_rounds: list[dict[str, Any]]


async def build_archive_harvest_bundle_stage(
    deps: Any,
    params: EmailCaseAnalysisInput,
    *,
    query_lanes: list[str],
    selected_top_k: int,
) -> dict[str, Any]:
    """Run unavailable or adaptive archive stages and return the stable bundle."""
    retriever = _dependency(deps, "get_retriever")
    email_db = _dependency(deps, "get_email_db")
    mixed_bundle, _chat_entries = _mixed_source_harvest_inputs(params)
    mixed_rows = promotable_mixed_source_evidence_rows(mixed_bundle)
    if retriever is None or not hasattr(retriever, "search_filtered"):
        return _unavailable_bundle(params, query_lanes, selected_top_k, mixed_rows)
    runtime, archive_size, initial_plan = _round_runtime(retriever, email_db, params, query_lanes, selected_top_k, mixed_rows)
    initial = _evaluate_round(runtime, round_index=0, query_lanes=list(query_lanes), plan=initial_plan, prior_rows=[])
    state = _run_coverage_rounds(runtime, archive_size, initial_plan, query_lanes, initial)
    return _completed_bundle(runtime, archive_size, initial_plan, query_lanes, state)


def _dependency(deps: Any, getter_name: str) -> Any:
    getter = getattr(deps, getter_name, None)
    return getter() if callable(getter) else None


def _unavailable_bundle(
    params: EmailCaseAnalysisInput,
    query_lanes: list[str],
    selected_top_k: int,
    mixed_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = _adaptive_harvest_plan(
        params=params, query_lane_count=len(query_lanes), selected_top_k=selected_top_k, total_emails=0, coverage_escalation=False
    )
    promoted = [
        {**dict(row), "harvest_round": int(row.get("harvest_round") or 0)} for row in mixed_rows[: int(plan["merge_budget"])]
    ]
    metrics = _coverage_metrics(evidence_bank=promoted, lane_diagnostics=[])
    summary = _unavailable_summary(params, query_lanes, selected_top_k, plan, promoted, mixed_rows, metrics)
    return {"selected_results": [], "lane_diagnostics": [], "promoted_evidence_rows": promoted, "summary": summary}


def _unavailable_summary(
    params: EmailCaseAnalysisInput,
    query_lanes: list[str],
    selected_top_k: int,
    plan: dict[str, Any],
    promoted: list[dict[str, Any]],
    mixed_rows: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "enabled": False,
        "harvest_run_status": "completed",
        "query_lanes": list(query_lanes),
        "effective_query_lanes": list(query_lanes),
        "selected_top_k": selected_top_k,
        "lane_top_k": 0,
        "merge_budget": 0,
        "candidate_pool_count": 0,
        "selected_result_count": 0,
        "raw_candidate_count": len(promoted),
        "compact_candidate_count": 0,
        "adaptive_breadth": _unavailable_breadth(plan),
        "source_basis": _source_basis_summary(params=params, email_archive_available=False),
        "coverage_metrics": metrics,
        "direct_coverage_metrics": metrics,
        "expanded_coverage_metrics": metrics,
        "coverage_thresholds": _coverage_thresholds(
            params=params, query_lane_count=len(query_lanes), selected_top_k=selected_top_k
        ),
        "coverage_gate": {"status": "needs_more_harvest", "reasons": ["archive_unavailable"], "recommendations": []},
        "quality_gate": {"status": "weak", "score": 0.0, "reasons": ["archive_unavailable"]},
        "actor_discovery": {"discovered_actor_count": 0, "roles": {}, "top_discovered_actors": []},
        "direct_evidence_count": len(promoted),
        "expanded_evidence_count": 0,
        "mixed_source_candidate_count": len(mixed_rows),
        "rerun_rounds": [],
        "later_round_only_evidence_handles": [],
        "expansion_diagnostics": _aggregate_expansion_diagnostics([]),
        "evidence_bank": promoted,
    }


def _unavailable_breadth(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_emails": plan["total_emails"],
        "date_span_days": plan["date_span_days"],
        "initial_lane_top_k": plan["lane_top_k"],
        "initial_merge_budget": plan["merge_budget"],
        "effective_lane_top_k": 0,
        "effective_merge_budget": 0,
        "coverage_rerun_triggered": False,
        "rerun_round_count": 0,
        "rerun_actions": [],
    }


def _round_runtime(
    retriever: Any,
    email_db: Any,
    params: EmailCaseAnalysisInput,
    query_lanes: list[str],
    selected_top_k: int,
    mixed_rows: list[dict[str, Any]],
) -> tuple[HarvestRoundRuntime, dict[str, Any], dict[str, Any]]:
    from .config import get_settings
    from .tools import search_answer_context_impl as impl

    answer_params = EmailAnswerContextInput(
        question=derive_case_analysis_query(params),
        max_results=selected_top_k,
        evidence_mode=params.evidence_mode,
        case_scope=params.case_scope,
        query_lanes=query_lanes,
        scan_id=params.scan_id,
    )
    search_kwargs = impl._answer_context_search_kwargs(answer_params, min(selected_top_k, get_settings().mcp_max_search_results))
    archive_size = _archive_size_hint(retriever)
    initial_plan = _adaptive_harvest_plan(
        params=params,
        query_lane_count=len(query_lanes),
        selected_top_k=selected_top_k,
        total_emails=int(archive_size.get("total_emails") or 0),
        coverage_escalation=False,
    )
    thresholds = _coverage_thresholds(params=params, query_lane_count=len(query_lanes), selected_top_k=selected_top_k)
    return (
        HarvestRoundRuntime(retriever, email_db, params, answer_params, search_kwargs, selected_top_k, mixed_rows, thresholds),
        archive_size,
        initial_plan,
    )


def _evaluate_round(
    runtime: HarvestRoundRuntime,
    *,
    round_index: int,
    query_lanes: list[str],
    plan: dict[str, Any],
    prior_rows: list[dict[str, Any]],
) -> HarvestRoundResult:
    from .tools.search_answer_context_runtime import _search_across_query_lanes

    selected, diagnostics, search_meta = _search_across_query_lanes(
        retriever=runtime.retriever,
        search_kwargs=runtime.search_kwargs,
        query_lanes=query_lanes,
        top_k=runtime.selected_top_k,
        scan_id=runtime.params.scan_id,
        lane_top_k=int(plan["lane_top_k"]),
        reserve_per_lane=int(plan["reserve_per_lane"]),
        bank_limit=int(plan["merge_budget"]),
    )
    search_bank, expansion = _round_evidence(runtime, round_index, plan, prior_rows, search_meta)
    direct, expanded = _split_evidence_bank_layers(search_bank)
    metrics = _coverage_metrics(evidence_bank=direct, lane_diagnostics=diagnostics)
    expanded_metrics = _coverage_metrics(evidence_bank=search_bank, lane_diagnostics=diagnostics)
    gate = _coverage_gate(
        direct_metrics=metrics, expanded_metrics=expanded_metrics, thresholds=runtime.thresholds, evidence_bank=search_bank
    )
    actors = _actor_discovery_summary(evidence_bank=search_bank, params=runtime.params)
    quality = _harvest_quality_summary(evidence_bank=search_bank, metrics=expanded_metrics, actor_discovery=actors)
    quality["round_summary"] = _round_summary(
        round_index, query_lanes, plan, search_meta, gate, search_bank, prior_rows, runtime.mixed_source_rows, expansion
    )
    return HarvestRoundResult(
        selected,
        diagnostics,
        search_meta,
        search_bank,
        direct,
        expanded,
        metrics,
        expanded_metrics,
        gate,
        actors,
        quality,
        expansion,
    )


def _round_evidence(
    runtime: HarvestRoundRuntime,
    round_index: int,
    plan: dict[str, Any],
    prior_rows: list[dict[str, Any]],
    search_meta: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = [
        {**dict(item), "harvest_round": round_index} for item in search_meta.get("evidence_bank", []) if isinstance(item, dict)
    ]
    bank, expansion = _enrich_evidence_bank(
        db=runtime.email_db,
        answer_params=runtime.answer_params,
        bank_entries=entries,
        bank_results=list(search_meta.get("evidence_results", [])),
        exhaustive_review=runtime.params.review_mode == "exhaustive_matter_review",
    )
    bank = _annotate_round(bank, prior_rows=prior_rows, round_index=round_index)
    mixed = [
        {**dict(row), "harvest_round": int(row.get("harvest_round") or 0)}
        for row in runtime.mixed_source_rows[: int(plan["merge_budget"])]
    ]
    return _dedupe_evidence_rows([*bank, *mixed]), expansion


def _round_summary(
    round_index: int,
    query_lanes: list[str],
    plan: dict[str, Any],
    search_meta: dict[str, Any],
    gate: dict[str, Any],
    bank: list[dict[str, Any]],
    prior_rows: list[dict[str, Any]],
    mixed_rows: list[dict[str, Any]],
    expansion: dict[str, Any],
) -> dict[str, Any]:
    recovered = _round_recovered_keys(bank, prior_rows)
    summary = {
        "round": round_index,
        "query_lane_count": len(query_lanes),
        "lane_top_k": int(search_meta.get("lane_top_k") or plan["lane_top_k"]),
        "merge_budget": int(search_meta.get("merge_budget") or plan["merge_budget"]),
        "coverage_status": str(gate.get("status") or ""),
        "recovered_count": len(recovered),
        "recovered_evidence_handles": recovered[:12],
        "mixed_source_candidate_count": len(mixed_rows),
        "expansion_status": str(expansion.get("status") or "ok"),
        "expansion_error_count": int(expansion.get("error_count") or 0),
    }
    if int(expansion.get("error_count") or 0) > 0:
        summary["expansion_errors"] = _round_expansion_errors(expansion)
    return summary


def _round_expansion_errors(expansion: dict[str, Any]) -> dict[str, Any]:
    return {key: _expansion_error_group(expansion, key) for key in ("thread_expansion", "attachment_expansion")}


def _expansion_error_group(expansion: dict[str, Any], key: str) -> dict[str, Any]:
    group = expansion.get(key) or {}
    return {
        "error_count": int(group.get("error_count") or 0),
        "errors": [item for item in list(group.get("errors") or [])[:_EXPANSION_ERROR_SAMPLE_LIMIT] if isinstance(item, dict)],
    }


def _run_coverage_rounds(
    runtime: HarvestRoundRuntime,
    archive_size: dict[str, Any],
    initial_plan: dict[str, Any],
    query_lanes: list[str],
    initial: HarvestRoundResult,
) -> HarvestRoundsState:
    state = HarvestRoundsState(
        initial,
        dict(initial_plan),
        list(query_lanes),
        [],
        [dict(initial.quality_gate.pop("round_summary", {}))],
        [{"round": 0, **dict(initial.expansion_diagnostics)}],
    )
    round_index = 0
    while state.result.coverage_gate["status"] == "needs_more_harvest" and round_index + 1 < 3:
        if not _run_next_round(runtime, archive_size, state, round_index):
            break
        round_index += 1
    return state


def _run_next_round(
    runtime: HarvestRoundRuntime, archive_size: dict[str, Any], state: HarvestRoundsState, round_index: int
) -> bool:
    widened_lanes, actions = _coverage_rerun_lanes(
        retriever=runtime.retriever,
        params=runtime.params,
        query_lanes=state.effective_query_lanes,
        lane_diagnostics=state.result.lane_diagnostics,
        actor_discovery=state.result.actor_discovery,
        coverage_gate=state.result.coverage_gate,
    )
    state.rerun_actions.extend(actions)
    plan = _adaptive_harvest_plan(
        params=runtime.params,
        query_lane_count=len(widened_lanes),
        selected_top_k=runtime.selected_top_k,
        total_emails=int(archive_size.get("total_emails") or 0),
        coverage_escalation=True,
    )
    if not _plan_changed(state, widened_lanes, plan):
        return False
    previous_rows, previous_signature = (
        [dict(item) for item in state.result.evidence_bank],
        _coverage_signature(state.result.expanded_metrics),
    )
    result = _evaluate_round(
        runtime, round_index=round_index + 1, query_lanes=list(widened_lanes), plan=plan, prior_rows=previous_rows
    )
    state.rerun_rounds.append(dict(result.quality_gate.pop("round_summary", {})))
    state.expansion_rounds.append({"round": round_index + 1, **dict(result.expansion_diagnostics)})
    state.result, state.effective_query_lanes, state.effective_plan = result, list(widened_lanes), plan
    recovered = state.rerun_rounds[-1].get("recovered_evidence_handles") or []
    return bool(recovered or _coverage_signature(result.expanded_metrics) > previous_signature)


def _plan_changed(state: HarvestRoundsState, lanes: list[str], plan: dict[str, Any]) -> bool:
    return lanes != state.effective_query_lanes or any(
        int(plan[key]) > int(state.effective_plan[key]) for key in ("lane_top_k", "merge_budget", "reserve_per_lane")
    )


def _completed_bundle(
    runtime: HarvestRoundRuntime,
    archive_size: dict[str, Any],
    initial_plan: dict[str, Any],
    query_lanes: list[str],
    state: HarvestRoundsState,
) -> dict[str, Any]:
    expansion = _aggregate_expansion_diagnostics(state.expansion_rounds)
    _apply_expansion_quality(state.result.quality_gate, expansion)
    summary = _completed_summary(runtime, archive_size, initial_plan, query_lanes, state, expansion)
    return {
        "selected_results": state.result.selected_results,
        "promoted_evidence_rows": state.result.evidence_bank,
        "lane_diagnostics": state.result.lane_diagnostics,
        "summary": summary,
    }


def _apply_expansion_quality(quality: dict[str, Any], expansion: dict[str, Any]) -> None:
    if int(expansion.get("error_count") or 0) <= 0:
        return
    reasons = [str(item) for item in list(quality.get("reasons") or []) if str(item).strip()]
    if "archive_expansion_partial" not in reasons:
        reasons.append("archive_expansion_partial")
    quality.update(status="weak", reasons=reasons, expansion_partial=True)


def _completed_summary(
    runtime: HarvestRoundRuntime,
    archive_size: dict[str, Any],
    initial_plan: dict[str, Any],
    query_lanes: list[str],
    state: HarvestRoundsState,
    expansion: dict[str, Any],
) -> dict[str, Any]:
    result, plan, meta = state.result, state.effective_plan, state.result.search_meta
    email_available = _email_archive_available(archive_size, result)
    later_handles = _later_round_handles(state.rerun_rounds)
    return {
        "enabled": True,
        "harvest_run_status": "partial" if int(expansion.get("error_count") or 0) > 0 else "completed",
        "query_lanes": list(query_lanes),
        "effective_query_lanes": state.effective_query_lanes,
        "selected_top_k": runtime.selected_top_k,
        "lane_top_k": int(meta.get("lane_top_k") or plan["lane_top_k"]),
        "merge_budget": int(meta.get("merge_budget") or plan["merge_budget"]),
        "candidate_pool_count": int(meta.get("candidate_pool_count") or 0),
        "selected_result_count": int(meta.get("selected_result_count") or len(result.selected_results)),
        "raw_candidate_count": len(result.evidence_bank),
        "compact_candidate_count": len(result.selected_results),
        "adaptive_breadth": _completed_breadth(archive_size, initial_plan, plan, meta, state),
        "source_basis": _source_basis_summary(params=runtime.params, email_archive_available=email_available),
        "coverage_metrics": result.expanded_metrics,
        "direct_coverage_metrics": result.metrics,
        "expanded_coverage_metrics": result.expanded_metrics,
        "coverage_thresholds": runtime.thresholds,
        "coverage_gate": result.coverage_gate,
        "quality_gate": result.quality_gate,
        "actor_discovery": result.actor_discovery,
        "direct_evidence_count": len(result.direct_rows),
        "expanded_evidence_count": len(result.expanded_rows),
        "mixed_source_candidate_count": len(runtime.mixed_source_rows),
        "rerun_rounds": state.rerun_rounds,
        "later_round_only_evidence_handles": later_handles,
        "expansion_diagnostics": expansion,
        "evidence_bank": result.evidence_bank,
    }


def _email_archive_available(archive_size: dict[str, Any], result: HarvestRoundResult) -> bool:
    return bool(int(archive_size.get("total_emails") or 0) > 0 or result.evidence_bank or result.selected_results)


def _later_round_handles(rerun_rounds: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            handle for item in rerun_rounds[1:] for handle in item.get("recovered_evidence_handles", []) if str(handle).strip()
        )
    )


def _completed_breadth(
    archive_size: dict[str, Any], initial: dict[str, Any], plan: dict[str, Any], meta: dict[str, Any], state: HarvestRoundsState
) -> dict[str, Any]:
    return {
        "total_emails": int(archive_size.get("total_emails") or 0),
        "date_span_days": int(initial["date_span_days"]),
        "initial_lane_top_k": int(initial["lane_top_k"]),
        "initial_merge_budget": int(initial["merge_budget"]),
        "effective_lane_top_k": int(meta.get("lane_top_k") or plan["lane_top_k"]),
        "effective_merge_budget": int(meta.get("merge_budget") or plan["merge_budget"]),
        "coverage_rerun_triggered": len(state.rerun_rounds) > 1,
        "rerun_round_count": max(len(state.rerun_rounds) - 1, 0),
        "rerun_actions": list(dict.fromkeys(state.rerun_actions)),
    }
