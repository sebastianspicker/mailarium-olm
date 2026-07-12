"""Assessment and timeline assembly helpers for retaliation analysis."""
# pylint: disable=too-many-arguments,too-many-locals


# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from ._utils import _as_dict, _as_list
from .trigger_retaliation_helpers import (
    RETALIATION_ANALYSIS_VERSION,
    _candidate_text,
    _candidate_timeline_entry,
    _normalized_subject,
    _parse_iso_like,
    _strongest_metric_changes,
    _window_breakdown,
)


def _timeline_rating(events_payload: list[dict[str, object]]) -> dict[str, str]:
    """Derive an overall timeline rating from trigger-linked assessment events.

    Args:
        events_payload: List of event dictionaries containing assessment data.

    Returns:
        Dictionary with 'rating' and 'reason' keys describing the timeline quality.
        Possible ratings: 'moderate_timing_support', 'limited_or_mixed_timing_support',
        'no_clear_timing_support', 'insufficient_timing_record'.
    """
    assessments = [
        assessment for assessment in (event.get("assessment") for event in events_payload) if isinstance(assessment, dict)
    ]
    if not assessments:
        return {
            "rating": "insufficient_timing_record",
            "reason": "No trigger-linked timeline assessment could be built from the current record.",
        }
    return _rating_from_assessments(assessments)


def _rating_from_assessments(assessments: list[dict[str, object]]) -> dict[str, str]:
    statuses = {str(item.get("status") or "") for item in assessments}
    high_quality_adverse = any(_is_high_quality_adverse(item) for item in assessments)
    if high_quality_adverse:
        return {
            "rating": "moderate_timing_support",
            "reason": "At least one trigger-linked adverse shift appears without visible confounders and with stronger timeline quality.",
        }
    if {"adverse_shift_after_trigger", "mixed_shift"} & statuses:
        return {
            "rating": "limited_or_mixed_timing_support",
            "reason": "Some trigger-linked timing indicators are present, but confounders, mixed movement, or limited context keep the timing record cautious.",
        }
    if statuses == {"no_clear_shift"}:
        return {
            "rating": "no_clear_timing_support",
            "reason": "The current record does not show a clear adverse shift after the trigger events.",
        }
    if statuses == {"insufficient_context"}:
        return {
            "rating": "insufficient_timing_record",
            "reason": "The current record lacks enough before/after coverage to evaluate retaliation timing reliably.",
        }
    return {
        "rating": "insufficient_timing_record",
        "reason": "The current timing record remains too limited or too mixed for a stronger rating.",
    }


def _is_high_quality_adverse(assessment: dict[str, object]) -> bool:
    return (
        str(assessment.get("status") or "") == "adverse_shift_after_trigger"
        and str(assessment.get("analysis_quality") or "") in {"high", "medium"}
        and not _as_list(assessment.get("confounder_signals"))
    )


@dataclass(slots=True)
class _TimelineAssembly:
    protected: list[dict[str, object]] = field(default_factory=list)
    adverse: list[dict[str, object]] = field(default_factory=list)
    correlations: list[dict[str, object]] = field(default_factory=list)
    indicators: list[dict[str, object]] = field(default_factory=list)
    explanations: list[dict[str, object]] = field(default_factory=list)
    seen_indicators: set[str] = field(default_factory=set)
    seen_explanations: set[str] = field(default_factory=set)


def _build_retaliation_timeline_assessment(events_payload: list[dict[str, object]]) -> dict[str, object]:
    """Build a comprehensive retaliation timeline assessment from trigger events.

    Args:
        events_payload: List of trigger event dictionaries with assessment data.

    Returns:
        Dictionary containing:
            - version: Analysis version identifier
            - protected_activity_timeline: List of protected activity entries
            - adverse_action_timeline: List of adverse action entries (max 8)
            - temporal_correlation_analysis: List of correlation analysis entries
            - strongest_retaliation_indicators: Top 5 retaliation indicators
            - strongest_non_retaliatory_explanations: Top 5 non-retaliatory explanations
            - overall_evidentiary_rating: Overall rating from _timeline_rating
    """
    assembly = _TimelineAssembly()
    for index, event in enumerate(events_payload, start=1):
        _append_timeline_event(assembly, event, index)
    assembly.adverse.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("uid") or "")))
    return {
        "version": RETALIATION_ANALYSIS_VERSION,
        "protected_activity_timeline": assembly.protected,
        "adverse_action_timeline": assembly.adverse[:8],
        "temporal_correlation_analysis": assembly.correlations,
        "strongest_retaliation_indicators": assembly.indicators[:5],
        "strongest_non_retaliatory_explanations": assembly.explanations[:5],
        "overall_evidentiary_rating": _timeline_rating(events_payload),
    }


