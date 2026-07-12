"""Runtime orchestration for comparative-treatment analysis."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from .comparative_treatment_matrix import issue_rows, shared_comparator_points_from_summaries


def compare_treatment(
    *, scope: dict[str, Any], candidates: list[dict[str, Any]], full_map: dict[str, Any], target_actor_id: str, helpers: Any
) -> dict[str, Any]:
    """Run comparative-treatment analysis across comparator actors."""
    raw_comparators = scope.get("comparator_actors")
    comparators = (
        [cast(dict[str, Any], item) for item in raw_comparators if isinstance(item, dict)]
        if isinstance(raw_comparators, list)
        else []
    )
    target = scope.get("target_person")
    target_email = str(target.get("email") or "").lower() if isinstance(target, dict) else ""
    discovery = helpers.comparator_discovery_candidates(scope=scope, candidates=candidates, full_map=full_map)
    summaries = [_comparator_summary(item, candidates, full_map, scope, target_email, discovery, helpers) for item in comparators]
    points = shared_comparator_points_from_summaries(summaries)
    return {
        "version": helpers.COMPARATIVE_TREATMENT_VERSION,
        "target_actor_id": target_actor_id,
        "comparator_count": len(summaries),
        "summary": _report_summary(summaries, points, discovery),
        "comparator_discovery_candidates": discovery,
        "comparator_summaries": summaries,
        "comparator_points": points,
    }


def _comparator_summary(comparator, candidates, full_map, scope, target_email, discovery, helpers):
    comparator_email = str(comparator.get("email") or "").lower()
    comparator_id = str(comparator.get("actor_id") or "")
    sender_ids = sorted({str(item.get("sender_actor_id") or "") for item in candidates if str(item.get("sender_actor_id") or "")})
    best = None
    for sender_id in sender_ids:
        current = _sender_summary(sender_id, comparator_id, comparator_email, target_email, candidates, full_map, scope, helpers)
        if current is not None and (best is None or _summary_score(current) > _summary_score(best)):
            best = current
    return best or _empty_summary(comparator_id, comparator_email, discovery, scope, helpers)


def _sender_summary(sender_id, comparator_id, comparator_email, target_email, candidates, full_map, scope, helpers):
    target_rows, comparator_rows = _sender_buckets(sender_id, target_email, comparator_email, candidates, full_map, helpers)
    if not target_rows or not comparator_rows:
        return None
    similarity = helpers.similarity_checks(target_rows, comparator_rows, full_map=full_map)
    target_metrics = helpers.metrics(target_rows, full_map=full_map)
    comparator_metrics = helpers.metrics(comparator_rows, full_map=full_map)
    quality, uncertainty = helpers.comparison_quality(
        similarity, target_metrics=target_metrics, comparator_metrics=comparator_metrics
    )
    signals = _unequal_signals(target_metrics, comparator_metrics)
    evidence = {"target_uids": _uids(target_rows), "comparator_uids": _uids(comparator_rows)}
    summary = {
        "comparator_actor_id": comparator_id,
        "comparator_email": comparator_email,
        "sender_actor_id": sender_id,
        "status": "comparator_available" if quality in {"high", "partial"} else "weak_similarity",
        "comparison_quality": quality,
        "comparison_quality_label": {
            "high": "high_quality_comparator",
            "partial": "partial_comparator",
            "weak": "weak_comparator",
        }[quality],
        "similarity_checks": similarity,
        "target_metrics": target_metrics,
        "comparator_metrics": comparator_metrics,
        "unequal_treatment_signals": signals,
        "supports_discrimination_concern": _supports_discrimination(quality, signals),
        "uncertainty_reasons": uncertainty,
        "evidence_chain": evidence,
    }
    summary["comparator_matrix"] = _matrix(
        comparator_id, quality, signals, target_metrics, comparator_metrics, evidence, scope, helpers
    )
    return summary


def _sender_buckets(sender_id, target_email, comparator_email, candidates, full_map, helpers):
    target_rows, comparator_rows = [], []
    for candidate in candidates:
        if str(candidate.get("sender_actor_id") or "") != sender_id:
            continue
        recipients = helpers.recipient_emails(full_map.get(str(candidate.get("uid") or "")))
        if target_email and target_email in recipients:
            target_rows.append(candidate)
        if comparator_email and comparator_email in recipients:
            comparator_rows.append(candidate)
    return target_rows, comparator_rows


def _unequal_signals(target, comparator):
    metric_signals = (
        ("tone_signal_rate", "tone_to_target_harsher_than_to_comparator"),
        ("escalation_rate", "same_sender_escalates_more_against_target"),
        ("criticism_rate", "same_sender_criticizes_target_more"),
        ("demand_intensity_rate", "same_sender_demands_more_from_target"),
        ("procedural_pressure_rate", "same_sender_uses_more_procedural_pressure_against_target"),
        ("multi_recipient_rate", "same_sender_uses_more_public_visibility_against_target"),
        ("average_visible_recipient_count", "same_sender_uses_broader_visibility_against_target"),
    )
    signals = [signal for metric, signal in metric_signals if float(target[metric]) > float(comparator[metric])]
    if _slower_response(target, comparator):
        signals.append("same_sender_replies_slower_to_target_requests")
    return signals


def _slower_response(target, comparator):
    return (
        int(target["response_delay_observation_count"]) > 0
        and int(comparator["response_delay_observation_count"]) > 0
        and float(target["average_response_delay_hours"]) > float(comparator["average_response_delay_hours"])
    )


def _supports_discrimination(quality, signals):
    material = {
        "tone_to_target_harsher_than_to_comparator",
        "same_sender_criticizes_target_more",
        "same_sender_uses_more_procedural_pressure_against_target",
        "same_sender_uses_more_public_visibility_against_target",
        "same_sender_uses_broader_visibility_against_target",
    }
    return bool(quality == "high" and len(signals) >= 2 and any(signal in material for signal in signals))


def _uids(rows):
    return [str(item.get("uid") or "") for item in rows]


def _matrix(comparator_id, quality, signals, target_metrics, comparator_metrics, evidence, scope, helpers):
    return issue_rows(
        comparator_actor_id=comparator_id,
        comparison_quality=quality,
        unequal_treatment_signals=signals,
        target_metrics=target_metrics,
        comparator_metrics=comparator_metrics,
        evidence_chain=evidence,
        scope=scope,
        scope_text=helpers.scope_text,
        comparator_issue_definitions=helpers.COMPARATOR_ISSUE_DEFINITIONS,
    )


def _summary_score(summary):
    similarity = summary.get("similarity_checks") or {}
    quality = str(summary.get("comparison_quality") or "")
    return (
        int(similarity.get("similarity_score") or 0) * 10
        + {"high": 3, "partial": 2, "weak": 1}.get(quality, 0)
        + len(summary.get("unequal_treatment_signals") or [])
    )


def _empty_summary(comparator_id, comparator_email, discovery, scope, helpers):
    evidence = {"target_uids": [], "comparator_uids": []}
    similarity = dict.fromkeys(
        (
            "shared_request_type",
            "shared_error_type",
            "shared_escalation_context",
            "shared_process_step",
            "shared_workflow_stage",
            "same_sender_decision_path",
            "shared_subject",
            "shared_subject_family",
            "shared_day",
            "shared_day_window",
            "shared_visibility_band",
        ),
        False,
    )
    similarity.update(
        {
            "shared_context_count": 0,
            "shared_subject_families": [],
            "shared_tags": [],
            "shared_workflow_stages": [],
            "shared_visibility_bands": [],
            "similarity_score": 0,
        }
    )
    summary = {
        "comparator_actor_id": comparator_id,
        "comparator_email": comparator_email,
        "status": "no_suitable_comparator",
        "reason": "No same-sender message pair addressed both the target and this comparator in the current evidence set.",
        "comparison_quality": "weak",
        "comparison_quality_label": "no_suitable_comparator",
        "similarity_checks": similarity,
        "target_metrics": {},
        "comparator_metrics": {},
        "unequal_treatment_signals": [],
        "supports_discrimination_concern": False,
        "uncertainty_reasons": ["No same-sender comparator pair could be established from the current evidence set."],
        "evidence_chain": evidence,
        "discovery_candidates": discovery,
    }
    summary["comparator_matrix"] = _matrix(comparator_id, "weak", [], {}, {}, evidence, scope, helpers)
    return summary


def _report_summary(summaries, points, discovery):
    statuses = Counter(str(item.get("status") or "") for item in summaries)
    qualities = Counter(str(item.get("comparison_quality") or "") for item in summaries)
    strengths = Counter(str(item.get("comparison_strength") or "") for item in points)
    return {
        "status_counts": dict(sorted(statuses.items())),
        "available_comparator_count": statuses["comparator_available"],
        "high_quality_comparator_count": qualities["high"],
        "partial_quality_comparator_count": qualities["partial"],
        "weak_quality_comparator_count": qualities["weak"],
        "low_quality_comparator_count": qualities["weak"],
        "no_suitable_comparator_count": statuses["no_suitable_comparator"],
        "discrimination_supporting_comparator_count": sum(
            bool(item.get("supports_discrimination_concern")) for item in summaries
        ),
        "matrix_row_count": sum(int(((item.get("comparator_matrix") or {}).get("row_count")) or 0) for item in summaries),
        "strong_matrix_row_count": strengths["strong"],
        "moderate_matrix_row_count": strengths["moderate"],
        "weak_matrix_row_count": strengths["weak"],
        "not_comparable_matrix_row_count": strengths["not_comparable"],
        "discovery_candidate_count": len(discovery),
    }
