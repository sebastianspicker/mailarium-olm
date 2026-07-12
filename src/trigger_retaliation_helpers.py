"""Shared helper primitives for retaliation-style timing analysis."""
# pylint: disable=too-many-locals

from __future__ import annotations

from collections import Counter
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
    candidate_rows, seen = _explicit_protected_rows(case_scope)
    _append_record_protected_rows(candidate_rows, seen, candidates)
    candidate_rows.sort(key=_protected_sort_key)
    return candidate_rows[:12]


def _explicit_protected_rows(case_scope: Any) -> tuple[list[dict[str, Any]], set[tuple[str, str, str]]]:
    rows: list[dict[str, Any]] = []
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
        rows.append(
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

    return rows, seen


def _append_record_protected_rows(
    rows: list[dict[str, Any]], seen: set[tuple[str, str, str]], candidates: list[dict[str, Any]]
) -> None:
    for candidate in candidates:
        text = _candidate_text(candidate)
        if not text:
            continue
        candidate_type, matched_keyword = _protected_rule(text)
        date_text, uid = str(candidate.get("date") or ""), str(candidate.get("uid") or "")
        key = (candidate_type, date_text, uid)
        if not matched_keyword or key in seen:
            continue
        seen.add(key)
        rows.append(
            _record_protected_row(candidate_type, date_text, uid, _source_ids(candidate), text, matched_keyword, len(rows) + 1)
        )


def _protected_rule(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for candidate_type, keywords in _PROTECTED_ACTIVITY_RULES:
        keyword = next((item for item in keywords if item in lowered), "")
        if keyword:
            return candidate_type, keyword
    return "", ""


def _source_ids(candidate: dict[str, Any]) -> list[str]:
    source_id = str(candidate.get("source_id") or "").strip()
    return [source_id] if source_id else []


def _record_protected_row(
    candidate_type: str, date_text: str, uid: str, source_ids: list[str], text: str, keyword: str, index: int
) -> dict[str, Any]:
    dated = _parse_iso_like(date_text) is not None
    return {
        "candidate_id": f"protected_activity:{candidate_type}:{index}",
        "candidate_type": candidate_type,
        "date": date_text,
        "date_confidence": "exact" if dated else "missing",
        "confidence": "medium" if dated else "low",
        "source_kind": "record_derived_candidate",
        "source_span": _source_span(text, keyword),
        "source_linkage": {"supporting_uids": [uid] if uid else [], "source_ids": source_ids},
        "requires_confirmation": True,
        "promotion_rule": "review_facing_only_explicit_trigger_confirmation_required",
    }


def _protected_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    confidence = str(item.get("confidence") or "")
    rank = {"high": 0, "medium": 1}.get(confidence, 2)
    return rank, str(item.get("date") or ""), str(item.get("candidate_id") or "")


def _adverse_action_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        text = _candidate_text(candidate)
        for action_type, matched_keyword in _derived_action_types(candidate, text):
            uid = str(candidate.get("uid") or "")
            date_text = str(candidate.get("date") or "")
            has_exact_date = _parse_iso_like(date_text) is not None
            key = (action_type, date_text, uid)
            if key in seen:
                continue
            seen.add(key)
            candidate_rows.append(
                _adverse_action_row(
                    action_type,
                    matched_keyword,
                    date_text,
                    uid,
                    _source_ids(candidate),
                    text,
                    has_exact_date,
                    len(candidate_rows) + 1,
                )
            )
    candidate_rows.sort(key=_adverse_sort_key)
    return candidate_rows[:12]


def _adverse_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    return (
        0 if str(item.get("confidence") or "") == "medium" else 1,
        str(item.get("date") or ""),
        str(item.get("candidate_id") or ""),
    )


def _derived_action_types(candidate: dict[str, Any], text: str) -> list[tuple[str, str]]:
    lowered = text.lower()
    actions: list[tuple[str, str]] = []
    for action_type, keywords in _ADVERSE_ACTION_RULES:
        keyword = next((item for item in keywords if item in lowered), "")
        if keyword:
            actions.append((action_type, keyword))
    if not actions and set(_behavior_ids(candidate)) & {"exclusion", "withholding"}:
        actions.append(("participation_exclusion", "behavior_signal"))
    return actions


def _adverse_action_row(
    action_type: str,
    keyword: str,
    date_text: str,
    uid: str,
    source_ids: list[str],
    text: str,
    dated: bool,
    index: int,
) -> dict[str, Any]:
    behavior_signal = keyword == "behavior_signal"
    return {
        "candidate_id": f"adverse_action:{action_type}:{index}",
        "action_type": action_type,
        "date": date_text,
        "date_confidence": "exact" if dated else "missing",
        "confidence": "medium" if not behavior_signal and dated else "low",
        "source_kind": "record_derived_candidate",
        "source_span": text[:180] if behavior_signal else _source_span(text, keyword),
        "source_linkage": {"supporting_uids": [uid] if uid else [], "source_ids": source_ids},
        "candidate_basis": "behavior_signal" if behavior_signal else "direct_text_keyword",
        "requires_confirmation": True,
        "promotion_rule": "review_facing_only_explicit_adverse_action_confirmation_required",
    }


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
    pairings = _expected_reply_pairings(candidates)
    delays = _reply_delays(pairings)
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


def _expected_reply_pairings(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairings: list[dict[str, Any]] = []
    for candidate in candidates:
        pairing = candidate.get("reply_pairing") if isinstance(candidate, dict) else None
        if isinstance(pairing, dict) and pairing.get("request_expected") and pairing.get("target_authored_request"):
            pairings.append(pairing)
    return pairings


def _reply_delays(pairings: list[dict[str, Any]]) -> list[float]:
    return [
        float(value)
        for item in pairings
        if item.get("response_status") in {"direct_reply", "delayed_reply"}
        if isinstance((value := item.get("response_delay_hours")), int | float | str)
    ]


def _response_time_metric(before_candidates: list[dict[str, Any]], after_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    before = _response_metrics(before_candidates)
    after = _response_metrics(after_candidates)
    before_avg = before.get("average_hours")
    after_avg = after.get("average_hours")
    delta = round(float(after_avg) - float(before_avg), 2) if before_avg is not None and after_avg is not None else None
    status = _combined_response_status(str(before["status"]), str(after["status"]))
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


def _combined_response_status(before: str, after: str) -> str:
    if "observed" in {before, after}:
        return "observed"
    if "no_direct_replies_observed" in {before, after}:
        return "no_direct_replies_observed"
    return "no_reply_expected_messages"


def _adverse_counts(candidate: dict[str, Any]) -> dict[str, int]:
    findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    behavior_ids = [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict)
    ]
    counts = Counter(behavior_ids)
    return {
        "escalation_rate": counts["escalation"],
        "inclusion_changes": counts["exclusion"] + counts["withholding"],
        "criticism_frequency": counts["public_correction"] + counts["undermining"],
        "selective_non_response": counts["selective_non_response"],
        "demand_intensity": counts["deadline_pressure"] + counts["selective_accountability"] + counts["escalation"],
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
            changes.extend(_response_metric_changes(payload))
            continue
        change = _rate_metric_change(metric_name, payload)
        if change is not None:
            changes.append(change)
    return changes[:4]


def _response_metric_changes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    delta_hours = payload.get("delta_hours")
    if isinstance(delta_hours, int | float) and delta_hours > 0:
        changes.append(
            {
                "metric": "response_time",
                "direction": "slower_after_trigger",
                "magnitude": round(float(delta_hours), 2),
                "reason": "Average observed reply delay increased after the trigger event.",
            }
        )
    after = int(payload.get("after_selective_non_response_count") or 0)
    before = int(payload.get("before_selective_non_response_count") or 0)
    if after > before:
        changes.append(
            {
                "metric": "selective_non_response",
                "direction": "higher_after_trigger",
                "magnitude": after - before,
                "reason": "Selective non-response indicators increased after the trigger event.",
            }
        )
    return changes


def _rate_metric_change(metric_name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    rate_delta, delta = payload.get("rate_delta"), payload.get("delta")
    if isinstance(rate_delta, int | float) and rate_delta > 0:
        return {
            "metric": metric_name,
            "direction": "higher_after_trigger",
            "magnitude": round(float(rate_delta), 3),
            "reason": f"Normalized {metric_name.replace('_', ' ')} increased after the trigger event.",
        }
    if isinstance(delta, int | float) and delta > 0:
        return {
            "metric": metric_name,
            "direction": "higher_after_trigger",
            "magnitude": delta,
            "reason": f"Raw {metric_name.replace('_', ' ')} increased after the trigger event.",
        }
    return None


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