def _append_timeline_event(assembly: _TimelineAssembly, event: dict[str, object], index: int) -> None:
    trigger_date_text = str(event.get("date") or "")
    trigger_date = _parse_iso_like(trigger_date_text)
    actor = event.get("actor")
    assembly.protected.append(
        {
            "timeline_id": f"protected_activity:{index}",
            "trigger_type": str(event.get("trigger_type") or ""),
            "date": trigger_date_text,
            "actor": actor if isinstance(actor, dict) else {},
            "notes": str(event.get("notes") or ""),
        }
    )
    before_after = _as_dict(event.get("before_after"))
    assessment = _as_dict(event.get("assessment"))
    evidence_chain = _as_dict(event.get("evidence_chain"))
    if trigger_date is not None:
        _append_adverse_entries(assembly.adverse, event, trigger_date)
    changes = _strongest_metric_changes(_as_dict(before_after.get("metrics")))
    assembly.correlations.append(
        _correlation_row(index, event, trigger_date_text, before_after, assessment, evidence_chain, changes)
    )
    _append_indicators(assembly, trigger_date_text, assessment, evidence_chain, changes)
    _append_explanations(assembly, trigger_date_text, assessment, evidence_chain)


def _append_adverse_entries(target: list[dict[str, object]], event: dict[str, object], trigger_date: datetime) -> None:
    for candidate in _as_list(event.get("_after_candidates")):
        if not isinstance(candidate, dict):
            continue
        entry = _candidate_timeline_entry(candidate, trigger_date=trigger_date)
        if entry["adverse_signals"]:
            target.append(entry)


def _correlation_row(
    index: int,
    event: dict[str, object],
    trigger_date_text: str,
    before_after: dict[str, object],
    assessment: dict[str, object],
    evidence_chain: dict[str, object],
    changes: list[dict[str, object]],
) -> dict[str, object]:
    window = _as_dict(before_after.get("window_breakdown"))
    return {
        "timeline_id": f"temporal_correlation:{index}",
        "trigger_type": str(event.get("trigger_type") or ""),
        "trigger_date": trigger_date_text,
        "assessment_status": str(assessment.get("status") or ""),
        "analysis_quality": str(assessment.get("analysis_quality") or ""),
        "before_message_count": int(cast(Any, before_after.get("before_message_count") or 0)),
        "after_message_count": int(cast(Any, before_after.get("after_message_count") or 0)),
        "immediate_after_count": int(window.get("immediate_after_count") or 0),
        "strongest_metric_changes": changes,
        "confounder_signals": _string_items(assessment.get("confounder_signals")),
        "supporting_uids": [
            *_string_items(evidence_chain.get("before_uids"))[:1],
            *_string_items(evidence_chain.get("after_uids"))[:2],
        ],
    }


def _append_indicators(
    assembly: _TimelineAssembly,
    trigger_date: str,
    assessment: dict[str, object],
    evidence_chain: dict[str, object],
    changes: list[dict[str, object]],
) -> None:
    for change in changes:
        key = f"{trigger_date}:{change['metric']}:{change['direction']}"
        if key in assembly.seen_indicators:
            continue
        assembly.seen_indicators.add(key)
        assembly.indicators.append(
            {
                "indicator": change["reason"],
                "trigger_date": trigger_date,
                "assessment_status": str(assessment.get("status") or ""),
                "supporting_uids": _string_items(evidence_chain.get("after_uids"))[:3],
            }
        )


def _append_explanations(
    assembly: _TimelineAssembly,
    trigger_date: str,
    assessment: dict[str, object],
    evidence_chain: dict[str, object],
) -> None:
    explanations = [
        *_string_items(assessment.get("confounder_signals")),
        *_string_items(assessment.get("uncertainty_reasons")),
    ]
    for explanation in explanations:
        if explanation in assembly.seen_explanations:
            continue
        assembly.seen_explanations.add(explanation)
        assembly.explanations.append(
            {
                "explanation": explanation,
                "trigger_date": trigger_date,
                "supporting_uids": _string_items(evidence_chain.get("after_uids"))[:2],
            }
        )


