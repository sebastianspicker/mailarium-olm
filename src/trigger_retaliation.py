"""Trigger-event and retaliation-style before/after analysis helpers."""
# pylint: disable=too-many-locals

from __future__ import annotations

from typing import Any

from src._utils import _as_dict, _as_list, _compact

from . import trigger_retaliation_assessment as _assessment
from .trigger_retaliation_helpers import (
    RETALIATION_ANALYSIS_VERSION,
    _adverse_action_candidates,
    _adverse_counts,
    _bucket_candidates,
    _candidate_timeline_entry,
    _empty_timeline_assessment,
    _parse_iso_like,
    _protected_activity_candidates,
    _rate_metric,
    _response_time_metric,
    _targeted_message_count,
    _window_breakdown,
)

_conditional_assessment = _assessment._conditional_assessment


def _source_record_candidates(multi_source_case_bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return pseudo-candidates derived from mixed-source records."""
    candidates: list[dict[str, Any]] = []
    for source in _as_list(_as_dict(multi_source_case_bundle).get("sources")):
        if not isinstance(source, dict):
            continue
        source_id = _compact(source.get("source_id"))
        if not source_id:
            continue
        text_preview = _compact(_as_dict(source.get("documentary_support")).get("text_preview"))
        if not any((_compact(source.get("title")), _compact(source.get("snippet")), text_preview)):
            continue
        candidates.append(
            {
                "uid": _compact(source.get("uid")) or source_id,
                "source_id": source_id,
                "date": _compact(source.get("date")),
                "subject": _compact(source.get("title")),
                "title": _compact(source.get("title")),
                "snippet": _compact(source.get("snippet")),
                "text_preview": text_preview,
                "source_type": _compact(source.get("source_type")),
            }
        )
    return candidates


def _merge_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate candidate rows based on type, date, and source linkage."""
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_linkage = _as_dict(row.get("source_linkage"))
        key = (
            _compact(row.get("candidate_type") or row.get("action_type")),
            _compact(row.get("date")),
            ",".join(str(item) for item in _as_list(source_linkage.get("supporting_uids")) if str(item).strip()),
            ",".join(str(item) for item in _as_list(source_linkage.get("source_ids")) if str(item).strip()),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _source_backed_retaliation_points(
    *,
    explicit_trigger_events: list[Any],
    source_adverse_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate retaliation points from source-backed adverse action candidates."""
    points: list[dict[str, Any]] = []
    for trigger_index, trigger_event in enumerate(explicit_trigger_events, start=1):
        trigger_date = _parse_iso_like(str(getattr(trigger_event, "date", "") or ""))
        if trigger_date is None:
            continue
        for adverse_index, adverse in enumerate(source_adverse_candidates, start=1):
            adverse_date = _parse_iso_like(_compact(adverse.get("date")))
            if adverse_date is None or adverse_date <= trigger_date:
                continue
            source_ids = [
                str(item) for item in _as_list(_as_dict(adverse.get("source_linkage")).get("source_ids")) if str(item).strip()
            ]
            if not source_ids:
                continue
            days_from_trigger = (adverse_date - trigger_date).days
            points.append(
                {
                    "retaliation_point_id": f"retaliation-source-point-{trigger_index}-{adverse_index}",
                    "assessment_status": "source_backed_temporal_proximity",
                    "analysis_quality": "low",
                    "support_strength": "limited",
                    "strongest_metric_changes": [],
                    "confounder_signals": ["source_backed_without_behavioral_before_after_baseline"],
                    "supporting_uids": [
                        str(item)
                        for item in _as_list(_as_dict(adverse.get("source_linkage")).get("supporting_uids"))
                        if str(item).strip()
                    ],
                    "supporting_source_ids": source_ids,
                    "counterargument": (
                        "Mixed-source timing is suggestive, but it lacks a comparable before/after behavioral baseline."
                    ),
                    "point_summary": (
                        f"Source-backed adverse-action candidate {str(adverse.get('action_type') or 'action').replace('_', ' ')} "
                        f"appears {days_from_trigger} days after the explicit trigger event in {source_ids[0]}."
                    ),
                }
            )
    return points


def augment_retaliation_analysis_with_sources(
    retaliation_analysis: dict[str, Any] | None,
    *,
    case_scope: Any,
    multi_source_case_bundle: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge mixed-source protected-activity and adverse-action candidates into retaliation output."""
    source_candidates = _source_record_candidates(multi_source_case_bundle)
    if not source_candidates:
        return retaliation_analysis

    explicit_trigger_events = _explicit_trigger_events(case_scope)
    source_protected_candidates, source_adverse_candidates = _source_retaliation_candidates(case_scope, source_candidates)
    if not source_protected_candidates and not source_adverse_candidates:
        return retaliation_analysis

    payload = dict(retaliation_analysis or {})
    protected_activity_candidates = _merged_source_candidates(
        payload, "protected_activity_candidates", source_protected_candidates
    )
    adverse_action_candidates = _merged_source_candidates(payload, "adverse_action_candidates", source_adverse_candidates)
    timeline_assessment = _augmented_source_timeline(payload, explicit_trigger_events, source_adverse_candidates)

    retaliation_points = _merged_source_points(payload, explicit_trigger_events, source_adverse_candidates)

    return _finalize_source_retaliation_payload(
        payload,
        protected_activity_candidates,
        adverse_action_candidates,
        timeline_assessment,
        retaliation_points,
        source_protected_candidates,
        source_adverse_candidates,
        explicit_trigger_events,
    )


def _merged_source_candidates(payload: dict[str, Any], key: str, additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = [row for row in payload.get(key) or [] if isinstance(row, dict)]
    return _merge_candidate_rows([*existing, *additions])


def _merged_source_points(
    payload: dict[str, Any], trigger_events: list[Any], adverse_candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    points = [row for row in payload.get("retaliation_points") or [] if isinstance(row, dict)]
    points.extend(
        _source_backed_retaliation_points(explicit_trigger_events=trigger_events, source_adverse_candidates=adverse_candidates)
    )
    return points


def _explicit_trigger_events(case_scope: Any) -> list[Any]:
    return [
        *list(getattr(case_scope, "trigger_events", []) or []),
        *list(getattr(case_scope, "asserted_rights_timeline", []) or []),
    ]


def _source_retaliation_candidates(
    case_scope: Any, source_candidates: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    protected = [row for row in _protected_activity_candidates(case_scope, source_candidates) if _eligible_source_protected(row)]
    return protected, _adverse_action_candidates(source_candidates)


def _eligible_source_protected(row: dict[str, Any]) -> bool:
    span = _compact(row.get("source_span")).lower()
    return (
        str(row.get("source_kind") or "") == "record_derived_candidate"
        and "after the complaint" not in span
        and "nach der beschwerde" not in span
    )


def _augmented_source_timeline(
    payload: dict[str, Any], trigger_events: list[Any], adverse_candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    assessment = dict(payload.get("retaliation_timeline_assessment") or _empty_timeline_assessment())
    timeline = [row for row in assessment.get("adverse_action_timeline") or [] if isinstance(row, dict)]
    for trigger_event in trigger_events:
        trigger_date = _parse_iso_like(str(getattr(trigger_event, "date", "") or ""))
        if trigger_date is not None:
            timeline.extend(_source_timeline_rows(trigger_date, adverse_candidates))
    assessment["adverse_action_timeline"] = _deduped_source_timeline(timeline)[:8]
    return assessment


def _source_timeline_rows(trigger_date: Any, adverse_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for adverse in adverse_candidates:
        adverse_date = _parse_iso_like(_compact(adverse.get("date")))
        if adverse_date is not None and adverse_date > trigger_date:
            rows.append(_source_timeline_row(trigger_date, adverse))
    return rows


def _source_timeline_row(trigger_date: Any, adverse: dict[str, Any]) -> dict[str, Any]:
    linkage = _as_dict(adverse.get("source_linkage"))
    source_ids = _string_rows(linkage.get("source_ids"))
    uids = _string_rows(linkage.get("supporting_uids"))
    row = _candidate_timeline_entry(
        {
            "uid": uids[0] if uids else "",
            "date": _compact(adverse.get("date")),
            "subject": _compact(adverse.get("action_type")).replace("_", " "),
        },
        trigger_date=trigger_date,
    )
    row.update(
        source_id=source_ids[0] if source_ids else "",
        adverse_signals=[str(adverse.get("action_type") or "")],
        source_kind="mixed_source_record",
    )
    return row


def _string_rows(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if str(item).strip()]


def _deduped_source_timeline(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in timeline:
        key = (_compact(row.get("uid")), _compact(row.get("source_id")), _compact(row.get("date")))
        if key not in seen:
            seen.add(key)
            rows.append(row)
    return sorted(rows, key=lambda item: (_compact(item.get("date")), _compact(item.get("uid")), _compact(item.get("source_id"))))


def _finalize_source_retaliation_payload(
    payload: dict[str, Any],
    protected: list[dict[str, Any]],
    adverse: list[dict[str, Any]],
    timeline: dict[str, Any],
    points: list[dict[str, Any]],
    source_protected: list[dict[str, Any]],
    source_adverse: list[dict[str, Any]],
    trigger_events: list[Any],
) -> dict[str, Any]:
    payload.update(
        protected_activity_candidate_count=len(protected),
        protected_activity_candidates=protected,
        adverse_action_candidate_count=len(adverse),
        adverse_action_candidates=adverse,
        retaliation_timeline_assessment=timeline,
        retaliation_points=points,
        retaliation_point_count=len(points),
        source_backed_candidate_counts={"protected_activity": len(source_protected), "adverse_actions": len(source_adverse)},
    )
    payload.setdefault("version", RETALIATION_ANALYSIS_VERSION)
    payload.setdefault(
        "anchor_requirement_status", "explicit_trigger_confirmed" if trigger_events else "explicit_trigger_confirmation_required"
    )
    return payload


def shared_retaliation_points(
    retaliation_analysis: object | None = None,
    *,
    retaliation_timeline_assessment: object | None = None,
) -> list[dict[str, object]]:
    """Return shared retaliation points with backward-compatible call shapes."""
    return _assessment.shared_retaliation_points(
        retaliation_analysis,
        retaliation_timeline_assessment=retaliation_timeline_assessment,
    )


def build_retaliation_analysis(
    *,
    case_scope: Any,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    multi_source_case_bundle: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return explicit trigger-event and before/after retaliation-style analysis."""
    trigger_events = list(getattr(case_scope, "trigger_events", []) or [])
    asserted_rights_timeline = list(getattr(case_scope, "asserted_rights_timeline", []) or [])
    explicit_trigger_events = trigger_events or asserted_rights_timeline
    protected_activity_candidates = _protected_activity_candidates(case_scope, candidates)
    adverse_action_candidates = _adverse_action_candidates(candidates)
    if not explicit_trigger_events:
        timeline_assessment = _empty_timeline_assessment()
        payload = {
            "version": RETALIATION_ANALYSIS_VERSION,
            "trigger_event_count": 0,
            "trigger_events": [],
            "protected_activity_candidate_count": len(protected_activity_candidates),
            "protected_activity_candidates": protected_activity_candidates,
            "adverse_action_candidate_count": len(adverse_action_candidates),
            "adverse_action_candidates": adverse_action_candidates,
            "anchor_requirement_status": "explicit_trigger_confirmation_required",
            "retaliation_timeline_assessment": timeline_assessment,
            "retaliation_point_count": 0,
            "retaliation_points": [],
        }
        return augment_retaliation_analysis_with_sources(
            payload,
            case_scope=case_scope,
            multi_source_case_bundle=multi_source_case_bundle,
        )

    target_actor_id = _target_actor_id(case_bundle)
    events_payload = [
        event_payload
        for trigger_event in explicit_trigger_events
        if (event_payload := _trigger_event_payload(trigger_event, candidates, target_actor_id)) is not None
    ]

    timeline_assessment = _assessment._build_retaliation_timeline_assessment(events_payload)
    retaliation_points = _assessment._retaliation_points_from_timeline_assessment(timeline_assessment)
    for event in events_payload:
        event.pop("_after_candidates", None)
    payload = {
        "version": RETALIATION_ANALYSIS_VERSION,
        "trigger_event_count": len(events_payload),
        "trigger_events": events_payload,
        "protected_activity_candidate_count": len(protected_activity_candidates),
        "protected_activity_candidates": protected_activity_candidates,
        "adverse_action_candidate_count": len(adverse_action_candidates),
        "adverse_action_candidates": adverse_action_candidates,
        "anchor_requirement_status": "explicit_trigger_confirmed",
        "retaliation_timeline_assessment": timeline_assessment,
        "retaliation_point_count": len(retaliation_points),
        "retaliation_points": retaliation_points,
    }
    return augment_retaliation_analysis_with_sources(
        payload,
        case_scope=case_scope,
        multi_source_case_bundle=multi_source_case_bundle,
    )


def _target_actor_id(case_bundle: dict[str, Any] | None) -> str:
    scope = _as_dict((case_bundle or {}).get("scope"))
    return str(_as_dict(scope.get("target_person")).get("actor_id") or "")


def _trigger_event_payload(trigger_event: Any, candidates: list[dict[str, Any]], target_actor_id: str) -> dict[str, Any] | None:
    trigger_date = _parse_iso_like(str(trigger_event.date))
    if trigger_date is None:
        return None
    before, after = _bucket_candidates(candidates, trigger_date=trigger_date)
    before_totals, after_totals = _candidate_totals(before), _candidate_totals(after)
    target_before = _targeted_message_count(before, target_actor_id=target_actor_id)
    target_after = _targeted_message_count(after, target_actor_id=target_actor_id)
    return {
        "trigger_type": str(trigger_event.trigger_type),
        "date": str(trigger_event.date),
        "actor": _trigger_actor(trigger_event),
        "notes": str(trigger_event.notes or ""),
        "before_after": _before_after_payload(
            before, after, before_totals, after_totals, target_before, target_after, candidates, trigger_date
        ),
        "assessment": _conditional_assessment(
            trigger_date=trigger_date,
            before_candidates=before,
            after_candidates=after,
            before_totals=before_totals,
            after_totals=after_totals,
            target_before=target_before,
            target_after=target_after,
        ),
        "evidence_chain": {"before_uids": _candidate_uids(before), "after_uids": _candidate_uids(after)},
        "_after_candidates": after,
    }


def _candidate_totals(candidates: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "escalation_rate": 0,
        "inclusion_changes": 0,
        "criticism_frequency": 0,
        "selective_non_response": 0,
        "demand_intensity": 0,
    }
    for candidate in candidates:
        for key, value in _adverse_counts(candidate).items():
            totals[key] += value
    return totals


def _trigger_actor(trigger_event: Any) -> dict[str, str] | None:
    actor = getattr(trigger_event, "actor", None)
    return {"name": str(actor.name), "email": str(actor.email or "")} if actor is not None else None


def _before_after_payload(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    before_totals: dict[str, int],
    after_totals: dict[str, int],
    target_before: int,
    target_after: int,
    all_candidates: list[dict[str, Any]],
    trigger_date: Any,
) -> dict[str, Any]:
    return {
        "before_message_count": len(before),
        "after_message_count": len(after),
        "targeted_message_count_before": target_before,
        "targeted_message_count_after": target_after,
        "metrics": _before_after_metrics(before, after, before_totals, after_totals),
        "bucket_balance": {
            "message_count_delta": len(after) - len(before),
            "window_status": "balanced" if abs(len(after) - len(before)) <= 1 else "imbalanced",
        },
        "window_breakdown": _window_breakdown(all_candidates, trigger_date=trigger_date),
    }


def _before_after_metrics(
    before: list[dict[str, Any]], after: list[dict[str, Any]], before_totals: dict[str, int], after_totals: dict[str, int]
) -> dict[str, Any]:
    metrics = {"response_time": _response_time_metric(before, after)}
    for key in ("escalation_rate", "inclusion_changes", "criticism_frequency", "selective_non_response", "demand_intensity"):
        metrics[key] = _rate_metric(before_totals[key], after_totals[key], before_messages=len(before), after_messages=len(after))
    return metrics


def _candidate_uids(candidates: list[dict[str, Any]]) -> list[str]:
    return [str(candidate.get("uid") or "") for candidate in candidates if candidate.get("uid")]
