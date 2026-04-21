"""Trigger-event and retaliation-style before/after analysis helpers."""

from __future__ import annotations

from typing import Any

from . import trigger_retaliation_assessment as _assessment
from .trigger_retaliation_helpers import (
    RETALIATION_ANALYSIS_VERSION,
    _adverse_action_candidates,
    _adverse_counts,
    _as_dict,
    _as_list,
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


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


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

    explicit_trigger_events = [
        *list(getattr(case_scope, "trigger_events", []) or []),
        *list(getattr(case_scope, "asserted_rights_timeline", []) or []),
    ]
    source_protected_candidates = [
        row
        for row in _protected_activity_candidates(case_scope, source_candidates)
        if str(row.get("source_kind") or "") == "record_derived_candidate"
        and "after the complaint" not in _compact(row.get("source_span")).lower()
        and "nach der beschwerde" not in _compact(row.get("source_span")).lower()
    ]
    source_adverse_candidates = _adverse_action_candidates(source_candidates)
    if not source_protected_candidates and not source_adverse_candidates:
        return retaliation_analysis

    payload = dict(retaliation_analysis or {})
    protected_activity_candidates = _merge_candidate_rows(
        [
            *[row for row in payload.get("protected_activity_candidates") or [] if isinstance(row, dict)],
            *source_protected_candidates,
        ]
    )
    adverse_action_candidates = _merge_candidate_rows(
        [
            *[row for row in payload.get("adverse_action_candidates") or [] if isinstance(row, dict)],
            *source_adverse_candidates,
        ]
    )
    timeline_assessment = dict(payload.get("retaliation_timeline_assessment") or _empty_timeline_assessment())
    adverse_action_timeline = [row for row in timeline_assessment.get("adverse_action_timeline") or [] if isinstance(row, dict)]
    for trigger_event in explicit_trigger_events:
        trigger_date = _parse_iso_like(str(getattr(trigger_event, "date", "") or ""))
        if trigger_date is None:
            continue
        for adverse in source_adverse_candidates:
            adverse_date = _parse_iso_like(_compact(adverse.get("date")))
            if adverse_date is None or adverse_date <= trigger_date:
                continue
            source_ids = [
                str(item) for item in _as_list(_as_dict(adverse.get("source_linkage")).get("source_ids")) if str(item).strip()
            ]
            supporting_uids = [
                str(item)
                for item in _as_list(_as_dict(adverse.get("source_linkage")).get("supporting_uids"))
                if str(item).strip()
            ]
            timeline_row = _candidate_timeline_entry(
                {
                    "uid": supporting_uids[0] if supporting_uids else "",
                    "date": _compact(adverse.get("date")),
                    "subject": _compact(adverse.get("action_type")).replace("_", " "),
                },
                trigger_date=trigger_date,
            )
            timeline_row["source_id"] = source_ids[0] if source_ids else ""
            timeline_row["adverse_signals"] = [str(adverse.get("action_type") or "")]
            timeline_row["source_kind"] = "mixed_source_record"
            adverse_action_timeline.append(timeline_row)
    seen_timeline_keys: set[tuple[str, str, str]] = set()
    deduped_timeline: list[dict[str, Any]] = []
    for row in adverse_action_timeline:
        key = (_compact(row.get("uid")), _compact(row.get("source_id")), _compact(row.get("date")))
        if key in seen_timeline_keys:
            continue
        seen_timeline_keys.add(key)
        deduped_timeline.append(row)
    deduped_timeline.sort(
        key=lambda item: (
            _compact(item.get("date")),
            _compact(item.get("uid")),
            _compact(item.get("source_id")),
        )
    )
    timeline_assessment["adverse_action_timeline"] = deduped_timeline[:8]

    retaliation_points = [row for row in payload.get("retaliation_points") or [] if isinstance(row, dict)]
    retaliation_points.extend(
        _source_backed_retaliation_points(
            explicit_trigger_events=explicit_trigger_events,
            source_adverse_candidates=source_adverse_candidates,
        )
    )

    payload["protected_activity_candidate_count"] = len(protected_activity_candidates)
    payload["protected_activity_candidates"] = protected_activity_candidates
    payload["adverse_action_candidate_count"] = len(adverse_action_candidates)
    payload["adverse_action_candidates"] = adverse_action_candidates
    payload["retaliation_timeline_assessment"] = timeline_assessment
    payload["retaliation_points"] = retaliation_points
    payload["retaliation_point_count"] = len(retaliation_points)
    payload["source_backed_candidate_counts"] = {
        "protected_activity": len(source_protected_candidates),
        "adverse_actions": len(source_adverse_candidates),
    }
    if "version" not in payload:
        payload["version"] = RETALIATION_ANALYSIS_VERSION
    if "anchor_requirement_status" not in payload:
        payload["anchor_requirement_status"] = (
            "explicit_trigger_confirmed" if explicit_trigger_events else "explicit_trigger_confirmation_required"
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

    target_actor_id = ""
    if case_bundle is not None and isinstance(case_bundle.get("scope"), dict):
        target_actor_id = str((((case_bundle.get("scope") or {}).get("target_person") or {}).get("actor_id")) or "")

    events_payload: list[dict[str, Any]] = []
    for trigger_event in explicit_trigger_events:
        trigger_date = _parse_iso_like(str(trigger_event.date))
        if trigger_date is None:
            continue
        before_candidates, after_candidates = _bucket_candidates(candidates, trigger_date=trigger_date)
        window_breakdown = _window_breakdown(candidates, trigger_date=trigger_date)
        before_totals = {
            "escalation_rate": 0,
            "inclusion_changes": 0,
            "criticism_frequency": 0,
            "selective_non_response": 0,
            "demand_intensity": 0,
        }
        after_totals = dict(before_totals)
        for candidate in before_candidates:
            for key, value in _adverse_counts(candidate).items():
                before_totals[key] += value
        for candidate in after_candidates:
            for key, value in _adverse_counts(candidate).items():
                after_totals[key] += value

        target_before = _targeted_message_count(before_candidates, target_actor_id=target_actor_id)
        target_after = _targeted_message_count(after_candidates, target_actor_id=target_actor_id)
        event_payload: dict[str, Any] = {
            "trigger_type": str(trigger_event.trigger_type),
            "date": str(trigger_event.date),
            "actor": (
                {"name": str(trigger_event.actor.name), "email": str(trigger_event.actor.email or "")}
                if getattr(trigger_event, "actor", None) is not None
                else None
            ),
            "notes": str(trigger_event.notes or ""),
            "before_after": {
                "before_message_count": len(before_candidates),
                "after_message_count": len(after_candidates),
                "targeted_message_count_before": target_before,
                "targeted_message_count_after": target_after,
                "metrics": {
                    "response_time": _response_time_metric(before_candidates, after_candidates),
                    "escalation_rate": _rate_metric(
                        before_totals["escalation_rate"],
                        after_totals["escalation_rate"],
                        before_messages=len(before_candidates),
                        after_messages=len(after_candidates),
                    ),
                    "inclusion_changes": _rate_metric(
                        before_totals["inclusion_changes"],
                        after_totals["inclusion_changes"],
                        before_messages=len(before_candidates),
                        after_messages=len(after_candidates),
                    ),
                    "criticism_frequency": _rate_metric(
                        before_totals["criticism_frequency"],
                        after_totals["criticism_frequency"],
                        before_messages=len(before_candidates),
                        after_messages=len(after_candidates),
                    ),
                    "selective_non_response": _rate_metric(
                        before_totals["selective_non_response"],
                        after_totals["selective_non_response"],
                        before_messages=len(before_candidates),
                        after_messages=len(after_candidates),
                    ),
                    "demand_intensity": _rate_metric(
                        before_totals["demand_intensity"],
                        after_totals["demand_intensity"],
                        before_messages=len(before_candidates),
                        after_messages=len(after_candidates),
                    ),
                },
                "bucket_balance": {
                    "message_count_delta": len(after_candidates) - len(before_candidates),
                    "window_status": "balanced" if abs(len(after_candidates) - len(before_candidates)) <= 1 else "imbalanced",
                },
                "window_breakdown": window_breakdown,
            },
            "assessment": _conditional_assessment(
                trigger_date=trigger_date,
                before_candidates=before_candidates,
                after_candidates=after_candidates,
                before_totals=before_totals,
                after_totals=after_totals,
                target_before=target_before,
                target_after=target_after,
            ),
            "evidence_chain": {
                "before_uids": [str(candidate.get("uid") or "") for candidate in before_candidates if candidate.get("uid")],
                "after_uids": [str(candidate.get("uid") or "") for candidate in after_candidates if candidate.get("uid")],
            },
            "_after_candidates": after_candidates,
        }
        events_payload.append(event_payload)

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
