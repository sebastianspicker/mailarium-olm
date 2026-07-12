"""Pure stages for archive harvest coverage lanes, metrics, and gates."""

from __future__ import annotations

from typing import Any

from ._utils import _compact
from .case_analysis_harvest_common import _coerce_month_bucket
from .mcp_models import EmailCaseAnalysisInput
from .question_execution_waves import derive_wave_query_lane_specs, get_wave_definition


def coverage_rerun_lanes_stage(
    *,
    retriever: Any,
    params: EmailCaseAnalysisInput,
    query_lanes: list[str],
    lane_diagnostics: list[dict[str, Any]],
    actor_discovery: dict[str, Any],
    coverage_gate: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Build deterministic widened lanes from gate, actor, and zero-result stages."""
    lanes = list(query_lanes)
    actions: list[str] = []
    reasons = {str(item) for item in coverage_gate.get("reasons", []) if _compact(item)}
    wave_specs = _wave_specs(params)
    _append_reason_lanes(lanes, actions, reasons, wave_specs)
    _append_discovered_actor_lanes(lanes, actions, params, actor_discovery)
    _append_zero_result_variants(lanes, actions, retriever, lane_diagnostics)
    return lanes, list(dict.fromkeys(actions))


def _wave_specs(params: EmailCaseAnalysisInput) -> dict[str, str]:
    if not params.wave_id:
        return {}
    return {spec.lane_class: spec.query for spec in derive_wave_query_lane_specs(params, params.wave_id)}


def _append_reason_lanes(lanes: list[str], actions: list[str], reasons: set[str], wave_specs: dict[str, str]) -> None:
    reason_groups = (
        ({"attachment_hits_below_threshold"}, ("attachment_or_record",)),
        ({"unique_months_below_threshold"}, ("temporal_event",)),
        (
            {"unique_senders_below_threshold", "lane_coverage_below_threshold"},
            ("actor_seeded_management", "actor_free_issue_family"),
        ),
        ({"unique_hits_below_threshold", "unique_threads_below_threshold"}, ("counterevidence_or_silence",)),
    )
    for triggers, lane_classes in reason_groups:
        if triggers & reasons:
            _append_lane_classes(lanes, actions, lane_classes, wave_specs)


def _append_lane_classes(lanes: list[str], actions: list[str], lane_classes: tuple[str, ...], wave_specs: dict[str, str]) -> None:
    from .case_analysis_harvest_coverage import _append_unique_lane

    for lane_class in lane_classes:
        lane = str(wave_specs.get(lane_class) or "")
        if lane and _append_unique_lane(lanes, lane):
            actions.append(lane_class)


def _append_discovered_actor_lanes(
    lanes: list[str], actions: list[str], params: EmailCaseAnalysisInput, actor_discovery: dict[str, Any]
) -> None:
    from .case_analysis_harvest_coverage import _append_unique_lane

    issue_terms = list(get_wave_definition(params.wave_id).issue_terms[:2]) if params.wave_id else []
    track_terms = [str(item).strip() for item in params.case_scope.employment_issue_tracks[:2] if str(item).strip()]
    for actor in actor_discovery.get("top_discovered_actors", [])[:2]:
        lane = _actor_lane(actor, issue_terms, track_terms)
        if lane and _append_unique_lane(lanes, lane):
            actions.append("discovered_actor_lane")


def _actor_lane(actor: dict[str, Any], issue_terms: list[str], track_terms: list[str]) -> str:
    identity = _compact(actor.get("sender_name")) or _compact(actor.get("sender_email"))
    return " ".join(bit for bit in [identity, *issue_terms, *track_terms] if bit).strip()


def _append_zero_result_variants(lanes: list[str], actions: list[str], retriever: Any, diagnostics: list[dict[str, Any]]) -> None:
    from .case_analysis_harvest_coverage import _append_unique_lane, _expanded_zero_result_lane_variants

    for item in diagnostics:
        if not isinstance(item, dict) or int(item.get("result_count") or 0) > 0:
            continue
        lane_query = _compact(item.get("query"))
        for variant in _expanded_zero_result_lane_variants(retriever, lane_query)[:2] if lane_query else []:
            if _append_unique_lane(lanes, variant):
                actions.append("zero_result_lane_expansion")


def coverage_metrics_stage(*, evidence_bank: list[dict[str, Any]], lane_diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate stable coverage metrics from independently named projections."""
    handles = {_evidence_handle(item) for item in evidence_bank}
    segments = {_segment_key(item) for item in evidence_bank if _is_segment(item)}
    attachments = {_attachment_key(item) for item in evidence_bank if _is_attachment(item)}
    return {
        "unique_hits": _nonempty_count(handles),
        "unique_messages": _unique_value_count(evidence_bank, _message_key),
        "unique_evidence_handles": _nonempty_count(handles),
        "unique_segments": _nonempty_count(segments),
        "unique_attachments": _nonempty_count(attachments),
        "unique_threads": _unique_value_count(evidence_bank, lambda item: str(item.get("conversation_id") or "").strip()),
        "unique_senders": _unique_value_count(evidence_bank, _sender_key),
        "unique_months": _unique_value_count(evidence_bank, lambda item: _coerce_month_bucket(str(item.get("date") or ""))),
        "attachment_hits": _matching_count(evidence_bank, _is_attachment),
        "thread_expansion_hits": _matching_count(evidence_bank, _is_thread_expansion),
        "attachment_candidate_count": _matching_count(evidence_bank, _is_attachment_candidate),
        "verified_exact_hits": _matching_count(evidence_bank, _is_verified_exact),
        "provenance_complete_hits": _matching_count(evidence_bank, _has_provenance),
        "folders_touched": _unique_value_count(evidence_bank, lambda item: str(item.get("folder") or "").strip()),
        "lane_coverage": len(_lane_hits(evidence_bank)),
        "zero_result_lanes": _zero_result_lanes(lane_diagnostics),
    }


def _unique_value_count(rows: list[dict[str, Any]], resolver: Any) -> int:
    return len({value for item in rows if (value := resolver(item))})


def _matching_count(rows: list[dict[str, Any]], predicate: Any) -> int:
    return sum(1 for item in rows if predicate(item))


def _nonempty_count(values: set[str]) -> int:
    return len({item for item in values if item})


def _message_key(item: dict[str, Any]) -> str:
    return str(item.get("uid") or item.get("source_id") or "").strip()


def _sender_key(item: dict[str, Any]) -> str:
    return str(item.get("sender_email") or item.get("sender_name") or "").strip()


def _evidence_handle(item: dict[str, Any]) -> str:
    return _compact(
        (item.get("provenance") or {}).get("evidence_handle")
        or (item.get("document_locator") or {}).get("evidence_handle")
        or item.get("result_key")
        or item.get("source_id")
        or item.get("uid")
    )


def _is_segment(item: dict[str, Any]) -> bool:
    return (
        str(item.get("score_kind") or "") == "segment_sql"
        or int(item.get("segment_ordinal") or 0) > 0
        or bool(_compact(item.get("segment_type")))
    )


def _segment_key(item: dict[str, Any]) -> str:
    return _compact(item.get("result_key") or item.get("chunk_id") or (item.get("provenance") or {}).get("evidence_handle"))


def _is_attachment(item: dict[str, Any]) -> bool:
    return str(item.get("candidate_kind") or "").strip() == "attachment" or bool(_compact(item.get("attachment_filename")))


def _is_attachment_candidate(item: dict[str, Any]) -> bool:
    return str(item.get("candidate_kind") or "").strip() == "attachment"


def _is_thread_expansion(item: dict[str, Any]) -> bool:
    return str(item.get("harvest_source") or "") == "thread_expansion"


def _attachment_key(item: dict[str, Any]) -> str:
    return _compact(
        item.get("result_key")
        or (item.get("provenance") or {}).get("evidence_handle")
        or f"{item.get('uid') or item.get('source_id') or ''}:{item.get('attachment_filename') or ''}"
    )


def _is_verified_exact(item: dict[str, Any]) -> bool:
    return str(item.get("verification_status") or "").strip() in {
        "retrieval_exact",
        "forensic_exact",
        "hybrid_verified_forensic",
        "segment_exact",
    }


def _has_provenance(item: dict[str, Any]) -> bool:
    return bool(
        _compact((item.get("provenance") or {}).get("evidence_handle"))
        or _compact((item.get("document_locator") or {}).get("evidence_handle"))
    )


def _lane_hits(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(lane_id)
        for item in rows
        for lane_id in item.get("matched_query_lanes", [])
        if str(lane_id).strip().startswith("lane_")
    }


def _zero_result_lanes(rows: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("lane_id") or "") for item in rows if isinstance(item, dict) and int(item.get("result_count") or 0) <= 0]


