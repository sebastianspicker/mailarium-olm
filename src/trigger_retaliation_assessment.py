"""Assessment and timeline assembly helpers for retaliation analysis."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime

from .trigger_retaliation_helpers import (
    RETALIATION_ANALYSIS_VERSION,
    _as_dict,
    _as_list,
    _candidate_text,
    _candidate_timeline_entry,
    _normalized_subject,
    _parse_iso_like,
    _strongest_metric_changes,
    _window_breakdown,
)


def _timeline_rating(events_payload: list[dict[str, object]]) -> dict[str, str]:
    assessments = [
        assessment for assessment in (event.get("assessment") for event in events_payload) if isinstance(assessment, dict)
    ]
    if not assessments:
        return {
            "rating": "insufficient_timing_record",
            "reason": "No trigger-linked timeline assessment could be built from the current record.",
        }
    statuses = {str(assessment.get("status") or "") for assessment in assessments}
    any_high_quality_adverse = any(
        str(assessment.get("status") or "") == "adverse_shift_after_trigger"
        and str(assessment.get("analysis_quality") or "") in {"high", "medium"}
        and not list(assessment.get("confounder_signals") or [])
        for assessment in assessments
    )
    any_adverse = "adverse_shift_after_trigger" in statuses
    any_mixed = "mixed_shift" in statuses
    all_insufficient = statuses == {"insufficient_context"}
    all_no_clear = statuses == {"no_clear_shift"}
    if any_high_quality_adverse:
        return {
            "rating": "moderate_timing_support",
            "reason": "At least one trigger-linked adverse shift appears without visible confounders and with stronger timeline quality.",
        }
    if any_adverse or any_mixed:
        return {
            "rating": "limited_or_mixed_timing_support",
            "reason": "Some trigger-linked timing indicators are present, but confounders, mixed movement, or limited context keep the timing record cautious.",
        }
    if all_no_clear:
        return {
            "rating": "no_clear_timing_support",
            "reason": "The current record does not show a clear adverse shift after the trigger events.",
        }
    if all_insufficient:
        return {
            "rating": "insufficient_timing_record",
            "reason": "The current record lacks enough before/after coverage to evaluate retaliation timing reliably.",
        }
    return {
        "rating": "insufficient_timing_record",
        "reason": "The current timing record remains too limited or too mixed for a stronger rating.",
    }


def _build_retaliation_timeline_assessment(events_payload: list[dict[str, object]]) -> dict[str, object]:
    protected_activity_timeline: list[dict[str, object]] = []
    adverse_action_timeline: list[dict[str, object]] = []
    temporal_correlation_analysis: list[dict[str, object]] = []
    strongest_retaliation_indicators: list[dict[str, object]] = []
    strongest_non_retaliatory_explanations: list[dict[str, object]] = []
    seen_indicator_keys: set[str] = set()
    seen_explanations: set[str] = set()

    for index, event in enumerate(events_payload, start=1):
        trigger_date_text = str(event.get("date") or "")
        trigger_date = _parse_iso_like(trigger_date_text)
        actor_payload = event.get("actor")
        protected_activity_timeline.append(
            {
                "timeline_id": f"protected_activity:{index}",
                "trigger_type": str(event.get("trigger_type") or ""),
                "date": trigger_date_text,
                "actor": actor_payload if isinstance(actor_payload, dict) else {},
                "notes": str(event.get("notes") or ""),
            }
        )
        before_after = _as_dict(event.get("before_after"))
        metrics = _as_dict(before_after.get("metrics"))
        evidence_chain = _as_dict(event.get("evidence_chain"))
        assessment = _as_dict(event.get("assessment"))
        trigger_after_candidates = [
            candidate for candidate in _as_list(event.get("_after_candidates")) if isinstance(candidate, dict)
        ]
        if trigger_date is not None:
            for candidate in trigger_after_candidates:
                adverse_entry = _candidate_timeline_entry(candidate, trigger_date=trigger_date)
                if adverse_entry["adverse_signals"]:
                    adverse_action_timeline.append(adverse_entry)
        metric_changes = _strongest_metric_changes(metrics)
        window_breakdown = _as_dict(before_after.get("window_breakdown"))
        supporting_uids = [
            str(uid)
            for uid in [*(evidence_chain.get("before_uids") or [])[:1], *(evidence_chain.get("after_uids") or [])[:2]]
            if uid
        ]
        temporal_correlation_analysis.append(
            {
                "timeline_id": f"temporal_correlation:{index}",
                "trigger_type": str(event.get("trigger_type") or ""),
                "trigger_date": trigger_date_text,
                "assessment_status": str(assessment.get("status") or ""),
                "analysis_quality": str(assessment.get("analysis_quality") or ""),
                "before_message_count": int(before_after.get("before_message_count") or 0),
                "after_message_count": int(before_after.get("after_message_count") or 0),
                "immediate_after_count": int(window_breakdown.get("immediate_after_count") or 0),
                "strongest_metric_changes": metric_changes,
                "confounder_signals": [str(item) for item in (assessment.get("confounder_signals") or []) if item],
                "supporting_uids": supporting_uids,
            }
        )
        for change in metric_changes:
            indicator_key = f"{trigger_date_text}:{change['metric']}:{change['direction']}"
            if indicator_key in seen_indicator_keys:
                continue
            seen_indicator_keys.add(indicator_key)
            strongest_retaliation_indicators.append(
                {
                    "indicator": change["reason"],
                    "trigger_date": trigger_date_text,
                    "assessment_status": str(assessment.get("status") or ""),
                    "supporting_uids": [str(uid) for uid in (evidence_chain.get("after_uids") or [])[:3] if uid],
                }
            )
        for explanation in [
            *[str(item) for item in (assessment.get("confounder_signals") or []) if item],
            *[str(item) for item in (assessment.get("uncertainty_reasons") or []) if item],
        ]:
            if explanation in seen_explanations:
                continue
            seen_explanations.add(explanation)
            strongest_non_retaliatory_explanations.append(
                {
                    "explanation": explanation,
                    "trigger_date": trigger_date_text,
                    "supporting_uids": [str(uid) for uid in (evidence_chain.get("after_uids") or [])[:2] if uid],
                }
            )

    adverse_action_timeline.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("uid") or "")))
    return {
        "version": RETALIATION_ANALYSIS_VERSION,
        "protected_activity_timeline": protected_activity_timeline,
        "adverse_action_timeline": adverse_action_timeline[:8],
        "temporal_correlation_analysis": temporal_correlation_analysis,
        "strongest_retaliation_indicators": strongest_retaliation_indicators[:5],
        "strongest_non_retaliatory_explanations": strongest_non_retaliatory_explanations[:5],
        "overall_evidentiary_rating": _timeline_rating(events_payload),
    }


def _retaliation_point_strength(assessment: dict[str, object]) -> str:
    status = str(assessment.get("assessment_status") or assessment.get("status") or "")
    quality = str(assessment.get("analysis_quality") or "")
    confounder_weight = str(_as_dict(assessment.get("confounder_summary")).get("confounder_weight") or "")
    if status == "adverse_shift_after_trigger" and quality in {"high", "medium"} and confounder_weight in {"", "low"}:
        return "moderate"
    if status in {"adverse_shift_after_trigger", "mixed_shift"}:
        return "limited"
    return "insufficient"


def _retaliation_points_from_timeline_assessment(timeline_assessment: dict[str, object]) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for index, row in enumerate(_as_list(timeline_assessment.get("temporal_correlation_analysis")), start=1):
        if not isinstance(row, dict):
            continue
        assessment_status = str(row.get("assessment_status") or "")
        analysis_quality = str(row.get("analysis_quality") or "")
        support_strength = _retaliation_point_strength(row)
        strongest_metric_changes = [
            str(change.get("metric") or "")
            for change in _as_list(row.get("strongest_metric_changes"))
            if isinstance(change, dict)
        ]
        points.append(
            {
                "retaliation_point_id": f"retaliation-point-{index}",
                "assessment_status": assessment_status,
                "analysis_quality": analysis_quality,
                "support_strength": support_strength,
                "strongest_metric_changes": strongest_metric_changes,
                "confounder_signals": [str(item) for item in _as_list(row.get("confounder_signals")) if str(item).strip()],
                "supporting_uids": [str(item) for item in _as_list(row.get("supporting_uids")) if str(item).strip()],
                "counterargument": (
                    str(_as_list(row.get("confounder_signals"))[0]) if _as_list(row.get("confounder_signals")) else ""
                ),
            }
        )
    return points


def shared_retaliation_points(
    retaliation_analysis: object | None = None,
    *,
    retaliation_timeline_assessment: object | None = None,
) -> list[dict[str, object]]:
    payload = retaliation_analysis
    if payload is None:
        payload = retaliation_timeline_assessment
    if not isinstance(payload, dict):
        return []
    points = [point for point in _as_list(payload.get("retaliation_points")) if isinstance(point, dict)]
    if points:
        return points
    nested = _as_dict(payload.get("retaliation_timeline_assessment"))
    timeline_payload = nested if nested else payload
    return _retaliation_points_from_timeline_assessment(timeline_payload)


def _confounder_signals(
    *,
    before_candidates: list[dict[str, object]],
    after_candidates: list[dict[str, object]],
    trigger_date: datetime,
) -> list[str]:
    signals: list[str] = []
    before_senders = {
        str(candidate.get("sender_actor_id") or "") for candidate in before_candidates if candidate.get("sender_actor_id")
    }
    after_senders = {
        str(candidate.get("sender_actor_id") or "") for candidate in after_candidates if candidate.get("sender_actor_id")
    }
    if after_senders - before_senders:
        signals.append("new_sender_appears_after_trigger")
    before_threads = {
        str(candidate.get("thread_group_id") or "") for candidate in before_candidates if candidate.get("thread_group_id")
    }
    after_threads = {
        str(candidate.get("thread_group_id") or "") for candidate in after_candidates if candidate.get("thread_group_id")
    }
    if before_threads and after_threads and not (before_threads & after_threads):
        signals.append("workflow_or_thread_changed_after_trigger")
    before_subjects = {
        _normalized_subject(str(candidate.get("subject") or ""))
        for candidate in before_candidates
        if _normalized_subject(str(candidate.get("subject") or ""))
    }
    after_subjects = {
        _normalized_subject(str(candidate.get("subject") or ""))
        for candidate in after_candidates
        if _normalized_subject(str(candidate.get("subject") or ""))
    }
    if before_subjects and after_subjects and not (before_subjects & after_subjects):
        signals.append("topic_family_shift_after_trigger")
    before_text = " ".join(_candidate_text(candidate) for candidate in before_candidates).lower()
    after_text = " ".join(_candidate_text(candidate) for candidate in after_candidates).lower()
    if any(
        keyword in after_text
        for keyword in ("reorg", "reorganisation", "reorganization", "restructure", "umstruktur", "team move")
    ) and not any(
        keyword in before_text
        for keyword in ("reorg", "reorganisation", "reorganization", "restructure", "umstruktur", "team move")
    ):
        signals.append("organizational_restructuring_context_after_trigger")
    if any(
        keyword in after_text for keyword in ("performance", "incident", "error", "mistake", "outage", "bug", "vpn", "ticket")
    ) and not any(
        keyword in before_text for keyword in ("performance", "incident", "error", "mistake", "outage", "bug", "vpn", "ticket")
    ):
        signals.append("performance_or_incident_context_after_trigger")
    if any(
        keyword in after_text for keyword in ("new manager", "new lead", "department", "team", "handover", "vertretung")
    ) and not any(
        keyword in before_text for keyword in ("new manager", "new lead", "department", "team", "handover", "vertretung")
    ):
        signals.append("team_or_reporting_line_change_after_trigger")
    if any(
        keyword in after_text for keyword in ("hr", "legal", "compliance", "investigation", "formal process", "hr-mailbox")
    ) and not any(
        keyword in before_text for keyword in ("hr", "legal", "compliance", "investigation", "formal process", "hr-mailbox")
    ):
        signals.append("formal_process_transition_after_trigger")
    after_dates = [
        parsed for candidate in after_candidates if (parsed := _parse_iso_like(str(candidate.get("date") or ""))) is not None
    ]
    if len(after_dates) >= 2 and (max(after_dates) - min(after_dates)).days <= 2:
        signals.append("post_trigger_burst_may_reflect_time_limited_operational_event")
    window_breakdown = _window_breakdown([*before_candidates, *after_candidates], trigger_date=trigger_date)
    if window_breakdown["immediate_after_count"] == 0 and window_breakdown["long_tail_count"] > 0:
        signals.append("no_immediate_after_trigger_messages_in_current_record")
    return signals


def _conditional_assessment(
    *,
    trigger_date: datetime,
    before_candidates: list[dict[str, object]],
    after_candidates: list[dict[str, object]],
    before_totals: dict[str, int],
    after_totals: dict[str, int],
    target_before: int,
    target_after: int,
) -> dict[str, object]:
    uncertainty_reasons: list[str] = []
    if not before_candidates or not after_candidates:
        return {
            "status": "insufficient_context",
            "reason": "Need both before and after evidence to assess trigger-linked change.",
            "uncertainty_reasons": [],
            "confounder_signals": [],
            "confounder_summary": {"confounder_count": 0, "confounder_weight": "low"},
            "analysis_quality": "low",
        }
    before_count = len(before_candidates)
    after_count = len(after_candidates)
    if min(before_count, after_count) == 1:
        uncertainty_reasons.append("At least one side of the before/after comparison contains only one message.")
    if abs(before_count - after_count) >= 2:
        uncertainty_reasons.append("Before/after buckets are imbalanced in message count.")
    if target_before == 0 and target_after == 0:
        uncertainty_reasons.append("No message in the current slice can be linked to a target-focused behaviour pattern.")
    confounder_signals = _confounder_signals(
        before_candidates=before_candidates, after_candidates=after_candidates, trigger_date=trigger_date
    )
    if len(confounder_signals) >= 3:
        uncertainty_reasons.append("Multiple neutral confounders remain available in the current before/after slice.")
    metric_rate_deltas = {
        key: (
            (after_totals[key] / after_count if after_count else 0.0)
            - (before_totals[key] / before_count if before_count else 0.0)
        )
        for key in before_totals
    }
    increased_metrics = [key for key, delta in metric_rate_deltas.items() if delta > 0]
    decreased_metrics = [key for key, delta in metric_rate_deltas.items() if delta < 0]
    adverse_before = sum(before_totals.values()) / before_count if before_count else 0.0
    adverse_after = sum(after_totals.values()) / after_count if after_count else 0.0
    analysis_quality = (
        "high"
        if min(before_count, after_count) >= 2 and not confounder_signals
        else "low"
        if len(confounder_signals) >= 3
        else "medium"
        if min(before_count, after_count) >= 1
        else "low"
    )
    strong_confounders = {
        "organizational_restructuring_context_after_trigger",
        "performance_or_incident_context_after_trigger",
        "team_or_reporting_line_change_after_trigger",
        "formal_process_transition_after_trigger",
    }
    strong_confounder_present = any(signal in strong_confounders for signal in confounder_signals)
    if adverse_after > adverse_before and (target_after > target_before or len(increased_metrics) >= 2):
        if strong_confounder_present and len(confounder_signals) >= 2:
            return {
                "status": "mixed_shift",
                "reason": "Some adverse metrics worsened after the trigger event, but the current sequence also contains strong neutral confounders such as workflow, team, or incident-context changes.",
                "uncertainty_reasons": uncertainty_reasons,
                "confounder_signals": confounder_signals,
                "confounder_summary": {"confounder_count": len(confounder_signals), "confounder_weight": "high"},
                "analysis_quality": analysis_quality,
            }
        if decreased_metrics:
            return {
                "status": "mixed_shift",
                "reason": "Some adverse metrics worsened after the trigger event, while other metrics moved in a different direction.",
                "uncertainty_reasons": uncertainty_reasons,
                "confounder_signals": confounder_signals,
                "confounder_summary": {
                    "confounder_count": len(confounder_signals),
                    "confounder_weight": "medium" if confounder_signals else "low",
                },
                "analysis_quality": analysis_quality,
            }
        return {
            "status": "adverse_shift_after_trigger",
            "reason": "Normalized adverse behaviour intensity increased after the trigger event, but alternative non-retaliatory explanations remain possible.",
            "uncertainty_reasons": uncertainty_reasons,
            "confounder_signals": confounder_signals,
            "confounder_summary": {
                "confounder_count": len(confounder_signals),
                "confounder_weight": "medium" if confounder_signals else "low",
            },
            "analysis_quality": analysis_quality,
        }
    if increased_metrics and decreased_metrics:
        return {
            "status": "mixed_shift",
            "reason": "Some normalized adverse metrics increased after the trigger event, while others did not.",
            "uncertainty_reasons": uncertainty_reasons,
            "confounder_signals": confounder_signals,
            "confounder_summary": {
                "confounder_count": len(confounder_signals),
                "confounder_weight": "medium" if confounder_signals else "low",
            },
            "analysis_quality": analysis_quality,
        }
    return {
        "status": "no_clear_shift",
        "reason": "Normalized adverse behaviour intensity did not increase after the trigger event.",
        "uncertainty_reasons": uncertainty_reasons,
        "confounder_signals": confounder_signals,
        "confounder_summary": {
            "confounder_count": len(confounder_signals),
            "confounder_weight": "medium" if confounder_signals else "low",
        },
        "analysis_quality": analysis_quality,
    }