def _string_items(value: object) -> list[str]:
    return [str(item) for item in _as_list(value) if item]


def _retaliation_point_strength(assessment: dict[str, object]) -> str:
    """Determine the strength level of a retaliation assessment point.

    Args:
        assessment: Dictionary containing assessment data with status, quality,
            and confounder information.

    Returns:
        String strength level: 'moderate', 'limited', or 'insufficient'.
    """
    status = str(assessment.get("assessment_status") or assessment.get("status") or "")
    quality = str(assessment.get("analysis_quality") or "")
    confounder_weight = str(_as_dict(assessment.get("confounder_summary")).get("confounder_weight") or "")
    if status == "adverse_shift_after_trigger" and quality in {"high", "medium"} and confounder_weight in {"", "low"}:
        return "moderate"
    if status in {"adverse_shift_after_trigger", "mixed_shift"}:
        return "limited"
    return "insufficient"


def _retaliation_points_from_timeline_assessment(timeline_assessment: dict[str, object]) -> list[dict[str, object]]:
    """Extract retaliation points from a timeline assessment structure.

    Args:
        timeline_assessment: Dictionary containing temporal correlation analysis data.

    Returns:
        List of retaliation point dictionaries with extracted metadata.
    """
    points: list[dict[str, object]] = []
    for index, row in enumerate(_as_list(timeline_assessment.get("temporal_correlation_analysis")), start=1):
        if not isinstance(row, dict):
            continue
        points.append(_retaliation_point(row, index))
    return points


def _retaliation_point(row: dict[str, object], index: int) -> dict[str, object]:
    confounders = _as_list(row.get("confounder_signals"))
    return {
        "retaliation_point_id": f"retaliation-point-{index}",
        "assessment_status": str(row.get("assessment_status") or ""),
        "analysis_quality": str(row.get("analysis_quality") or ""),
        "support_strength": _retaliation_point_strength(row),
        "strongest_metric_changes": [
            str(change.get("metric") or "")
            for change in _as_list(row.get("strongest_metric_changes"))
            if isinstance(change, dict)
        ],
        "confounder_signals": [str(item) for item in confounders if str(item).strip()],
        "supporting_uids": [str(item) for item in _as_list(row.get("supporting_uids")) if str(item).strip()],
        "counterargument": str(confounders[0]) if confounders else "",
    }


def shared_retaliation_points(
    retaliation_analysis: object | None = None,
    *,
    retaliation_timeline_assessment: object | None = None,
) -> list[dict[str, object]]:
    """Extract retaliation points from either a retaliation analysis or timeline assessment.

    This is a shared utility that can work with either format, falling back to
    conversion from timeline assessment if needed.

    Args:
        retaliation_analysis: Optional pre-built retaliation analysis dictionary.
        retaliation_timeline_assessment: Optional timeline assessment to convert.

    Returns:
        List of retaliation point dictionaries. Empty list if no valid input.
    """
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
    """Identify confounder signals that may explain changes independent of retaliation.

    Analyzes before/after candidate sets to detect patterns that could provide
    alternative explanations for observed changes.

    Args:
        before_candidates: List of candidate dictionaries from before the trigger date.
        after_candidates: List of candidate dictionaries from after the trigger date.
        trigger_date: The datetime of the trigger event.

    Returns:
        List of string signal identifiers describing detected confounders.
    """
    signals = _identity_confounders(before_candidates, after_candidates)
    before_text = " ".join(_candidate_text(candidate) for candidate in before_candidates).lower()
    after_text = " ".join(_candidate_text(candidate) for candidate in after_candidates).lower()
    signals.extend(_text_confounders(before_text, after_text))
    signals.extend(_timing_confounders(after_candidates, before_candidates, trigger_date))
    return signals