def coverage_gate_reasons_stage(*, metrics: dict[str, Any], thresholds: dict[str, int]) -> tuple[list[str], list[str]]:
    """Evaluate threshold specifications in stable output order."""
    specifications = (
        (
            "unique_hits",
            "min_unique_hits",
            "unique_hits_below_threshold",
            "Raise harvest breadth and widen actor-plus-issue query lanes.",
        ),
        (
            "unique_threads",
            "min_unique_threads",
            "unique_threads_below_threshold",
            "Expand the strongest hits with thread lookup and similar-message replay.",
        ),
        (
            "unique_senders",
            "min_unique_senders",
            "unique_senders_below_threshold",
            "Add actor-name variants and routing lanes across the archive.",
        ),
        (
            "unique_months",
            "min_unique_months",
            "unique_months_below_threshold",
            "Widen the timeline window or add explicit dated event lanes.",
        ),
        (
            "attachment_hits",
            "min_attachment_hits",
            "attachment_hits_below_threshold",
            "Run attachment-first retrieval and search mixed-source records more aggressively.",
        ),
        (
            "lane_coverage",
            "min_lane_coverage",
            "lane_coverage_below_threshold",
            "Add German orthographic fallback and lower-performing actor or issue lanes.",
        ),
    )
    failed = [spec for spec in specifications if int(metrics.get(spec[0]) or 0) < int(thresholds.get(spec[1]) or 0)]
    return [spec[2] for spec in failed], list(dict.fromkeys(spec[3] for spec in failed))


