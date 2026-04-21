"""Runtime orchestration for comparative-treatment analysis."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast

from .comparative_treatment_matrix import issue_rows, shared_comparator_points_from_summaries


def compare_treatment(
    *, scope: dict[str, Any], candidates: list[dict[str, Any]], full_map: dict[str, Any], target_actor_id: str, helpers: Any
) -> dict[str, Any]:
    raw_comparators = scope.get("comparator_actors")
    comparators: list[dict[str, Any]] = (
        [cast(dict[str, Any], item) for item in raw_comparators if isinstance(item, dict)]
        if isinstance(raw_comparators, list)
        else []
    )
    target = scope.get("target_person")
    target_email = str(target.get("email") or "").lower() if isinstance(target, dict) else ""
    discovery_candidates = helpers.comparator_discovery_candidates(scope=scope, candidates=candidates, full_map=full_map)
    comparator_summaries: list[dict[str, Any]] = []
    for comparator in comparators:
        if not isinstance(comparator, dict):
            continue
        comparator_email = str(comparator.get("email") or "").lower()
        comparator_actor_id = str(comparator.get("actor_id") or "")
        sender_ids = sorted(
            {
                str(candidate.get("sender_actor_id") or "")
                for candidate in candidates
                if str(candidate.get("sender_actor_id") or "")
            }
        )
        best_summary: dict[str, Any] | None = None
        for sender_actor_id in sender_ids:
            target_candidates = []
            comparator_candidates = []
            for candidate in candidates:
                if str(candidate.get("sender_actor_id") or "") != sender_actor_id:
                    continue
                uid = str(candidate.get("uid") or "")
                recipients = helpers.recipient_emails(full_map.get(uid))
                if target_email and target_email in recipients:
                    target_candidates.append(candidate)
                if comparator_email and comparator_email in recipients:
                    comparator_candidates.append(candidate)
            if not target_candidates or not comparator_candidates:
                continue
            similarity = helpers.similarity_checks(target_candidates, comparator_candidates, full_map=full_map)
            target_metrics = helpers.metrics(target_candidates, full_map=full_map)
            comparator_metrics = helpers.metrics(comparator_candidates, full_map=full_map)
            current_quality, uncertainty_reasons = helpers.comparison_quality(
                similarity,
                target_metrics=target_metrics,
                comparator_metrics=comparator_metrics,
            )
            unequal_treatment_signals = []
            if float(target_metrics["tone_signal_rate"]) > float(comparator_metrics["tone_signal_rate"]):
                unequal_treatment_signals.append("tone_to_target_harsher_than_to_comparator")
            if float(target_metrics["escalation_rate"]) > float(comparator_metrics["escalation_rate"]):
                unequal_treatment_signals.append("same_sender_escalates_more_against_target")
            if float(target_metrics["criticism_rate"]) > float(comparator_metrics["criticism_rate"]):
                unequal_treatment_signals.append("same_sender_criticizes_target_more")
            if float(target_metrics["demand_intensity_rate"]) > float(comparator_metrics["demand_intensity_rate"]):
                unequal_treatment_signals.append("same_sender_demands_more_from_target")
            if float(target_metrics["procedural_pressure_rate"]) > float(comparator_metrics["procedural_pressure_rate"]):
                unequal_treatment_signals.append("same_sender_uses_more_procedural_pressure_against_target")
            if float(target_metrics["multi_recipient_rate"]) > float(comparator_metrics["multi_recipient_rate"]):
                unequal_treatment_signals.append("same_sender_uses_more_public_visibility_against_target")
            if float(target_metrics["average_visible_recipient_count"]) > float(
                comparator_metrics["average_visible_recipient_count"]
            ):
                unequal_treatment_signals.append("same_sender_uses_broader_visibility_against_target")
            if (
                int(target_metrics["response_delay_observation_count"]) > 0
                and int(comparator_metrics["response_delay_observation_count"]) > 0
                and float(target_metrics["average_response_delay_hours"])
                > float(comparator_metrics["average_response_delay_hours"])
            ):
                unequal_treatment_signals.append("same_sender_replies_slower_to_target_requests")
            supports_discrimination_concern = bool(
                current_quality == "high"
                and len(unequal_treatment_signals) >= 2
                and any(
                    signal
                    in {
                        "tone_to_target_harsher_than_to_comparator",
                        "same_sender_criticizes_target_more",
                        "same_sender_uses_more_procedural_pressure_against_target",
                        "same_sender_uses_more_public_visibility_against_target",
                        "same_sender_uses_broader_visibility_against_target",
                    }
                    for signal in unequal_treatment_signals
                )
            )
            status = "comparator_available" if current_quality in {"high", "partial"} else "weak_similarity"
            summary = {
                "comparator_actor_id": comparator_actor_id,
                "comparator_email": comparator_email,
                "sender_actor_id": sender_actor_id,
                "status": status,
                "comparison_quality": current_quality,
                "comparison_quality_label": {
                    "high": "high_quality_comparator",
                    "partial": "partial_comparator",
                    "weak": "weak_comparator",
                }[current_quality],
                "similarity_checks": similarity,
                "target_metrics": target_metrics,
                "comparator_metrics": comparator_metrics,
                "unequal_treatment_signals": unequal_treatment_signals,
                "supports_discrimination_concern": supports_discrimination_concern,
                "uncertainty_reasons": uncertainty_reasons,
                "evidence_chain": {
                    "target_uids": [str(candidate.get("uid") or "") for candidate in target_candidates],
                    "comparator_uids": [str(candidate.get("uid") or "") for candidate in comparator_candidates],
                },
            }
            summary["comparator_matrix"] = issue_rows(
                comparator_actor_id=comparator_actor_id,
                comparison_quality=current_quality,
                unequal_treatment_signals=unequal_treatment_signals,
                target_metrics=target_metrics,
                comparator_metrics=comparator_metrics,
                evidence_chain=summary["evidence_chain"],
                scope=scope,
                scope_text=helpers.scope_text,
                comparator_issue_definitions=helpers.COMPARATOR_ISSUE_DEFINITIONS,
            )
            current_score = (
                int(summary["similarity_checks"]["similarity_score"]) * 10
                + {"high": 3, "partial": 2, "weak": 1}[current_quality]
                + len(unequal_treatment_signals)
            )
            previous_similarity = ((best_summary or {}).get("similarity_checks") or {}) if best_summary else {}
            previous_score = (
                int(previous_similarity.get("similarity_score") or 0) * 10
                + {"high": 3, "partial": 2, "weak": 1}.get(str((best_summary or {}).get("comparison_quality") or ""), 0)
                + len((best_summary or {}).get("unequal_treatment_signals") or [])
            )
            if best_summary is None or current_score > previous_score:
                best_summary = summary
        if best_summary is None:
            summary = {
                "comparator_actor_id": comparator_actor_id,
                "comparator_email": comparator_email,
                "status": "no_suitable_comparator",
                "reason": (
                    "No same-sender message pair addressed both the target and this comparator in the current evidence set."
                ),
                "comparison_quality": "weak",
                "comparison_quality_label": "no_suitable_comparator",
                "similarity_checks": {
                    "shared_request_type": False,
                    "shared_error_type": False,
                    "shared_escalation_context": False,
                    "shared_process_step": False,
                    "shared_workflow_stage": False,
                    "same_sender_decision_path": False,
                    "shared_subject": False,
                    "shared_subject_family": False,
                    "shared_day": False,
                    "shared_day_window": False,
                    "shared_visibility_band": False,
                    "shared_context_count": 0,
                    "shared_subject_families": [],
                    "shared_tags": [],
                    "shared_workflow_stages": [],
                    "shared_visibility_bands": [],
                    "similarity_score": 0,
                },
                "target_metrics": {},
                "comparator_metrics": {},
                "unequal_treatment_signals": [],
                "supports_discrimination_concern": False,
                "uncertainty_reasons": ["No same-sender comparator pair could be established from the current evidence set."],
                "evidence_chain": {"target_uids": [], "comparator_uids": []},
                "discovery_candidates": discovery_candidates,
            }
            summary["comparator_matrix"] = issue_rows(
                comparator_actor_id=comparator_actor_id,
                comparison_quality="weak",
                unequal_treatment_signals=[],
                target_metrics={},
                comparator_metrics={},
                evidence_chain=summary["evidence_chain"],
                scope=scope,
                scope_text=helpers.scope_text,
                comparator_issue_definitions=helpers.COMPARATOR_ISSUE_DEFINITIONS,
            )
            comparator_summaries.append(summary)
        else:
            comparator_summaries.append(best_summary)
    status_counts = Counter(str(summary.get("status") or "") for summary in comparator_summaries)
    comparator_points = shared_comparator_points_from_summaries(comparator_summaries)
    return {
        "version": helpers.COMPARATIVE_TREATMENT_VERSION,
        "target_actor_id": target_actor_id,
        "comparator_count": len(comparator_summaries),
        "summary": {
            "status_counts": dict(sorted(status_counts.items())),
            "available_comparator_count": len(
                [summary for summary in comparator_summaries if summary.get("status") == "comparator_available"]
            ),
            "high_quality_comparator_count": sum(
                1 for summary in comparator_summaries if summary.get("comparison_quality") == "high"
            ),
            "partial_quality_comparator_count": sum(
                1 for summary in comparator_summaries if summary.get("comparison_quality") == "partial"
            ),
            "weak_quality_comparator_count": sum(
                1 for summary in comparator_summaries if summary.get("comparison_quality") == "weak"
            ),
            "low_quality_comparator_count": sum(
                1 for summary in comparator_summaries if summary.get("comparison_quality") == "weak"
            ),
            "no_suitable_comparator_count": sum(
                1 for summary in comparator_summaries if summary.get("status") == "no_suitable_comparator"
            ),
            "discrimination_supporting_comparator_count": sum(
                1 for summary in comparator_summaries if bool(summary.get("supports_discrimination_concern"))
            ),
            "matrix_row_count": sum(
                int(((summary.get("comparator_matrix") or {}).get("row_count")) or 0) for summary in comparator_summaries
            ),
            "strong_matrix_row_count": sum(
                1 for point in comparator_points if str(point.get("comparison_strength") or "") == "strong"
            ),
            "moderate_matrix_row_count": sum(
                1 for point in comparator_points if str(point.get("comparison_strength") or "") == "moderate"
            ),
            "weak_matrix_row_count": sum(
                1 for point in comparator_points if str(point.get("comparison_strength") or "") == "weak"
            ),
            "not_comparable_matrix_row_count": sum(
                1 for point in comparator_points if str(point.get("comparison_strength") or "") == "not_comparable"
            ),
            "discovery_candidate_count": len(discovery_candidates),
        },
        "comparator_discovery_candidates": discovery_candidates,
        "comparator_summaries": comparator_summaries,
        "comparator_points": comparator_points,
    }