def _identity_confounders(before_candidates: list[dict[str, object]], after_candidates: list[dict[str, object]]) -> list[str]:
    signals: list[str] = []
    before_senders = _field_values(before_candidates, "sender_actor_id")
    after_senders = _field_values(after_candidates, "sender_actor_id")
    if after_senders - before_senders:
        signals.append("new_sender_appears_after_trigger")
    before_threads = _field_values(before_candidates, "thread_group_id")
    after_threads = _field_values(after_candidates, "thread_group_id")
    if before_threads and after_threads and not (before_threads & after_threads):
        signals.append("workflow_or_thread_changed_after_trigger")
    before_subjects = _subjects(before_candidates)
    after_subjects = _subjects(after_candidates)
    if before_subjects and after_subjects and not (before_subjects & after_subjects):
        signals.append("topic_family_shift_after_trigger")
    return signals


def _field_values(candidates: list[dict[str, object]], key: str) -> set[str]:
    return {str(candidate[key]) for candidate in candidates if candidate.get(key)}


def _subjects(candidates: list[dict[str, object]]) -> set[str]:
    return {subject for candidate in candidates if (subject := _normalized_subject(str(candidate.get("subject") or "")))}


def _text_confounders(before_text: str, after_text: str) -> list[str]:
    contexts = (
        (
            ("reorg", "reorganisation", "reorganization", "restructure", "umstruktur", "team move"),
            "organizational_restructuring_context_after_trigger",
        ),
        (
            ("performance", "incident", "error", "mistake", "outage", "bug", "vpn", "ticket"),
            "performance_or_incident_context_after_trigger",
        ),
        (
            ("new manager", "new lead", "department", "team", "handover", "vertretung"),
            "team_or_reporting_line_change_after_trigger",
        ),
        (
            ("hr", "legal", "compliance", "investigation", "formal process", "hr-mailbox"),
            "formal_process_transition_after_trigger",
        ),
    )
    return [signal for keywords, signal in contexts if _new_keyword_context(keywords, before_text, after_text)]


def _new_keyword_context(keywords: tuple[str, ...], before_text: str, after_text: str) -> bool:
    return any(keyword in after_text for keyword in keywords) and not any(keyword in before_text for keyword in keywords)


def _timing_confounders(
    after_candidates: list[dict[str, object]],
    before_candidates: list[dict[str, object]],
    trigger_date: datetime,
) -> list[str]:
    signals: list[str] = []
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
    """Generate a conditional assessment of retaliation based on before/after comparison.

    Evaluates whether adverse behavior intensity changed after a trigger event,
    considering confounders, metric changes, and analysis quality.

    Args:
        trigger_date: The datetime of the trigger event.
        before_candidates: List of candidate dictionaries from before the trigger.
        after_candidates: List of candidate dictionaries from after the trigger.
        before_totals: Dictionary of adverse metric totals from before period.
        after_totals: Dictionary of adverse metric totals from after period.
        target_before: Count of target-focused messages before the trigger.
        target_after: Count of target-focused messages after the trigger.

    Returns:
        Dictionary containing:
            - status: Assessment status string
            - reason: Human-readable explanation
            - uncertainty_reasons: List of uncertainty factors
            - confounder_signals: List of detected confounder signals
            - confounder_summary: Dictionary with confounder count and weight
            - analysis_quality: Quality level string
    """
    if not before_candidates or not after_candidates:
        return _insufficient_assessment()
    context = _assessment_context(
        trigger_date=trigger_date,
        before_candidates=before_candidates,
        after_candidates=after_candidates,
        before_totals=before_totals,
        after_totals=after_totals,
        target_before=target_before,
        target_after=target_after,
    )
    if context.adverse_after > context.adverse_before and (target_after > target_before or len(context.increased_metrics) >= 2):
        return _adverse_shift_result(context)
    if context.increased_metrics and context.decreased_metrics:
        return _assessment_result(
            "mixed_shift",
            "Some normalized adverse metrics increased after the trigger event, while others did not.",
            context,
        )
    return _assessment_result(
        "no_clear_shift",
        "Normalized adverse behaviour intensity did not increase after the trigger event.",
        context,
    )


@dataclass(slots=True)
class _AssessmentContext:
    uncertainty_reasons: list[str]
    confounder_signals: list[str]
    increased_metrics: list[str]
    decreased_metrics: list[str]
    adverse_before: float
    adverse_after: float
    analysis_quality: str