def coverage_gate_stage(
    *,
    direct_metrics: dict[str, Any],
    expanded_metrics: dict[str, Any],
    thresholds: dict[str, int],
    evidence_bank: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate direct and recovered sufficiency without altering rescue semantics."""
    direct_reasons, direct_recommendations = coverage_gate_reasons_stage(metrics=direct_metrics, thresholds=thresholds)
    recovered_reasons, recovered_recommendations = coverage_gate_reasons_stage(metrics=expanded_metrics, thresholds=thresholds)
    direct_ok, recovered_ok = not direct_reasons, not recovered_reasons
    later_count = sum(1 for item in evidence_bank if int(item.get("harvest_round") or 0) > 0)
    later_rescue = bool(recovered_ok and not direct_ok and later_count > 0)
    return {
        "status": "pass" if recovered_ok else "needs_more_harvest",
        "reasons": [] if recovered_ok else recovered_reasons,
        "recommendations": [] if recovered_ok else recovered_recommendations,
        "direct_sufficiency": direct_ok,
        "recovered_sufficiency": recovered_ok,
        "later_round_rescue": later_rescue,
        "sufficiency_basis": _sufficiency_basis(direct_ok, recovered_ok, later_rescue),
        "later_round_evidence_count": later_count,
        "direct_reasons": direct_reasons,
        "direct_recommendations": direct_recommendations,
        "recovered_reasons": [] if recovered_ok else recovered_reasons,
        "recovered_recommendations": [] if recovered_ok else recovered_recommendations,
    }


def _sufficiency_basis(direct_ok: bool, recovered_ok: bool, later_rescue: bool) -> str:
    if direct_ok:
        return "direct"
    if later_rescue:
        return "later_round_rescue"
    return "recovered" if recovered_ok else "insufficient"
