"""Shared helper primitives for retaliation-style timing analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any

RETALIATION_ANALYSIS_VERSION = "1"

_PROTECTED_ACTIVITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("complaint", ("complaint", "grievance", "beschwerde", "formal complaint", "formal grievance")),
    ("escalation_to_hr", ("hr", "human resources", "hr-mailbox", "escalation")),
    ("illness_disability_disclosure", ("disability", "behinderung", "illness", "medical", "gesundheit")),
    ("objection_refusal", ("objection", "widerspruch", "refusal", "refused", "declined")),
    ("rights_assertion", ("right", "rights", "sbv", "personalrat", "betriebsrat", "lpvg", "accommodation")),
)
_ADVERSE_ACTION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("task_withdrawal", ("task withdrawal", "aufgabenentzug", "td fixation", "tätigkeitsdarstellung")),
    ("project_removal", ("project removal", "project withdrawn", "removed from project", "projekt entzogen")),
    ("participation_exclusion", ("excluded from process", "without sbv", "ohne sbv", "not included", "left out")),
    ("mobile_work_restriction", ("home office", "mobile work", "remote work denied", "home office restriction")),
    ("attendance_control", ("time system", "attendance control", "worktime control", "arbeitszeitkontrolle", "surveillance")),
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_iso_like(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _metric(before: int, after: int) -> dict[str, Any]:
    return {"before": before, "after": after, "delta": after - before, "changed": before != after}


def _normalized_subject(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.removeprefix("re:").removeprefix("fw:").removeprefix("fwd:").removeprefix("aw:").removeprefix("wg:")
    return " ".join(normalized.split())


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("subject", "snippet", "text_preview", "body_preview", "title"):
        value = str(candidate.get(field) or "").strip()
        if value:
            parts.append(value)
    return " ".join(parts)


def _source_span(text: str, keyword: str) -> str:
    lowered = text.lower()
    index = lowered.find(keyword.lower())
    if index < 0:
        return text[:180]
    start = max(0, index - 60)
    end = min(len(text), index + len(keyword) + 90)
    return text[start:end].strip()


def _empty_timeline_assessment() -> dict[str, Any]:
    return {
        "version": RETALIATION_ANALYSIS_VERSION,
        "protected_activity_timeline": [],
        "adverse_action_timeline": [],
        "temporal_correlation_analysis": [],
        "strongest_retaliation_indicators": [],
        "strongest_non_retaliatory_explanations": [],
        "overall_evidentiary_rating": {
            "rating": "insufficient_timing_record",
            "reason": "No explicit confirmed trigger event is available for before/after retaliation analysis.",
        },
    }


def _behavior_ids(candidate: dict[str, Any]) -> list[str]:
    findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    return [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict) and str(behavior.get("behavior_id") or "")
    ]


def _protected_activity_candidates(case_scope: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    explicit_events = [
        *list(getattr(case_scope, "trigger_events", []) or []),
        *list(getattr(case_scope, "asserted_rights_timeline", []) or []),
    ]
    for index, event in enumerate(explicit_events, start=1):
        trigger_type = str(getattr(event, "trigger_type", "") or "")
        date_text = str(getattr(event, "date", "") or "")
        key = (trigger_type, date_text, "explicit_scope_event")
        if key in seen:
            continue
        seen.add(key)
        candidate_rows.append(
            {
                "candidate_id": f"protected_activity:explicit:{index}",
                "candidate_type": trigger_type or "protected_activity",
                "date": date_text,
                "date_confidence": "exact" if date_text else "missing",
                "confidence": "high" if date_text else "medium",
                "source_kind": "explicit_case_scope_event",
                "source_span": str(getattr(event, "notes", "") or trigger_type or "").strip(),
                "source_linkage": {"supporting_uids": [], "source_ids": []},
                "requires_confirmation": False,
                "promotion_rule": "already_structured_case_scope_event",
            }
        )

    for candidate in candidates:
        text = _candidate_text(candidate)
        if not text:
            continue
        lowered = text.lower()
        for candidate_type, keywords in _PROTECTED_ACTIVITY_RULES:
            matched_keyword = next((keyword for keyword in keywords if keyword in lowered), "")
            if not matched_keyword:
                continue
            date_text = str(candidate.get("date") or "")
            uid = str(candidate.get("uid") or "")
            key = (candidate_type, date_text, uid)
            if key in seen:
                continue
            seen.add(key)
            source_ids = [str(item) for item in [candidate.get("source_id")] if str(item or "").strip()]
            candidate_rows.append(
                {
                    "candidate_id": f"protected_activity:{candidate_type}:{len(candidate_rows) + 1}",
                    "candidate_type": candidate_type,
                    "date": date_text,
                    "date_confidence": "exact" if _parse_iso_like(date_text) is not None else "missing",
                    "confidence": "medium" if _parse_iso_like(date_text) is not None else "low",
                    "source_kind": "record_derived_candidate",
                    "source_span": _source_span(text, matched_keyword),
                    "source_linkage": {
                        "supporting_uids": [uid] if uid else [],
                        "source_ids": source_ids,
                    },
                    "requires_confirmation": True,
                    "promotion_rule": "review_facing_only_explicit_trigger_confirmation_required",
                }
            )
            break
    candidate_rows.sort(
        key=lambda item: (
            0 if str(item.get("confidence") or "") == "high" else 1 if str(item.get("confidence") or "") == "medium" else 2,
            str(item.get("date") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    return candidate_rows[:12]


def _adverse_action_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        text = _candidate_text(candidate)
        lowered = text.lower()
        behavior_ids = set(_behavior_ids(candidate))
        derived_action_types: list[tuple[str, str]] = []
        for action_type, keywords in _ADVERSE_ACTION_RULES:
            matched_keyword = next((keyword for keyword in keywords if keyword in lowered), "")
            if matched_keyword:
                derived_action_types.append((action_type, matched_keyword))
        if not derived_action_types and behavior_ids & {"exclusion", "withholding"}:
            derived_action_types.append(("participation_exclusion", "behavior_signal"))
        for action_type, matched_keyword in derived_action_types:
            uid = str(candidate.get("uid") or "")
            date_text = str(candidate.get("date") or "")
            has_exact_date = _parse_iso_like(date_text) is not None
            key = (action_type, date_text, uid)
            if key in seen:
                continue
            seen.add(key)
            source_ids = [str(item) for item in [candidate.get("source_id")] if str(item or "").strip()]
            candidate_rows.append(
                {
                    "candidate_id": f"adverse_action:{action_type}:{len(candidate_rows) + 1}",
                    "action_type": action_type,
                    "date": date_text,
                    "date_confidence": "exact" if has_exact_date else "missing",
                    "confidence": "medium" if matched_keyword != "behavior_signal" and has_exact_date else "low",
                    "source_kind": "record_derived_candidate",
                    "source_span": _source_span(text, matched_keyword) if matched_keyword != "behavior_signal" else text[:180],
                    "source_linkage": {"supporting_uids": [uid] if uid else [], "source_ids": source_ids},
                    "candidate_basis": "behavior_signal" if matched_keyword == "behavior_signal" else "direct_text_keyword",
                    "requires_confirmation": True,
                    "promotion_rule": "review_facing_only_explicit_adverse_action_confirmation_required",
                }
            )
    candidate_rows.sort(
        key=lambda item: (
            0 if str(item.get("confidence") or "") == "medium" else 1,
            str(item.get("date") or ""),
            str(item.get("candidate_id") or ""),
        )
    )
    return candidate_rows[:12]


def _rate_metric(before: int, after: int, *, before_messages: int, after_messages: int) -> dict[str, Any]:
    before_rate = round(before / before_messages, 3) if before_messages > 0 else None
    after_rate = round(after / after_messages, 3) if after_messages > 0 else None
    rate_delta = round(after_rate - before_rate, 3) if before_rate is not None and after_rate is not None else None
    return {
        **_metric(before, after),
        "before_rate_per_message": before_rate,
        "after_rate_per_message": after_rate,
        "rate_delta": rate_delta,
    }


def _response_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    pairings = [
        pairing
        for pairing in (candidate.get("reply_pairing") for candidate in candidates if isinstance(candidate, dict))
        if isinstance(pairing, dict) and bool(pairing.get("request_expected")) and bool(pairing.get("target_authored_request"))
    ]
    delays: list[float] = []
    for pairing in pairings:
        if pairing.get("response_status") not in {"direct_reply", "delayed_reply"}:
            continue
        delay_value = pairing.get("response_delay_hours")
        if isinstance(delay_value, (int, float, str)):
            delays.append(float(delay_value))
    selective_non_response_count = sum(
        1 for pairing in pairings if bool(pairing.get("supports_selective_non_response_inference"))
    )
    if delays:
        return {
            "status": "observed",
            "request_expected_count": len(pairings),
            "direct_reply_count": len(delays),
            "delayed_reply_count": sum(1 for pairing in pairings if pairing.get("response_status") == "delayed_reply"),
            "average_hours": round(sum(delays) / len(delays), 2),
            "selective_non_response_count": selective_non_response_count,
        }
    if pairings:
        return {
            "status": "no_direct_replies_observed",
            "request_expected_count": len(pairings),
            "direct_reply_count": 0,
            "delayed_reply_count": 0,
            "average_hours": None,
            "selective_non_response_count": selective_non_response_count,
        }
    return {
        "status": "no_reply_expected_messages",
        "request_expected_count": 0,
        "direct_reply_count": 0,
        "delayed_reply_count": 0,
        "average_hours": None,
        "selective_non_response_count": 0,
    }


def _response_time_metric(before_candidates: list[dict[str, Any]], after_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    before = _response_metrics(before_candidates)
    after = _response_metrics(after_candidates)
    before_avg = before.get("average_hours")
    after_avg = after.get("average_hours")
    delta = round(float(after_avg) - float(before_avg), 2) if before_avg is not None and after_avg is not None else None
    status = (
        "observed"
        if before["status"] == "observed" or after["status"] == "observed"
        else "no_direct_replies_observed"
        if before["status"] == "no_direct_replies_observed" or after["status"] == "no_direct_replies_observed"
        else "no_reply_expected_messages"
    )
    return {
        "status": status,
        "before_average_hours": before_avg,
        "after_average_hours": after_avg,
        "delta_hours": delta,
        "before_request_expected_count": int(before.get("request_expected_count") or 0),
        "after_request_expected_count": int(after.get("request_expected_count") or 0),
        "before_direct_reply_count": int(before.get("direct_reply_count") or 0),
        "after_direct_reply_count": int(after.get("direct_reply_count") or 0),
        "before_selective_non_response_count": int(before.get("selective_non_response_count") or 0),
        "after_selective_non_response_count": int(after.get("selective_non_response_count") or 0),
    }


def _adverse_counts(candidate: dict[str, Any]) -> dict[str, int]:
    findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    behavior_ids = [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict)
    ]
    return {
        "escalation_rate": sum(1 for behavior_id in behavior_ids if behavior_id == "escalation"),
        "inclusion_changes": sum(1 for behavior_id in behavior_ids if behavior_id in {"exclusion", "withholding"}),
        "criticism_frequency": sum(1 for behavior_id in behavior_ids if behavior_id in {"public_correction", "undermining"}),
        "selective_non_response": sum(1 for behavior_id in behavior_ids if behavior_id == "selective_non_response"),
        "demand_intensity": sum(
            1 for behavior_id in behavior_ids if behavior_id in {"deadline_pressure", "selective_accountability", "escalation"}
        ),
    }


def _targeted_message_count(candidates: list[dict[str, Any]], *, target_actor_id: str) -> int:
    if not target_actor_id:
        return 0
    count = 0
    for candidate in candidates:
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        if not sender_actor_id or sender_actor_id == target_actor_id:
            continue
        findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
        if findings.get("behavior_candidate_count"):
            count += 1
    return count


def _strongest_metric_changes(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    metric_priority = (
        "selective_non_response",
        "response_time",
        "escalation_rate",
        "criticism_frequency",
        "inclusion_changes",
        "demand_intensity",
    )
    for metric_name in metric_priority:
        payload = metrics.get(metric_name)
        if not isinstance(payload, dict):
            continue
        if metric_name == "response_time":
            delta_hours = payload.get("delta_hours")
            if isinstance(delta_hours, (int, float)) and delta_hours > 0:
                changes.append(
                    {
                        "metric": metric_name,
                        "direction": "slower_after_trigger",
                        "magnitude": round(float(delta_hours), 2),
                        "reason": "Average observed reply delay increased after the trigger event.",
                    }
                )
            after_non_response = int(payload.get("after_selective_non_response_count") or 0)
            before_non_response = int(payload.get("before_selective_non_response_count") or 0)
            if after_non_response > before_non_response:
                changes.append(
                    {
                        "metric": "selective_non_response",
                        "direction": "higher_after_trigger",
                        "magnitude": after_non_response - before_non_response,
                        "reason": "Selective non-response indicators increased after the trigger event.",
                    }
                )
            continue
        rate_delta = payload.get("rate_delta")
        delta = payload.get("delta")
        if isinstance(rate_delta, (int, float)) and rate_delta > 0:
            changes.append(
                {
                    "metric": metric_name,
                    "direction": "higher_after_trigger",
                    "magnitude": round(float(rate_delta), 3),
                    "reason": f"Normalized {metric_name.replace('_', ' ')} increased after the trigger event.",
                }
            )
        elif isinstance(delta, (int, float)) and delta > 0:
            changes.append(
                {
                    "metric": metric_name,
                    "direction": "higher_after_trigger",
                    "magnitude": delta,
                    "reason": f"Raw {metric_name.replace('_', ' ')} increased after the trigger event.",
                }
            )
    return changes[:4]


def _days_from_trigger(trigger_date: datetime, candidate_date: str) -> int | None:
    parsed = _parse_iso_like(candidate_date)
    if parsed is None:
        return None
    return (parsed - trigger_date).days


def _candidate_timeline_entry(candidate: dict[str, Any], *, trigger_date: datetime) -> dict[str, Any]:
    adverse_signals = [
        behavior_id
        for behavior_id in _behavior_ids(candidate)
        if behavior_id in {"escalation", "deadline_pressure", "public_correction", "undermining", "selective_non_response"}
    ]
    return {
        "uid": str(candidate.get("uid") or ""),
        "date": str(candidate.get("date") or ""),
        "days_from_trigger": _days_from_trigger(trigger_date, str(candidate.get("date") or "")),
        "subject": str(candidate.get("subject") or ""),
        "sender_actor_id": str(candidate.get("sender_actor_id") or ""),
        "adverse_signals": adverse_signals,
    }


def _bucket_candidates(
    candidates: list[dict[str, Any]], *, trigger_date: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    for candidate in candidates:
        parsed = _parse_iso_like(str(candidate.get("date") or ""))
        if parsed is None:
            continue
        if parsed < trigger_date:
            before.append(candidate)
        elif parsed > trigger_date:
            after.append(candidate)
    return before, after


def _window_breakdown(candidates: list[dict[str, Any]], *, trigger_date: datetime) -> dict[str, Any]:
    immediate_after_uids: list[str] = []
    medium_term_uids: list[str] = []
    long_tail_uids: list[str] = []
    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        delta_days = _days_from_trigger(trigger_date, str(candidate.get("date") or ""))
        if delta_days is None or delta_days < 0 or not uid:
            continue
        if delta_days <= 7:
            immediate_after_uids.append(uid)
        elif delta_days <= 21:
            medium_term_uids.append(uid)
        else:
            long_tail_uids.append(uid)
    return {
        "immediate_after_count": len(immediate_after_uids),
        "medium_term_count": len(medium_term_uids),
        "long_tail_count": len(long_tail_uids),
        "immediate_after_uids": immediate_after_uids,
        "medium_term_uids": medium_term_uids,
        "long_tail_uids": long_tail_uids,
    }