def _insufficient_assessment() -> dict[str, object]:
    return {
        "status": "insufficient_context",
        "reason": "Need both before and after evidence to assess trigger-linked change.",
        "uncertainty_reasons": [],
        "confounder_signals": [],
        "confounder_summary": {"confounder_count": 0, "confounder_weight": "low"},
        "analysis_quality": "low",
    }


def _assessment_context(
    *,
    trigger_date: datetime,
    before_candidates: list[dict[str, object]],
    after_candidates: list[dict[str, object]],
    before_totals: dict[str, int],
    after_totals: dict[str, int],
    target_before: int,
    target_after: int,
) -> _AssessmentContext:
    before_count = len(before_candidates)
    after_count = len(after_candidates)
    confounders = _confounder_signals(
        before_candidates=before_candidates, after_candidates=after_candidates, trigger_date=trigger_date
    )
    uncertainty = _uncertainty_reasons(before_count, after_count, target_before, target_after, confounders)
    deltas = _metric_rate_deltas(before_totals, after_totals, before_count, after_count)
    return _AssessmentContext(
        uncertainty_reasons=uncertainty,
        confounder_signals=confounders,
        increased_metrics=[key for key, delta in deltas.items() if delta > 0],
        decreased_metrics=[key for key, delta in deltas.items() if delta < 0],
        adverse_before=sum(before_totals.values()) / before_count,
        adverse_after=sum(after_totals.values()) / after_count,
        analysis_quality=_analysis_quality(before_count, after_count, confounders),
    )


def _uncertainty_reasons(
    before_count: int,
    after_count: int,
    target_before: int,
    target_after: int,
    confounders: list[str],
) -> list[str]:
    reasons: list[str] = []
    if min(before_count, after_count) == 1:
        reasons.append("At least one side of the before/after comparison contains only one message.")
    if abs(before_count - after_count) >= 2:
        reasons.append("Before/after buckets are imbalanced in message count.")
    if target_before == 0 and target_after == 0:
        reasons.append("No message in the current slice can be linked to a target-focused behaviour pattern.")
    if len(confounders) >= 3:
        reasons.append("Multiple neutral confounders remain available in the current before/after slice.")
    return reasons


def _metric_rate_deltas(
    before_totals: dict[str, int], after_totals: dict[str, int], before_count: int, after_count: int
) -> dict[str, float]:
    return {key: (after_totals[key] / after_count) - (before_totals[key] / before_count) for key in before_totals}


def _analysis_quality(before_count: int, after_count: int, confounders: list[str]) -> str:
    if min(before_count, after_count) >= 2 and not confounders:
        return "high"
    if len(confounders) >= 3:
        return "low"
    return "medium"


def _adverse_shift_result(context: _AssessmentContext) -> dict[str, object]:
    if _strong_confounder_present(context.confounder_signals) and len(context.confounder_signals) >= 2:
        return _assessment_result(
            "mixed_shift",
            "Some adverse metrics worsened after the trigger event, but the current sequence also contains strong neutral confounders such as workflow, team, or incident-context changes.",
            context,
            confounder_weight="high",
        )
    if context.decreased_metrics:
        return _assessment_result(
            "mixed_shift",
            "Some adverse metrics worsened after the trigger event, while other metrics moved in a different direction.",
            context,
        )
    return _assessment_result(
        "adverse_shift_after_trigger",
        "Normalized adverse behaviour intensity increased after the trigger event, but alternative non-retaliatory explanations remain possible.",
        context,
    )


def _strong_confounder_present(confounders: list[str]) -> bool:
    strong_confounders = {
        "organizational_restructuring_context_after_trigger",
        "performance_or_incident_context_after_trigger",
        "team_or_reporting_line_change_after_trigger",
        "formal_process_transition_after_trigger",
    }
    return any(signal in strong_confounders for signal in confounders)


def _assessment_result(
    status: str,
    reason: str,
    context: _AssessmentContext,
    *,
    confounder_weight: str | None = None,
) -> dict[str, object]:
    weight = confounder_weight or ("medium" if context.confounder_signals else "low")
    return {
        "status": status,
        "reason": reason,
        "uncertainty_reasons": context.uncertainty_reasons,
        "confounder_signals": context.confounder_signals,
        "confounder_summary": {"confounder_count": len(context.confounder_signals), "confounder_weight": weight},
        "analysis_quality": context.analysis_quality,
    }
