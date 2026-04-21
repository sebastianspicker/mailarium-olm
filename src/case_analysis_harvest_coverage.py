# mypy: disable-error-code=name-defined
"""Split archive-harvest helpers (case_analysis_harvest_coverage)."""

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


def _append_unique_lane(lanes: list[str], lane: str) -> bool:
    compact = _compact(lane)[:500]
    if not compact:
        return False
    lowered = compact.casefold()
    if any(_compact(existing).casefold() == lowered for existing in lanes):
        return False
    lanes.append(compact)
    return True


def _expanded_zero_result_lane_variants(retriever: Any, lane_query: str) -> list[str]:
    expand_query_lanes = getattr(retriever, "_expand_query_lanes", None)
    if not callable(expand_query_lanes):
        return []
    try:
        variants = expand_query_lanes(lane_query, max_lanes=3)
    except TypeError:
        try:
            variants = expand_query_lanes(lane_query)
        except Exception:
            return []
    except Exception:
        return []
    if not isinstance(variants, list):
        return []
    return [
        _compact(item) for item in variants if _compact(item) and _compact(item).casefold() != _compact(lane_query).casefold()
    ]


def _coverage_rerun_lanes(
    *,
    retriever: Any,
    params: EmailCaseAnalysisInput,
    query_lanes: list[str],
    lane_diagnostics: list[dict[str, Any]],
    actor_discovery: dict[str, Any],
    coverage_gate: dict[str, Any],
) -> tuple[list[str], list[str]]:
    widened_query_lanes = list(query_lanes)
    rerun_actions: list[str] = []
    reasons = {str(item) for item in coverage_gate.get("reasons", []) if _compact(item)}
    wave_specs = {}
    if params.wave_id:
        wave_specs = {spec.lane_class: spec.query for spec in derive_wave_query_lane_specs(params, params.wave_id)}

    if "attachment_hits_below_threshold" in reasons:
        lane = str(wave_specs.get("attachment_or_record") or "")
        if lane and _append_unique_lane(widened_query_lanes, lane):
            rerun_actions.append("attachment_or_record_lane")
    if "unique_months_below_threshold" in reasons:
        lane = str(wave_specs.get("temporal_event") or "")
        if lane and _append_unique_lane(widened_query_lanes, lane):
            rerun_actions.append("temporal_event_lane")
    if {"unique_senders_below_threshold", "lane_coverage_below_threshold"} & reasons:
        for lane_class in ("actor_seeded_management", "actor_free_issue_family"):
            lane = str(wave_specs.get(lane_class) or "")
            if lane and _append_unique_lane(widened_query_lanes, lane):
                rerun_actions.append(lane_class)
    if {"unique_hits_below_threshold", "unique_threads_below_threshold"} & reasons:
        lane = str(wave_specs.get("counterevidence_or_silence") or "")
        if lane and _append_unique_lane(widened_query_lanes, lane):
            rerun_actions.append("counterevidence_or_silence")

    discovered_issue_terms = list(get_wave_definition(params.wave_id).issue_terms[:2]) if params.wave_id else []
    discovered_track_terms = [str(item).strip() for item in params.case_scope.employment_issue_tracks[:2] if str(item).strip()]
    for actor in actor_discovery.get("top_discovered_actors", [])[:2]:
        sender_name = _compact(actor.get("sender_name"))
        sender_email = _compact(actor.get("sender_email"))
        lane = " ".join(
            bit for bit in [sender_name or sender_email, *discovered_issue_terms, *discovered_track_terms] if bit
        ).strip()
        if lane and _append_unique_lane(widened_query_lanes, lane):
            rerun_actions.append("discovered_actor_lane")

    for item in lane_diagnostics:
        if not isinstance(item, dict) or int(item.get("result_count") or 0) > 0:
            continue
        lane_query = _compact(item.get("query"))
        if not lane_query:
            continue
        for variant in _expanded_zero_result_lane_variants(retriever, lane_query)[:2]:
            if _append_unique_lane(widened_query_lanes, variant):
                rerun_actions.append("zero_result_lane_expansion")

    return widened_query_lanes, list(dict.fromkeys(rerun_actions))


