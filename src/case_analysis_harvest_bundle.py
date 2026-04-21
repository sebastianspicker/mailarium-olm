# mypy: disable-error-code=name-defined
"""Split archive-harvest helpers (case_analysis_harvest_bundle)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any, cast

from .case_analysis_scope import derive_case_analysis_query
from .case_operator_intake import ingest_chat_exports
from .matter_file_ingestion import enrich_matter_manifest, infer_matter_manifest_authorized_roots
from .mcp_models import EmailAnswerContextInput, EmailCaseAnalysisInput
from .multi_source_case_bundle import build_standalone_mixed_source_bundle, promotable_mixed_source_evidence_rows
from .question_execution_waves import derive_wave_query_lane_specs, get_wave_definition

if TYPE_CHECKING:
    from .tools.utils import ToolDepsProto

# ruff: noqa: F401,F821


async def build_archive_harvest_bundle(
    deps: ToolDepsProto,
    params: EmailCaseAnalysisInput,
    *,
    query_lanes: list[str],
    selected_top_k: int,
) -> dict[str, Any]:
    """Run a wider archive-harvest pass before compact wave synthesis."""
    from .config import get_settings
    from .tools import search_answer_context_impl as impl
    from .tools.search_answer_context_runtime import _search_across_query_lanes

    get_retriever = getattr(deps, "get_retriever", None)
    retriever = get_retriever() if callable(get_retriever) else None
    get_email_db = getattr(deps, "get_email_db", None)
    email_db = get_email_db() if callable(get_email_db) else None
    mixed_source_bundle, _normalized_chat_log_entries = _mixed_source_harvest_inputs(params)
    full_mixed_source_rows = promotable_mixed_source_evidence_rows(mixed_source_bundle)
    if retriever is None or not hasattr(retriever, "search_filtered"):
        adaptive_plan = _adaptive_harvest_plan(
            params=params,
            query_lane_count=len(query_lanes),
            selected_top_k=selected_top_k,
            total_emails=0,
            coverage_escalation=False,
        )
        mixed_source_rows = [
            {**dict(row), "harvest_round": int(row.get("harvest_round") or 0)}
            for row in full_mixed_source_rows[: int(adaptive_plan["merge_budget"])]
        ]
        metrics = _coverage_metrics(evidence_bank=mixed_source_rows, lane_diagnostics=[])
        expansion_diagnostics = _aggregate_expansion_diagnostics([])
        summary = {
            "enabled": False,
            "harvest_run_status": "completed",
            "query_lanes": list(query_lanes),
            "effective_query_lanes": list(query_lanes),
            "selected_top_k": selected_top_k,
            "lane_top_k": 0,
            "merge_budget": 0,
            "candidate_pool_count": 0,
            "selected_result_count": 0,
            "raw_candidate_count": len(mixed_source_rows),
            "compact_candidate_count": 0,
            "adaptive_breadth": {
                "total_emails": adaptive_plan["total_emails"],
                "date_span_days": adaptive_plan["date_span_days"],
                "initial_lane_top_k": adaptive_plan["lane_top_k"],
                "initial_merge_budget": adaptive_plan["merge_budget"],
                "effective_lane_top_k": 0,
                "effective_merge_budget": 0,
                "coverage_rerun_triggered": False,
                "rerun_round_count": 0,
                "rerun_actions": [],
            },
            "source_basis": _source_basis_summary(params=params, email_archive_available=False),
            "coverage_metrics": metrics,
            "direct_coverage_metrics": metrics,
            "expanded_coverage_metrics": metrics,
            "coverage_thresholds": _coverage_thresholds(
                params=params,
                query_lane_count=len(query_lanes),
                selected_top_k=selected_top_k,
            ),
            "coverage_gate": {"status": "needs_more_harvest", "reasons": ["archive_unavailable"], "recommendations": []},
            "quality_gate": {"status": "weak", "score": 0.0, "reasons": ["archive_unavailable"]},
            "actor_discovery": {"discovered_actor_count": 0, "roles": {}, "top_discovered_actors": []},
            "direct_evidence_count": len(mixed_source_rows),
            "expanded_evidence_count": 0,
            "mixed_source_candidate_count": len(full_mixed_source_rows),
            "rerun_rounds": [],
            "later_round_only_evidence_handles": [],
            "expansion_diagnostics": expansion_diagnostics,
            "evidence_bank": mixed_source_rows,
        }
        return {
            "selected_results": [],
            "lane_diagnostics": [],
            "promoted_evidence_rows": mixed_source_rows,
            "summary": summary,
        }

    settings = get_settings()
    archive_query = derive_case_analysis_query(params)
    answer_params = EmailAnswerContextInput(
        question=archive_query,
        max_results=selected_top_k,
        evidence_mode=params.evidence_mode,
        case_scope=params.case_scope,
        query_lanes=query_lanes,
        scan_id=params.scan_id,
    )
    search_kwargs = impl._answer_context_search_kwargs(answer_params, min(selected_top_k, settings.mcp_max_search_results))
    archive_size = _archive_size_hint(retriever)
    initial_plan = _adaptive_harvest_plan(
        params=params,
        query_lane_count=len(query_lanes),
        selected_top_k=selected_top_k,
        total_emails=int(archive_size.get("total_emails") or 0),
        coverage_escalation=False,
    )

    def _evaluate_round(
        *,
        round_index: int,
        round_query_lanes: list[str],
        round_plan: dict[str, Any],
        prior_rows: list[dict[str, Any]],
    ) -> tuple[
        list[Any],
        list[dict[str, Any]],
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]:
        selected_round_results, round_lane_diagnostics, round_search_meta = _search_across_query_lanes(
            retriever=retriever,
            search_kwargs=search_kwargs,
            query_lanes=round_query_lanes,
            top_k=selected_top_k,
            scan_id=params.scan_id,
            lane_top_k=int(round_plan["lane_top_k"]),
            reserve_per_lane=int(round_plan["reserve_per_lane"]),
            bank_limit=int(round_plan["merge_budget"]),
        )
        search_bank, expansion_diagnostics = _enrich_evidence_bank(
            db=email_db,
            answer_params=answer_params,
            bank_entries=[
                {**dict(item), "harvest_round": round_index}
                for item in round_search_meta.get("evidence_bank", [])
                if isinstance(item, dict)
            ],
            bank_results=list(round_search_meta.get("evidence_results", [])),
            exhaustive_review=params.review_mode == "exhaustive_matter_review",
        )
        search_bank = _annotate_round(search_bank, prior_rows=prior_rows, round_index=round_index)
        combined_bank = _dedupe_evidence_rows(
            [
                *search_bank,
                *[
                    {**dict(row), "harvest_round": int(row.get("harvest_round") or 0)}
                    for row in full_mixed_source_rows[: int(round_plan["merge_budget"])]
                ],
            ]
        )
        direct_rows, expanded_rows = _split_evidence_bank_layers(combined_bank)
        round_metrics = _coverage_metrics(evidence_bank=direct_rows, lane_diagnostics=round_lane_diagnostics)
        round_expanded_metrics = _coverage_metrics(evidence_bank=combined_bank, lane_diagnostics=round_lane_diagnostics)
        round_coverage_gate = _coverage_gate(
            direct_metrics=round_metrics,
            expanded_metrics=round_expanded_metrics,
            thresholds=thresholds,
            evidence_bank=combined_bank,
        )
        round_actor_discovery = _actor_discovery_summary(evidence_bank=combined_bank, params=params)
        round_quality_gate = _harvest_quality_summary(
            evidence_bank=combined_bank,
            metrics=round_expanded_metrics,
            actor_discovery=round_actor_discovery,
        )
        recovered_keys = _round_recovered_keys(combined_bank, prior_rows)
        round_summary = {
            "round": round_index,
            "query_lane_count": len(round_query_lanes),
            "lane_top_k": int(round_search_meta.get("lane_top_k") or round_plan["lane_top_k"]),
            "merge_budget": int(round_search_meta.get("merge_budget") or round_plan["merge_budget"]),
            "coverage_status": str(round_coverage_gate.get("status") or ""),
            "recovered_count": len(recovered_keys),
            "recovered_evidence_handles": recovered_keys[:12],
            "mixed_source_candidate_count": len(full_mixed_source_rows),
            "expansion_status": str(expansion_diagnostics.get("status") or "ok"),
            "expansion_error_count": int(expansion_diagnostics.get("error_count") or 0),
        }
        if int(expansion_diagnostics.get("error_count") or 0) > 0:
            round_summary["expansion_errors"] = {
                "thread_expansion": {
                    "error_count": int((expansion_diagnostics.get("thread_expansion") or {}).get("error_count") or 0),
                    "errors": [
                        item
                        for item in list((expansion_diagnostics.get("thread_expansion") or {}).get("errors") or [])[
                            :_EXPANSION_ERROR_SAMPLE_LIMIT
                        ]
                        if isinstance(item, dict)
                    ],
                },
                "attachment_expansion": {
                    "error_count": int((expansion_diagnostics.get("attachment_expansion") or {}).get("error_count") or 0),
                    "errors": [
                        item
                        for item in list((expansion_diagnostics.get("attachment_expansion") or {}).get("errors") or [])[
                            :_EXPANSION_ERROR_SAMPLE_LIMIT
                        ]
                        if isinstance(item, dict)
                    ],
                },
            }
        return (
            selected_round_results,
            round_lane_diagnostics,
            round_search_meta,
            combined_bank,
            direct_rows,
            expanded_rows,
            round_metrics,
            round_expanded_metrics,
            round_coverage_gate,
            round_actor_discovery,
            {**round_quality_gate, "round_summary": round_summary},
            expansion_diagnostics,
        )

    thresholds = _coverage_thresholds(
        params=params,
        query_lane_count=len(query_lanes),
        selected_top_k=selected_top_k,
    )

    (
        selected_results,
        lane_diagnostics,
        effective_search_meta,
        evidence_bank,
        direct_evidence_bank,
        expanded_rows,
        metrics,
        expanded_metrics,
        coverage_gate,
        actor_discovery,
        quality_gate,
        expansion_diagnostics,
    ) = _evaluate_round(
        round_index=0,
        round_query_lanes=list(query_lanes),
        round_plan=initial_plan,
        prior_rows=[],
    )
    effective_plan = dict(initial_plan)
    effective_query_lanes = list(query_lanes)
    rerun_actions: list[str] = []
    rerun_rounds = [dict(quality_gate.pop("round_summary", {}))]
    expansion_rounds = [{"round": 0, **dict(expansion_diagnostics)}]
    max_rounds = 3
    round_index = 0
    while coverage_gate["status"] == "needs_more_harvest" and round_index + 1 < max_rounds:
        widened_query_lanes, round_actions = _coverage_rerun_lanes(
            retriever=retriever,
            params=params,
            query_lanes=effective_query_lanes,
            lane_diagnostics=lane_diagnostics,
            actor_discovery=actor_discovery,
            coverage_gate=coverage_gate,
        )
        rerun_actions.extend(round_actions)
        widened_plan = _adaptive_harvest_plan(
            params=params,
            query_lane_count=len(widened_query_lanes),
            selected_top_k=selected_top_k,
            total_emails=int(archive_size.get("total_emails") or 0),
            coverage_escalation=True,
        )
        plan_changed = widened_query_lanes != effective_query_lanes or any(
            int(widened_plan[key]) > int(effective_plan[key]) for key in ("lane_top_k", "merge_budget", "reserve_per_lane")
        )
        if not plan_changed:
            break
        previous_rows = [dict(item) for item in evidence_bank]
        previous_signature = _coverage_signature(expanded_metrics)
        (
            selected_results,
            lane_diagnostics,
            effective_search_meta,
            evidence_bank,
            direct_evidence_bank,
            expanded_rows,
            metrics,
            expanded_metrics,
            coverage_gate,
            actor_discovery,
            quality_gate,
            expansion_diagnostics,
        ) = _evaluate_round(
            round_index=round_index + 1,
            round_query_lanes=list(widened_query_lanes),
            round_plan=widened_plan,
            prior_rows=previous_rows,
        )
        rerun_rounds.append(dict(quality_gate.pop("round_summary", {})))
        expansion_rounds.append({"round": round_index + 1, **dict(expansion_diagnostics)})
        effective_query_lanes = list(widened_query_lanes)
        effective_plan = widened_plan
        round_index += 1
        current_signature = _coverage_signature(expanded_metrics)
        latest_recovered = rerun_rounds[-1].get("recovered_evidence_handles") or []
        if not latest_recovered and current_signature <= previous_signature:
            break
    email_archive_available = bool(int(archive_size.get("total_emails") or 0) > 0 or evidence_bank or selected_results)
    later_round_only_evidence_handles = list(
        dict.fromkeys(
            handle
            for round_summary in rerun_rounds[1:]
            for handle in round_summary.get("recovered_evidence_handles", [])
            if str(handle).strip()
        )
    )
    expansion_diagnostics_summary = _aggregate_expansion_diagnostics(expansion_rounds)
    if int(expansion_diagnostics_summary.get("error_count") or 0) > 0:
        quality_reasons = [str(item) for item in list(quality_gate.get("reasons") or []) if str(item).strip()]
        if "archive_expansion_partial" not in quality_reasons:
            quality_reasons.append("archive_expansion_partial")
        quality_gate = {
            **dict(quality_gate),
            "status": "weak",
            "reasons": quality_reasons,
            "expansion_partial": True,
        }
    summary = {
        "enabled": True,
        "harvest_run_status": "partial" if int(expansion_diagnostics_summary.get("error_count") or 0) > 0 else "completed",
        "query_lanes": list(query_lanes),
        "effective_query_lanes": effective_query_lanes,
        "selected_top_k": selected_top_k,
        "lane_top_k": int(effective_search_meta.get("lane_top_k") or effective_plan["lane_top_k"]),
        "merge_budget": int(effective_search_meta.get("merge_budget") or effective_plan["merge_budget"]),
        "candidate_pool_count": int(effective_search_meta.get("candidate_pool_count") or 0),
        "selected_result_count": int(effective_search_meta.get("selected_result_count") or len(selected_results)),
        "raw_candidate_count": len(evidence_bank),
        "compact_candidate_count": len(selected_results),
        "adaptive_breadth": {
            "total_emails": int(archive_size.get("total_emails") or 0),
            "date_span_days": int(initial_plan["date_span_days"]),
            "initial_lane_top_k": int(initial_plan["lane_top_k"]),
            "initial_merge_budget": int(initial_plan["merge_budget"]),
            "effective_lane_top_k": int(effective_search_meta.get("lane_top_k") or effective_plan["lane_top_k"]),
            "effective_merge_budget": int(effective_search_meta.get("merge_budget") or effective_plan["merge_budget"]),
            "coverage_rerun_triggered": len(rerun_rounds) > 1,
            "rerun_round_count": max(len(rerun_rounds) - 1, 0),
            "rerun_actions": list(dict.fromkeys(rerun_actions)),
        },
        "source_basis": _source_basis_summary(params=params, email_archive_available=email_archive_available),
        "coverage_metrics": expanded_metrics,
        "direct_coverage_metrics": metrics,
        "expanded_coverage_metrics": expanded_metrics,
        "coverage_thresholds": thresholds,
        "coverage_gate": coverage_gate,
        "quality_gate": quality_gate,
        "actor_discovery": actor_discovery,
        "direct_evidence_count": len(direct_evidence_bank),
        "expanded_evidence_count": len(expanded_rows),
        "mixed_source_candidate_count": len(full_mixed_source_rows),
        "rerun_rounds": rerun_rounds,
        "later_round_only_evidence_handles": later_round_only_evidence_handles,
        "expansion_diagnostics": expansion_diagnostics_summary,
        "evidence_bank": evidence_bank,
    }
    return {
        "selected_results": selected_results,
        "promoted_evidence_rows": evidence_bank,
        "lane_diagnostics": lane_diagnostics,
        "summary": summary,
    }


__all__ = [
    "build_archive_harvest_bundle",
]
