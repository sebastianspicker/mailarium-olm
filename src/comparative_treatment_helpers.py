"""Helper functions for comparative-treatment analysis."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from typing import Any

COMPARATIVE_TREATMENT_VERSION = "2"

_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")

COMPARATOR_ISSUE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "issue_id": "mobile_work_approvals_or_restrictions",
        "issue_label": "Mobile work approvals or restrictions",
        "evidence_needed_to_strengthen_point": [
            "Target and comparator decisions on remote/mobile work requests.",
            "Same-role policy or practice records for remote-work handling.",
        ],
        "significance": "May support unequal-treatment review if the same decision-maker applied different flexibility rules.",
    },
    {
        "issue_id": "formality_of_application_requirements",
        "issue_label": "Formality of application requirements",
        "evidence_needed_to_strengthen_point": [
            "Comparable application/request messages for both the claimant and comparator.",
            "Policy text describing required formal steps for the relevant process.",
        ],
        "significance": "May show one person was held to stricter process requirements than a comparator.",
    },
    {
        "issue_id": "control_intensity",
        "issue_label": "Control intensity",
        "evidence_needed_to_strengthen_point": [
            "More same-sender messages to both sides in a similar workflow stage.",
            "Comparable role or process context for the claimant and comparator.",
        ],
        "significance": (
            "May support unequal-treatment review where the same sender used materially harsher "
            "control cues against the claimant."
        ),
    },
    {
        "issue_id": "project_allocation",
        "issue_label": "Project allocation",
        "evidence_needed_to_strengthen_point": [
            "Task/project assignment records for both the claimant and comparator.",
            "Role or workload evidence showing comparability.",
        ],
        "significance": "May matter if comparable staff received materially different work allocation.",
    },
    {
        "issue_id": "training_or_development_opportunities",
        "issue_label": "Training or development opportunities",
        "evidence_needed_to_strengthen_point": [
            "Training approvals, invitations, or refusals for both sides.",
            "Comparable eligibility or role-development records.",
        ],
        "significance": "May matter if one person received fewer development opportunities than a comparator.",
    },
    {
        "issue_id": "sbv_or_pr_participation",
        "issue_label": "SBV or PR participation",
        "evidence_needed_to_strengthen_point": [
            "Participation or consultation records involving SBV, PR, or similar bodies.",
            "Comparable process records for the claimant and comparator.",
        ],
        "significance": "May matter if participation channels were handled differently across comparable cases.",
    },
    {
        "issue_id": "reaction_to_technical_incidents",
        "issue_label": "Reaction to technical incidents",
        "evidence_needed_to_strengthen_point": [
            "Comparable incident-response messages or ticket records for both sides.",
            "Technical incident chronology showing similar circumstances.",
        ],
        "significance": "May matter if technical problems triggered materially different managerial responses.",
    },
    {
        "issue_id": "flexibility_around_medical_needs",
        "issue_label": "Flexibility around medical needs",
        "evidence_needed_to_strengthen_point": [
            "Comparable accommodation, scheduling, or health-related requests.",
            "Role and attendance context for both the claimant and comparator.",
        ],
        "significance": "May matter where one side received less flexibility around health-related needs.",
    },
    {
        "issue_id": "treatment_after_complaints_or_rights_assertions",
        "issue_label": "Treatment after complaints or rights assertions",
        "evidence_needed_to_strengthen_point": [
            "Trigger-event chronology tied to the claimant and comparator.",
            "More before/after messages from the same sender in comparable contexts.",
        ],
        "significance": "May matter if treatment worsened after complaints, rights assertions, or protected participation.",
    },
)


def recipient_emails(full_email: dict[str, Any] | None) -> list[str]:
    emails: list[str] = []
    for field in ("to", "cc", "bcc"):
        for value in (full_email or {}).get(field) or []:
            match = _EMAIL_RE.search(str(value or ""))
            if not match:
                continue
            email = match.group(1).lower()
            if email not in emails:
                emails.append(email)
    return emails


def behavior_ids(candidate: dict[str, Any]) -> list[str]:
    findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    return [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict)
    ]


def normalized_subject(value: str) -> str:
    normalized = str(value or "").strip().lower()
    normalized = re.sub(r"^(re|fw|fwd|aw|wg)\s*:\s*", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def parse_day(value: str) -> date | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def recipient_count(candidate: dict[str, Any], full_map: dict[str, Any]) -> int:
    return len(recipient_emails(full_map.get(str(candidate.get("uid") or ""))))


def visibility_band(count: int) -> str:
    if count <= 1:
        return "direct_only"
    if count == 2:
        return "small_group"
    return "broad_visibility"


def metrics(candidates: list[dict[str, Any]], *, full_map: dict[str, Any]) -> dict[str, float | int]:
    tone_signal_count = sum(
        int(((candidate.get("language_rhetoric") or {}).get("authored_text") or {}).get("signal_count") or 0)
        for candidate in candidates
    )
    ids = [behavior_id for candidate in candidates for behavior_id in behavior_ids(candidate)]
    message_count = len(candidates)
    escalation_count = sum(1 for behavior_id in ids if behavior_id == "escalation")
    criticism_count = sum(1 for behavior_id in ids if behavior_id in {"public_correction", "undermining"})
    demand_intensity_count = sum(
        1 for behavior_id in ids if behavior_id in {"deadline_pressure", "selective_accountability", "escalation"}
    )
    procedural_pressure_count = sum(
        1 for behavior_id in ids if behavior_id in {"deadline_pressure", "selective_accountability", "withholding", "escalation"}
    )
    recipient_counts = [recipient_count(candidate, full_map) for candidate in candidates]
    multi_recipient_count = sum(1 for count in recipient_counts if count >= 2)
    response_delays = [
        float(candidate.get("reply_pairing", {}).get("response_delay_hours"))
        for candidate in candidates
        if isinstance(candidate.get("reply_pairing"), dict)
        and str(candidate["reply_pairing"].get("response_status") or "") in {"direct_reply", "delayed_reply"}
        and candidate["reply_pairing"].get("response_delay_hours") is not None
    ]
    return {
        "message_count": message_count,
        "tone_signal_count": tone_signal_count,
        "tone_signal_rate": round(tone_signal_count / message_count, 3) if message_count else 0.0,
        "escalation_count": escalation_count,
        "escalation_rate": round(escalation_count / message_count, 3) if message_count else 0.0,
        "criticism_count": criticism_count,
        "criticism_rate": round(criticism_count / message_count, 3) if message_count else 0.0,
        "demand_intensity_count": demand_intensity_count,
        "demand_intensity_rate": round(demand_intensity_count / message_count, 3) if message_count else 0.0,
        "procedural_pressure_count": procedural_pressure_count,
        "procedural_pressure_rate": round(procedural_pressure_count / message_count, 3) if message_count else 0.0,
        "average_visible_recipient_count": round(sum(recipient_counts) / message_count, 3) if message_count else 0.0,
        "multi_recipient_count": multi_recipient_count,
        "multi_recipient_rate": round(multi_recipient_count / message_count, 3) if message_count else 0.0,
        "response_delay_observation_count": len(response_delays),
        "average_response_delay_hours": round(sum(response_delays) / len(response_delays), 3) if response_delays else 0.0,
    }


def situation_tags(candidates: list[dict[str, Any]]) -> set[str]:
    tags: set[str] = set()
    for candidate in candidates:
        ids = set(behavior_ids(candidate))
        if ids & {"deadline_pressure", "selective_accountability"}:
            tags.add("request_type")
        if ids & {"public_correction", "undermining"}:
            tags.add("error_type")
        if "escalation" in ids:
            tags.add("escalation_context")
        if candidate.get("thread_group_id"):
            tags.add(f"thread:{candidate['thread_group_id']}")
        subject_family = normalized_subject(str(candidate.get("subject") or ""))
        if subject_family:
            tags.add(f"subject:{subject_family}")
    return tags


def workflow_stage(candidate: dict[str, Any]) -> str:
    ids = set(behavior_ids(candidate))
    subject_family = normalized_subject(str(candidate.get("subject") or ""))
    lowered_subject = subject_family.lower()
    if ids & {"deadline_pressure", "selective_accountability"}:
        return "request_or_compliance"
    if ids & {"public_correction", "undermining"}:
        return "error_or_correction"
    if "escalation" in ids:
        return "escalation"
    if any(token in lowered_subject for token in ("status", "update", "follow-up", "follow up")):
        return "status_or_follow_up"
    if any(token in lowered_subject for token in ("request", "antrag", "approval", "freigabe")):
        return "request_or_approval"
    return "generic"


def similarity_checks(
    target_candidates: list[dict[str, Any]], comparator_candidates: list[dict[str, Any]], *, full_map: dict[str, Any]
) -> dict[str, Any]:
    target_tags = situation_tags(target_candidates)
    comparator_tags = situation_tags(comparator_candidates)
    shared_tags = sorted(target_tags & comparator_tags)
    target_subjects = {
        normalized_subject(str(candidate.get("subject") or ""))
        for candidate in target_candidates
        if normalized_subject(str(candidate.get("subject") or ""))
    }
    comparator_subjects = {
        normalized_subject(str(candidate.get("subject") or ""))
        for candidate in comparator_candidates
        if normalized_subject(str(candidate.get("subject") or ""))
    }
    shared_subject = bool(target_subjects & comparator_subjects)
    target_days = [parsed for candidate in target_candidates if (parsed := parse_day(str(candidate.get("date") or "")))]
    comparator_days = [parsed for candidate in comparator_candidates if (parsed := parse_day(str(candidate.get("date") or "")))]
    shared_day = bool(set(target_days) & set(comparator_days))
    bounded_day_window = bool(
        target_days
        and comparator_days
        and min(abs((target_day - comparator_day).days) for target_day in target_days for comparator_day in comparator_days) <= 1
    )
    subject_overlap = sorted(target_subjects & comparator_subjects)
    process_step_overlap = any(tag.startswith("thread:") for tag in shared_tags) or bool(subject_overlap)
    shared_context_map = {
        "shared_request_type": "request_type",
        "shared_error_type": "error_type",
        "shared_escalation_context": "escalation_context",
    }
    target_workflow_stages = {
        workflow_stage(candidate) for candidate in target_candidates if workflow_stage(candidate) != "generic"
    }
    comparator_workflow_stages = {
        workflow_stage(candidate) for candidate in comparator_candidates if workflow_stage(candidate) != "generic"
    }
    shared_workflow_stage = bool(target_workflow_stages & comparator_workflow_stages)
    target_visibility_bands = {visibility_band(recipient_count(candidate, full_map)) for candidate in target_candidates}
    comparator_visibility_bands = {visibility_band(recipient_count(candidate, full_map)) for candidate in comparator_candidates}
    return {
        "shared_request_type": "request_type" in shared_tags,
        "shared_error_type": "error_type" in shared_tags,
        "shared_escalation_context": "escalation_context" in shared_tags,
        "shared_process_step": process_step_overlap,
        "shared_workflow_stage": shared_workflow_stage,
        "same_sender_decision_path": True,
        "shared_subject": shared_subject,
        "shared_subject_family": shared_subject,
        "shared_day": shared_day,
        "shared_day_window": bounded_day_window,
        "shared_visibility_band": bool(target_visibility_bands & comparator_visibility_bands),
        "shared_context_count": sum(
            1
            for key in ("shared_request_type", "shared_error_type", "shared_escalation_context")
            if shared_context_map[key] in shared_tags
        ),
        "shared_subject_families": subject_overlap,
        "shared_tags": shared_tags,
        "shared_workflow_stages": sorted(target_workflow_stages & comparator_workflow_stages),
        "shared_visibility_bands": sorted(target_visibility_bands & comparator_visibility_bands),
        "similarity_score": len(shared_tags)
        + int(shared_subject)
        + int(shared_day)
        + int(bounded_day_window)
        + int(shared_workflow_stage)
        + int(bool(target_visibility_bands & comparator_visibility_bands)),
    }


def comparison_quality(
    similarity: dict[str, Any], *, target_metrics: dict[str, float | int], comparator_metrics: dict[str, float | int]
) -> tuple[str, list[str]]:
    uncertainty_reasons: list[str] = []
    message_delta = abs(int(target_metrics.get("message_count") or 0) - int(comparator_metrics.get("message_count") or 0))
    if not bool(similarity.get("shared_process_step")):
        uncertainty_reasons.append("Target and comparator messages do not share a clear process step or thread.")
    if not bool(similarity.get("shared_subject")):
        uncertainty_reasons.append("Target and comparator messages do not share a normalized subject line.")
    if not bool(similarity.get("shared_workflow_stage")):
        uncertainty_reasons.append("Target and comparator messages do not share a clear workflow stage.")
    if not bool(similarity.get("shared_day")):
        uncertainty_reasons.append("Target and comparator messages do not occur on the same day in the current evidence set.")
    if not bool(similarity.get("shared_day_window")):
        uncertainty_reasons.append("Target and comparator messages do not fall within a bounded day window.")
    if not bool(similarity.get("shared_visibility_band")):
        uncertainty_reasons.append("Target and comparator messages do not share a similar visibility band.")
    if int(similarity.get("shared_context_count") or 0) == 0:
        uncertainty_reasons.append("Target and comparator messages do not share a clear request, error, or escalation context.")
    if message_delta >= 2:
        uncertainty_reasons.append("Target and comparator buckets are imbalanced in message count.")
    if (
        int(target_metrics.get("response_delay_observation_count") or 0) == 0
        or int(comparator_metrics.get("response_delay_observation_count") or 0) == 0
    ):
        uncertainty_reasons.append("Comparable reply-latency evidence is not available for both sides in the current record.")

    similarity_score = int(similarity.get("similarity_score") or 0)
    if (
        similarity_score >= 4
        and message_delta <= 1
        and bool(similarity.get("shared_process_step"))
        and bool(similarity.get("shared_workflow_stage"))
        and bool(similarity.get("shared_day_window"))
        and bool(similarity.get("shared_visibility_band"))
        and int(similarity.get("shared_context_count") or 0) >= 1
    ):
        quality = "high"
    elif similarity_score >= 3:
        quality = "partial"
    else:
        quality = "weak"
    return quality, uncertainty_reasons


def scope_text(scope: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("analysis_goal", "context_notes"):
        value = str(scope.get(field) or "").strip()
        if value:
            parts.append(value)
    for field in ("allegation_focus", "employment_issue_tags", "employment_issue_tracks"):
        for item in scope.get(field, []) or []:
            text = str(item or "").strip()
            if text:
                parts.append(text)
    for event in scope.get("trigger_events", []) or []:
        if isinstance(event, dict):
            parts.append(str(event.get("trigger_type") or ""))
            parts.append(str(event.get("summary") or ""))
    return " ".join(parts).lower()


def comparator_discovery_candidates(
    *, scope: dict[str, Any], candidates: list[dict[str, Any]], full_map: dict[str, Any]
) -> list[dict[str, Any]]:
    target = scope.get("target_person") if isinstance(scope.get("target_person"), dict) else {}
    target_email = str((target or {}).get("email") or "").lower()
    named_comparator_emails = {
        str(item.get("email") or "").lower()
        for item in scope.get("comparator_actors", []) or []
        if isinstance(item, dict) and str(item.get("email") or "").strip()
    }
    named_comparator_actor_ids = {
        str(item.get("actor_id") or "")
        for item in scope.get("comparator_actors", []) or []
        if isinstance(item, dict) and str(item.get("actor_id") or "").strip()
    }
    by_email: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        subject = normalized_subject(str(candidate.get("subject") or ""))
        day = parse_day(str(candidate.get("date") or ""))
        recipients = recipient_emails(full_map.get(str(candidate.get("uid") or "")))
        if target_email and target_email not in recipients:
            continue
        for other in candidates:
            if other is candidate or str(other.get("sender_actor_id") or "") != sender_actor_id:
                continue
            other_uid = str(other.get("uid") or "")
            other_recipients = recipient_emails(full_map.get(other_uid))
            other_subject = normalized_subject(str(other.get("subject") or ""))
            other_day = parse_day(str(other.get("date") or ""))
            for recipient_email in other_recipients:
                if not recipient_email or recipient_email == target_email or recipient_email in named_comparator_emails:
                    continue
                if (
                    subject
                    and other_subject
                    and subject != other_subject
                    and not (day and other_day and abs((day - other_day).days) <= 1)
                ):
                    continue
                row = by_email.setdefault(
                    recipient_email,
                    {
                        "email": recipient_email,
                        "evidence_uids": [],
                        "shared_sender_actor_ids": [],
                        "shared_subject_families": [],
                        "shared_day_window_count": 0,
                    },
                )
                if other_uid and other_uid not in row["evidence_uids"]:
                    row["evidence_uids"].append(other_uid)
                if sender_actor_id and sender_actor_id not in row["shared_sender_actor_ids"]:
                    row["shared_sender_actor_ids"].append(sender_actor_id)
                if other_subject and other_subject not in row["shared_subject_families"]:
                    row["shared_subject_families"].append(other_subject)
                if day and other_day and abs((day - other_day).days) <= 1:
                    row["shared_day_window_count"] += 1
    result: list[dict[str, Any]] = []
    for email, row in by_email.items():
        if email == target_email:
            continue
        actor_id = ""
        for comparator in scope.get("comparator_actors", []) or []:
            if isinstance(comparator, dict) and str(comparator.get("email") or "").lower() == email:
                actor_id = str(comparator.get("actor_id") or "")
                break
        if actor_id and actor_id in named_comparator_actor_ids:
            continue
        confidence = "medium" if row["shared_day_window_count"] >= 1 and row["shared_subject_families"] else "low"
        result.append(
            {
                "candidate_email": email,
                "candidate_actor_id": actor_id,
                "evidence_uids": row["evidence_uids"][:5],
                "shared_sender_actor_ids": row["shared_sender_actor_ids"][:3],
                "shared_subject_families": row["shared_subject_families"][:3],
                "shared_day_window_count": int(row["shared_day_window_count"]),
                "confidence": confidence,
                "promotion_rule": "review_facing_only_explicit_comparator_override_required",
            }
        )
    result.sort(
        key=lambda item: (
            0 if str(item.get("confidence") or "") == "medium" else 1,
            -len(item.get("evidence_uids", [])),
            str(item.get("candidate_email") or ""),
        )
    )
    return result[:10]


def shared_comparator_points_from_summaries(comparator_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from .comparative_treatment_matrix import shared_comparator_points_from_summaries as _shared_points

    return _shared_points(comparator_summaries)


def compare_treatment(
    *, scope: dict[str, Any], candidates: list[dict[str, Any]], full_map: dict[str, Any], target_actor_id: str
) -> dict[str, Any]:
    from .comparative_treatment_runtime import compare_treatment as _compare_treatment

    helpers = sys.modules[__name__]
    return _compare_treatment(
        scope=scope,
        candidates=candidates,
        full_map=full_map,
        target_actor_id=target_actor_id,
        helpers=helpers,
    )