def _coverage_thresholds(
    *,
    params: EmailCaseAnalysisInput,
    query_lane_count: int,
    selected_top_k: int,
) -> dict[str, int]:
    span_days = _date_span_days(params)
    min_unique_months = 1
    if span_days > 120:
        min_unique_months = 3
    elif span_days > 45:
        min_unique_months = 2
    min_attachment_hits = 0
    if params.wave_id:
        definition = get_wave_definition(params.wave_id)
        if definition.attachment_terms and params.source_scope != "emails_only":
            min_attachment_hits = 1
    return {
        "min_unique_hits": max(selected_top_k, query_lane_count * 2),
        "min_unique_threads": 3 if selected_top_k >= 8 else 2,
        "min_unique_senders": 3 if selected_top_k >= 8 else 2,
        "min_unique_months": min_unique_months,
        "min_attachment_hits": min_attachment_hits,
        "min_lane_coverage": min(query_lane_count, 3) if query_lane_count else 0,
    }


def _coverage_metrics(
    *,
    evidence_bank: list[dict[str, Any]],
    lane_diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    unique_messages = {
        str(item.get("uid") or item.get("source_id") or "").strip()
        for item in evidence_bank
        if str(item.get("uid") or item.get("source_id") or "").strip()
    }
    unique_evidence_handles = {
        _compact(
            (item.get("provenance") or {}).get("evidence_handle")
            or (item.get("document_locator") or {}).get("evidence_handle")
            or item.get("result_key")
            or item.get("source_id")
            or item.get("uid")
        )
        for item in evidence_bank
    }
    unique_threads = {str(item.get("conversation_id") or "").strip() for item in evidence_bank}
    unique_senders = {
        str(item.get("sender_email") or item.get("sender_name") or "").strip()
        for item in evidence_bank
        if str(item.get("sender_email") or item.get("sender_name") or "").strip()
    }
    unique_months = {bucket for bucket in (_coerce_month_bucket(str(item.get("date") or "")) for item in evidence_bank) if bucket}
    folders = {str(item.get("folder") or "").strip() for item in evidence_bank if str(item.get("folder") or "").strip()}
    lane_hits = {
        str(lane_id)
        for item in evidence_bank
        for lane_id in item.get("matched_query_lanes", [])
        if str(lane_id).strip().startswith("lane_")
    }
    unique_segments = {
        _compact(item.get("result_key") or item.get("chunk_id") or (item.get("provenance") or {}).get("evidence_handle"))
        for item in evidence_bank
        if str(item.get("score_kind") or "") == "segment_sql"
        or int(item.get("segment_ordinal") or 0) > 0
        or _compact(item.get("segment_type"))
    }
    unique_attachments = {
        _compact(
            item.get("result_key")
            or (item.get("provenance") or {}).get("evidence_handle")
            or f"{item.get('uid') or item.get('source_id') or ''}:{item.get('attachment_filename') or ''}"
        )
        for item in evidence_bank
        if str(item.get("candidate_kind") or "").strip() == "attachment" or _compact(item.get("attachment_filename"))
    }
    zero_result_lanes = [
        str(item.get("lane_id") or "")
        for item in lane_diagnostics
        if isinstance(item, dict) and int(item.get("result_count") or 0) <= 0
    ]
    return {
        "unique_hits": len({item for item in unique_evidence_handles if item}),
        "unique_messages": len(unique_messages),
        "unique_evidence_handles": len({item for item in unique_evidence_handles if item}),
        "unique_segments": len({item for item in unique_segments if item}),
        "unique_attachments": len({item for item in unique_attachments if item}),
        "unique_threads": len({item for item in unique_threads if item}),
        "unique_senders": len(unique_senders),
        "unique_months": len(unique_months),
        "attachment_hits": sum(
            1
            for item in evidence_bank
            if str(item.get("candidate_kind") or "").strip() == "attachment" or _compact(item.get("attachment_filename"))
        ),
        "thread_expansion_hits": sum(1 for item in evidence_bank if str(item.get("harvest_source") or "") == "thread_expansion"),
        "attachment_candidate_count": sum(
            1 for item in evidence_bank if str(item.get("candidate_kind") or "").strip() == "attachment"
        ),
        "verified_exact_hits": sum(
            1
            for item in evidence_bank
            if str(item.get("verification_status") or "").strip()
            in {"retrieval_exact", "forensic_exact", "hybrid_verified_forensic", "segment_exact"}
        ),
        "provenance_complete_hits": sum(
            1
            for item in evidence_bank
            if _compact((item.get("provenance") or {}).get("evidence_handle"))
            or _compact((item.get("document_locator") or {}).get("evidence_handle"))
        ),
        "folders_touched": len(folders),
        "lane_coverage": len(lane_hits),
        "zero_result_lanes": zero_result_lanes,
    }


def _split_evidence_bank_layers(evidence_bank: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    direct_rows: list[dict[str, Any]] = []
    expanded_rows: list[dict[str, Any]] = []
    for row in evidence_bank:
        if str(row.get("harvest_source") or "") in {"thread_expansion", "attachment_expansion"}:
            expanded_rows.append(row)
        else:
            direct_rows.append(row)
    return direct_rows, expanded_rows


def _coverage_gate_reasons(*, metrics: dict[str, Any], thresholds: dict[str, int]) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    recommendations: list[str] = []
    if int(metrics.get("unique_hits") or 0) < int(thresholds.get("min_unique_hits") or 0):
        reasons.append("unique_hits_below_threshold")
        recommendations.append("Raise harvest breadth and widen actor-plus-issue query lanes.")
    if int(metrics.get("unique_threads") or 0) < int(thresholds.get("min_unique_threads") or 0):
        reasons.append("unique_threads_below_threshold")
        recommendations.append("Expand the strongest hits with thread lookup and similar-message replay.")
    if int(metrics.get("unique_senders") or 0) < int(thresholds.get("min_unique_senders") or 0):
        reasons.append("unique_senders_below_threshold")
        recommendations.append("Add actor-name variants and routing lanes across the archive.")
    if int(metrics.get("unique_months") or 0) < int(thresholds.get("min_unique_months") or 0):
        reasons.append("unique_months_below_threshold")
        recommendations.append("Widen the timeline window or add explicit dated event lanes.")
    if int(metrics.get("attachment_hits") or 0) < int(thresholds.get("min_attachment_hits") or 0):
        reasons.append("attachment_hits_below_threshold")
        recommendations.append("Run attachment-first retrieval and search mixed-source records more aggressively.")
    if int(metrics.get("lane_coverage") or 0) < int(thresholds.get("min_lane_coverage") or 0):
        reasons.append("lane_coverage_below_threshold")
        recommendations.append("Add German orthographic fallback and lower-performing actor or issue lanes.")
    deduped_recommendations: list[str] = []
    seen: set[str] = set()
    for item in recommendations:
        if item not in seen:
            seen.add(item)
            deduped_recommendations.append(item)
    return reasons, deduped_recommendations


def _coverage_gate(
    *,
    direct_metrics: dict[str, Any],
    expanded_metrics: dict[str, Any],
    thresholds: dict[str, int],
    evidence_bank: list[dict[str, Any]],
) -> dict[str, Any]:
    direct_reasons, direct_recommendations = _coverage_gate_reasons(metrics=direct_metrics, thresholds=thresholds)
    recovered_reasons, recovered_recommendations = _coverage_gate_reasons(metrics=expanded_metrics, thresholds=thresholds)
    direct_sufficiency = not direct_reasons
    recovered_sufficiency = not recovered_reasons
    later_round_evidence_count = sum(1 for item in evidence_bank if int(item.get("harvest_round") or 0) > 0)
    later_round_rescue = bool(recovered_sufficiency and not direct_sufficiency and later_round_evidence_count > 0)
    sufficiency_basis = "insufficient"
    if direct_sufficiency:
        sufficiency_basis = "direct"
    elif later_round_rescue:
        sufficiency_basis = "later_round_rescue"
    elif recovered_sufficiency:
        sufficiency_basis = "recovered"
    return {
        "status": "pass" if recovered_sufficiency else "needs_more_harvest",
        "reasons": [] if recovered_sufficiency else recovered_reasons,
        "recommendations": [] if recovered_sufficiency else recovered_recommendations,
        "direct_sufficiency": direct_sufficiency,
        "recovered_sufficiency": recovered_sufficiency,
        "later_round_rescue": later_round_rescue,
        "sufficiency_basis": sufficiency_basis,
        "later_round_evidence_count": later_round_evidence_count,
        "direct_reasons": direct_reasons,
        "direct_recommendations": direct_recommendations,
        "recovered_reasons": [] if recovered_sufficiency else recovered_reasons,
        "recovered_recommendations": [] if recovered_sufficiency else recovered_recommendations,
    }


__all__ = [
    "_append_unique_lane",
    "_coverage_gate",
    "_coverage_gate_reasons",
    "_coverage_metrics",
    "_coverage_rerun_lanes",
    "_coverage_thresholds",
    "_expanded_zero_result_lane_variants",
    "_split_evidence_bank_layers",
]
