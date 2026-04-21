"""Trigger-event and retaliation-style before/after analysis helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

RETALIATION_ANALYSIS_VERSION = "1"


def _parse_iso_like(value: str) -> datetime | None:
    """Parse one ISO-like date or timestamp for stable ordering."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _metric(before: int, after: int) -> dict[str, Any]:
    """Return a compact before/after metric payload."""
    return {
        "before": before,
        "after": after,
        "delta": after - before,
        "changed": before != after,
    }


def _response_time_metric() -> dict[str, Any]:
    """Return the current BA8 response-time placeholder contract."""
    return {
        "status": "not_available",
        "reason": "Response-time deltas require explicit request-response pairing that is not yet modeled.",
    }


def _adverse_counts(candidate: dict[str, Any]) -> dict[str, int]:
    """Return message-local adverse-behaviour counters for one candidate."""
    findings = ((candidate.get("message_findings") or {}).get("authored_text") or {})
    behavior_ids = [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict)
    ]
    return {
        "escalation_rate": sum(1 for behavior_id in behavior_ids if behavior_id == "escalation"),
        "inclusion_changes": sum(1 for behavior_id in behavior_ids if behavior_id in {"exclusion", "withholding"}),
        "criticism_frequency": sum(1 for behavior_id in behavior_ids if behavior_id in {"public_correction", "undermining"}),
        "demand_intensity": sum(
            1 for behavior_id in behavior_ids if behavior_id in {"deadline_pressure", "selective_accountability", "escalation"}
        ),
    }


def _targeted_message_count(candidates: list[dict[str, Any]], *, target_actor_id: str) -> int:
    """Return the number of messages tied to the same target actor."""
    if not target_actor_id:
        return 0
    count = 0
    for candidate in candidates:
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        if not sender_actor_id:
            continue
        if sender_actor_id == target_actor_id:
            continue
        findings = ((candidate.get("message_findings") or {}).get("authored_text") or {})
        if findings.get("behavior_candidate_count"):
            count += 1
    return count


def _bucket_candidates(
    candidates: list[dict[str, Any]],
    *,
    trigger_date: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split candidates into before and after buckets relative to one trigger date."""
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    for candidate in candidates:
        parsed_date = _parse_iso_like(str(candidate.get("date") or ""))
        if parsed_date is None:
            continue
        if parsed_date < trigger_date:
            before.append(candidate)
        else:
            after.append(candidate)
    return before, after


def _conditional_assessment(
    *,
    before_candidates: list[dict[str, Any]],
    after_candidates: list[dict[str, Any]],
    before_totals: dict[str, int],
    after_totals: dict[str, int],
) -> dict[str, str]:
    """Return a cautious retaliation-style interpretation block."""
    if not before_candidates or not after_candidates:
        return {
            "status": "insufficient_context",
            "reason": "Need both before and after evidence to assess trigger-linked change.",
        }
    adverse_before = sum(before_totals.values())
    adverse_after = sum(after_totals.values())
    if adverse_after > adverse_before:
        return {
            "status": "possible_retaliatory_shift",
            "reason": (
                "Adverse message-level behaviour counts increased after the "
                "trigger event, but comparator support is still missing."
            ),
        }
    if adverse_after == adverse_before:
        return {
            "status": "no_clear_shift",
            "reason": "Before/after adverse behaviour totals are stable on the current message set.",
        }
    return {
        "status": "no_clear_shift",
        "reason": "Adverse message-level behaviour counts did not increase after the trigger event.",
    }


def build_retaliation_analysis(
    *,
    case_scope: Any,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return explicit trigger-event and before/after retaliation-style analysis."""
    trigger_events = list(getattr(case_scope, "trigger_events", []) or [])
    if not trigger_events:
        return None
    target_actor_id = ""
    if case_bundle is not None and isinstance(case_bundle.get("scope"), dict):
        target_actor_id = str((((case_bundle.get("scope") or {}).get("target_person") or {}).get("actor_id")) or "")
    events_payload: list[dict[str, Any]] = []
    for trigger_event in trigger_events:
        trigger_date = _parse_iso_like(str(trigger_event.date))
        if trigger_date is None:
            continue
        before_candidates, after_candidates = _bucket_candidates(candidates, trigger_date=trigger_date)
        before_totals = {
            "escalation_rate": 0,
            "inclusion_changes": 0,
            "criticism_frequency": 0,
            "demand_intensity": 0,
        }
        after_totals = dict(before_totals)
        for candidate in before_candidates:
            for key, value in _adverse_counts(candidate).items():
                before_totals[key] += value
        for candidate in after_candidates:
            for key, value in _adverse_counts(candidate).items():
                after_totals[key] += value
        events_payload.append(
            {
                "trigger_type": str(trigger_event.trigger_type),
                "date": str(trigger_event.date),
                "actor": {
                    "name": str(trigger_event.actor.name),
                    "email": str(trigger_event.actor.email or ""),
                }
                if getattr(trigger_event, "actor", None) is not None
                else None,
                "notes": str(trigger_event.notes or ""),
                "before_after": {
                    "before_message_count": len(before_candidates),
                    "after_message_count": len(after_candidates),
                    "targeted_message_count_before": _targeted_message_count(before_candidates, target_actor_id=target_actor_id),
                    "targeted_message_count_after": _targeted_message_count(after_candidates, target_actor_id=target_actor_id),
                    "metrics": {
                        "response_time": _response_time_metric(),
                        "escalation_rate": _metric(before_totals["escalation_rate"], after_totals["escalation_rate"]),
                        "inclusion_changes": _metric(before_totals["inclusion_changes"], after_totals["inclusion_changes"]),
                        "criticism_frequency": _metric(
                            before_totals["criticism_frequency"], after_totals["criticism_frequency"]
                        ),
                        "demand_intensity": _metric(before_totals["demand_intensity"], after_totals["demand_intensity"]),
                    },
                },
                "assessment": _conditional_assessment(
                    before_candidates=before_candidates,
                    after_candidates=after_candidates,
                    before_totals=before_totals,
                    after_totals=after_totals,
                ),
                "evidence_chain": {
                    "before_uids": [str(candidate.get("uid") or "") for candidate in before_candidates if candidate.get("uid")],
                    "after_uids": [str(candidate.get("uid") or "") for candidate in after_candidates if candidate.get("uid")],
                },
            }
        )
    return {
        "version": RETALIATION_ANALYSIS_VERSION,
        "trigger_event_count": len(events_payload),
        "trigger_events": events_payload,
    }
