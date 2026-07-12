"""Helper functions for comparative-treatment analysis."""
# pylint: disable=too-many-boolean-expressions,too-many-branches,too-many-locals

from __future__ import annotations

import re
import sys
from collections import Counter
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
    """Extract all recipient email addresses from an email dictionary.

    Args:
        full_email: A dictionary containing email fields (to, cc, bcc).

    Returns:
        A list of unique lowercase email addresses found in to, cc, and bcc fields.

    """
    emails: list[str] = []
    for field in ("to", "cc", "bcc"):
        for value in (full_email or {}).get(field) or []:
            for match in _EMAIL_RE.finditer(str(value or "")):
                email = match.group(1).lower()
                if email not in emails:
                    emails.append(email)
    return emails


def behavior_ids(candidate: dict[str, Any]) -> list[str]:
    """Extract behavior IDs from a candidate's message findings.

    Args:
        candidate: A dictionary containing message_findings with authored_text
            and behavior_candidates.

    Returns:
        A list of behavior_id strings from the candidate's behavior candidates.

    """
    findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    return [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict)
    ]


def normalized_subject(value: str) -> str:
    """Normalize an email subject by removing common prefixes and extra whitespace.

    Removes prefixes like 'Re:', 'Fw:', 'Fwd:', 'Aw:', 'Wg:' and collapses
    multiple spaces.

    Args:
        value: The email subject string to normalize.

    Returns:
        The normalized subject in lowercase with prefixes removed and
        whitespace collapsed.

    """
    normalized = str(value or "").strip().lower()
    while True:
        updated = re.sub(r"^(re|fw|fwd|aw|wg)\s*:\s*", "", normalized)
        if updated == normalized:
            break
        normalized = updated
    return re.sub(r"\s+", " ", normalized).strip()


def parse_day(value: str) -> date | None:
    """Parse a string value into a date object.

    Handles ISO format dates and replaces 'Z' with '+00:00' for UTC.

    Args:
        value: The date string to parse.

    Returns:
        A date object if parsing succeeds, None otherwise.

    """
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def recipient_count(candidate: dict[str, Any], full_map: dict[str, Any]) -> int:
    """Count the number of recipients for a candidate email.

    Args:
        candidate: A candidate dictionary with a uid field.
        full_map: A dictionary mapping UIDs to full email data.

    Returns:
        The number of unique recipient email addresses.

    """
    return len(recipient_emails(full_map.get(str(candidate.get("uid") or ""))))


def visibility_band(count: int) -> str:
    """Categorize recipient count into a visibility band.

    Args:
        count: The number of recipients.

    Returns:
        One of: 'direct_only' (0-1 recipients), 'small_group' (2 recipients),
        'broad_visibility' (3+ recipients).

    """
    if count <= 1:
        return "direct_only"
    if count == 2:
        return "small_group"
    return "broad_visibility"


def metrics(candidates: list[dict[str, Any]], *, full_map: dict[str, Any]) -> dict[str, float | int]:
    """Calculate various metrics from a list of candidate messages.

    Computes counts and rates for tone signals, escalations, criticisms,
    demands, procedural pressure, visibility, and response delays.

    Args:
        candidates: List of candidate message dictionaries.
        full_map: Dictionary mapping UIDs to full email data.

    Returns:
        A dictionary containing computed metrics including:
        - message_count: Total number of messages
        - tone_signal_count/rate: Tone signal metrics
        - escalation_count/rate: Escalation metrics
        - criticism_count/rate: Criticism metrics
        - demand_intensity_count/rate: Demand intensity metrics
        - procedural_pressure_count/rate: Procedural pressure metrics
        - average_visible_recipient_count: Average recipients per message
        - multi_recipient_count/rate: Multi-recipient message metrics
        - response_delay_observation_count: Number of messages with delay data
        - average_response_delay_hours: Average response delay in hours

    """
    # Extract tone signal counts step-by-step for readability.
    tone_signal_count = _tone_signal_count(candidates)
    ids = [behavior_id for candidate in candidates for behavior_id in behavior_ids(candidate)]
    message_count = len(candidates)
    id_counts = Counter(ids)
    escalation_count = id_counts["escalation"]
    criticism_count = _count_ids(id_counts, {"public_correction", "undermining"})
    demand_intensity_count = _count_ids(id_counts, {"deadline_pressure", "selective_accountability", "escalation"})
    procedural_pressure_count = _count_ids(
        id_counts, {"deadline_pressure", "selective_accountability", "withholding", "escalation"}
    )
    recipient_counts = [recipient_count(candidate, full_map) for candidate in candidates]
    multi_recipient_count = sum(1 for count in recipient_counts if count >= 2)
    response_delays = _response_delays(candidates)
    return {
        "message_count": message_count,
        "tone_signal_count": tone_signal_count,
        "tone_signal_rate": _rate(tone_signal_count, message_count),
        "escalation_count": escalation_count,
        "escalation_rate": _rate(escalation_count, message_count),
        "criticism_count": criticism_count,
        "criticism_rate": _rate(criticism_count, message_count),
        "demand_intensity_count": demand_intensity_count,
        "demand_intensity_rate": _rate(demand_intensity_count, message_count),
        "procedural_pressure_count": procedural_pressure_count,
        "procedural_pressure_rate": _rate(procedural_pressure_count, message_count),
        "average_visible_recipient_count": _rate(sum(recipient_counts), message_count),
        "multi_recipient_count": multi_recipient_count,
        "multi_recipient_rate": _rate(multi_recipient_count, message_count),
        "response_delay_observation_count": len(response_delays),
        "average_response_delay_hours": _rate(sum(response_delays), len(response_delays)),
    }


def _tone_signal_count(candidates):
    total = 0
    for candidate in candidates:
        rhetoric = candidate.get("language_rhetoric") or {}
        authored_text = rhetoric.get("authored_text") or {}
        total += int(authored_text.get("signal_count") or 0)
    return total


def _count_ids(counts, ids):
    return sum(counts[item] for item in ids)


def _rate(numerator, denominator):
    return round(numerator / denominator, 3) if denominator else 0.0


def _response_delays(candidates):
    delays = []
    for candidate in candidates:
        pairing = candidate.get("reply_pairing")
        if isinstance(pairing, dict) and str(pairing.get("response_status") or "") in {"direct_reply", "delayed_reply"}:
            delay = pairing.get("response_delay_hours")
            if delay is not None:
                delays.append(float(delay))
    return delays


def situation_tags(candidates: list[dict[str, Any]]) -> set[str]:
    """Extract situation tags from a list of candidate messages.

    Tags are derived from behavior IDs and message metadata like thread groups
    and subjects.

    Args:
        candidates: List of candidate message dictionaries.

    Returns:
        A set of situation tag strings including:
        - 'request_type' if deadline_pressure or selective_accountability behaviors found
        - 'error_type' if public_correction or undermining behaviors found
        - 'escalation_context' if escalation behavior found
        - 'thread:{thread_group_id}' for each thread group
        - 'subject:{normalized_subject}' for each subject

    """
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
    """Determine the workflow stage for a candidate message.

    Classifies messages based on behavior IDs and subject content.

    Args:
        candidate: A candidate message dictionary with behavior_ids and subject.

    Returns:
        A workflow stage string: 'request_or_compliance', 'error_or_correction',
        'escalation', 'status_or_follow_up', 'request_or_approval', or 'generic'.

    """
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
    """Perform similarity checks between target and comparator candidates.

    Compares candidates across multiple dimensions: tags, subjects, dates,
    workflow stages, and visibility bands.

    Args:
        target_candidates: List of target candidate message dictionaries.
        comparator_candidates: List of comparator candidate message dictionaries.
        full_map: Dictionary mapping UIDs to full email data.

    Returns:
        A dictionary containing similarity metrics including:
        - shared_request_type, shared_error_type, shared_escalation_context: Boolean flags
        - shared_process_step: Whether there's process step overlap
        - shared_workflow_stage: Whether there's workflow stage overlap
        - same_sender_decision_path: Always True
        - shared_subject, shared_subject_family: Whether subjects match
        - shared_day, shared_day_window: Whether dates match or are close
        - shared_visibility_band: Whether visibility bands match
        - shared_context_count: Number of shared context types
        - shared_subject_families, shared_tags, shared_workflow_stages, shared_visibility_bands: Lists
        - similarity_score: Numeric score combining all similarity factors

    """
    target_tags, target_subjects, target_days, target_workflow_stages, target_visibility_bands = _similarity_dimensions(
        target_candidates, full_map
    )
    comparator_tags, comparator_subjects, comparator_days, comparator_workflow_stages, comparator_visibility_bands = (
        _similarity_dimensions(comparator_candidates, full_map)
    )
    shared_tags = sorted(target_tags & comparator_tags)
    shared_subject = bool(target_subjects & comparator_subjects)
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
    shared_workflow_stage = bool(target_workflow_stages & comparator_workflow_stages)
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


def _candidate_subjects(candidates):
    return {subject for candidate in candidates if (subject := normalized_subject(str(candidate.get("subject") or "")))}


def _similarity_dimensions(candidates, full_map):
    stages = {stage for candidate in candidates if (stage := workflow_stage(candidate)) != "generic"}
    days = [parsed for candidate in candidates if (parsed := parse_day(str(candidate.get("date") or "")))]
    visibility = {visibility_band(recipient_count(candidate, full_map)) for candidate in candidates}
    return situation_tags(candidates), _candidate_subjects(candidates), days, stages, visibility


def comparison_quality(
    similarity: dict[str, Any], *, target_metrics: dict[str, float | int], comparator_metrics: dict[str, float | int]
) -> tuple[str, list[str]]:
    """Determine the quality of a comparison based on similarity and metrics.

    Args:
        similarity: Dictionary of similarity metrics from similarity_checks().
        target_metrics: Metrics dictionary for target candidates.
        comparator_metrics: Metrics dictionary for comparator candidates.

    Returns:
        A tuple of (quality, uncertainty_reasons) where:
        - quality is one of: 'high', 'partial', 'weak'
        - uncertainty_reasons is a list of strings explaining quality limitations

    """
    message_delta = abs(int(target_metrics.get("message_count") or 0) - int(comparator_metrics.get("message_count") or 0))
    uncertainty_reasons = _comparison_uncertainty_reasons(similarity, target_metrics, comparator_metrics, message_delta)

    similarity_score = int(similarity.get("similarity_score") or 0)
    similarity_threshold_met = similarity_score >= 4
    message_delta_threshold_met = message_delta <= 1
    if _is_high_quality(similarity, similarity_threshold_met, message_delta_threshold_met):
        quality = "high"
    elif similarity_score >= 3:
        quality = "partial"
    else:
        quality = "weak"
    return quality, uncertainty_reasons


def _is_high_quality(similarity, similarity_threshold_met, message_delta_threshold_met):
    required = ("shared_process_step", "shared_workflow_stage", "shared_day_window", "shared_visibility_band")
    return (
        similarity_threshold_met
        and message_delta_threshold_met
        and all(bool(similarity.get(key)) for key in required)
        and int(similarity.get("shared_context_count") or 0) >= 1
    )


def _comparison_uncertainty_reasons(similarity, target_metrics, comparator_metrics, message_delta):
    checks = (
        (
            not similarity.get("shared_process_step"),
            "Target and comparator messages do not share a clear process step or thread.",
        ),
        (not similarity.get("shared_subject"), "Target and comparator messages do not share a normalized subject line."),
        (not similarity.get("shared_workflow_stage"), "Target and comparator messages do not share a clear workflow stage."),
        (
            not similarity.get("shared_day"),
            "Target and comparator messages do not occur on the same day in the current evidence set.",
        ),
        (not similarity.get("shared_day_window"), "Target and comparator messages do not fall within a bounded day window."),
        (not similarity.get("shared_visibility_band"), "Target and comparator messages do not share a similar visibility band."),
        (
            int(similarity.get("shared_context_count") or 0) == 0,
            "Target and comparator messages do not share a clear request, error, or escalation context.",
        ),
        (message_delta >= 2, "Target and comparator buckets are imbalanced in message count."),
        (
            not _both_have_delay_metrics(target_metrics, comparator_metrics),
            "Comparable reply-latency evidence is not available for both sides in the current record.",
        ),
    )
    return [reason for failed, reason in checks if failed]


def _both_have_delay_metrics(target, comparator):
    return (
        int(target.get("response_delay_observation_count") or 0) > 0
        and int(comparator.get("response_delay_observation_count") or 0) > 0
    )


def scope_text(scope: dict[str, Any]) -> str:
    """Extract and concatenate text from various scope fields.

    Combines analysis_goal, context_notes, allegation_focus, employment_issue_tags,
    employment_issue_tracks, and trigger_events into a single lowercase string.

    Args:
        scope: A dictionary containing case scope information.

    Returns:
        A space-joined string of all non-empty text values from the scope.

    """
    parts = _scope_values(scope, ("analysis_goal", "context_notes"))
    for field in ("allegation_focus", "employment_issue_tags", "employment_issue_tracks"):
        parts.extend(_scope_values(scope, (field,)))
    for event in scope.get("trigger_events", []) or []:
        if isinstance(event, dict):
            parts.append(str(event.get("trigger_type") or ""))
            parts.append(str(event.get("summary") or ""))
    return " ".join(parts).lower()


def _scope_values(scope, fields):
    values = []
    for field in fields:
        raw_values = scope.get(field, []) or []
        for item in raw_values if isinstance(raw_values, list) else [raw_values]:
            if text := str(item or "").strip():
                values.append(text)
    return values


def comparator_discovery_candidates(
    *, scope: dict[str, Any], candidates: list[dict[str, Any]], full_map: dict[str, Any]
) -> list[dict[str, Any]]:
    """Discover potential comparator candidates from the candidate pool.

    Identifies emails sent to the same recipients as the target by the same sender,
    excluding the target email itself and any explicitly named comparators.

    Args:
        scope: Dictionary containing target_person and comparator_actors.
        candidates: List of all candidate message dictionaries.
        full_map: Dictionary mapping UIDs to full email data.

    Returns:
        A sorted list of comparator candidate dictionaries with fields:
        - candidate_email: The email address
        - candidate_actor_id: The actor ID if found
        - evidence_uids: List of UIDs for this comparator
        - shared_sender_actor_ids: List of shared sender actor IDs
        - shared_subject_families: List of shared subject families
        - shared_day_window_count: Number of days within window
        - confidence: 'medium' or 'low'
        - promotion_rule: Promotion rule string
        Sorted by confidence (medium first), then evidence count (descending).

    """
    target_value = scope.get("target_person")
    target: dict[str, Any] = dict(target_value) if isinstance(target_value, dict) else {}
    target_email = str(target.get("email") or "").lower()
    comparators = [item for item in scope.get("comparator_actors", []) or [] if isinstance(item, dict)]
    named_emails, named_actor_ids = _named_comparator_sets(comparators)
    by_email = _discover_comparator_rows(candidates, full_map, target_email, named_emails)
    result = _discovery_results(by_email, comparators, target_email, named_actor_ids)
    result.sort(
        key=lambda item: (
            0 if str(item.get("confidence") or "") == "medium" else 1,
            -len(item.get("evidence_uids", [])),
            str(item.get("candidate_email") or ""),
        )
    )
    return result[:10]


def _named_comparator_sets(comparators):
    emails = {str(item.get("email") or "").lower() for item in comparators if str(item.get("email") or "").strip()}
    actor_ids = {str(item.get("actor_id") or "") for item in comparators if str(item.get("actor_id") or "").strip()}
    return emails, actor_ids


def _discover_comparator_rows(candidates, full_map, target_email, excluded_emails):
    by_email = {}
    for candidate in candidates:
        recipients = recipient_emails(full_map.get(str(candidate.get("uid") or "")))
        if target_email and target_email not in recipients:
            continue
        for other in candidates:
            _consider_comparator_pair(candidate, other, full_map, target_email, excluded_emails, by_email)
    return by_email


def _consider_comparator_pair(candidate, other, full_map, target_email, excluded_emails, by_email):
    sender_id = str(candidate.get("sender_actor_id") or "")
    if other is candidate or str(other.get("sender_actor_id") or "") != sender_id:
        return
    context = _pair_context(candidate, other)
    if context is None:
        return
    other_subject, within_day = context
    other_uid = str(other.get("uid") or "")
    for email in recipient_emails(full_map.get(other_uid)):
        if _eligible_recipient(email, target_email, excluded_emails):
            _update_discovery_row(by_email, email, other_uid, sender_id, other_subject, within_day)


def _pair_context(candidate, other):
    subject = normalized_subject(str(candidate.get("subject") or ""))
    other_subject = normalized_subject(str(other.get("subject") or ""))
    within_day = _days_within_one(parse_day(str(candidate.get("date") or "")), parse_day(str(other.get("date") or "")))
    if subject and other_subject and subject != other_subject and not within_day:
        return None
    return other_subject, within_day


def _eligible_recipient(email, target_email, excluded_emails):
    return bool(email and email != target_email and email not in excluded_emails)


def _days_within_one(day, other_day):
    return bool(day and other_day and abs((day - other_day).days) <= 1)


def _update_discovery_row(by_email, email, uid, sender_id, subject, within_day):
    row = by_email.setdefault(
        email,
        {
            "email": email,
            "evidence_uids": [],
            "shared_sender_actor_ids": [],
            "shared_subject_families": [],
            "shared_day_window_count": 0,
        },
    )
    for value, key in ((uid, "evidence_uids"), (sender_id, "shared_sender_actor_ids"), (subject, "shared_subject_families")):
        if value and value not in row[key]:
            row[key].append(value)
    if within_day:
        row["shared_day_window_count"] += 1


def _discovery_results(by_email, comparators, target_email, named_actor_ids):
    results = []
    for email, row in by_email.items():
        actor_id = _comparator_actor_id(comparators, email)
        if email == target_email or (actor_id and actor_id in named_actor_ids):
            continue
        results.append(
            {
                "candidate_email": email,
                "candidate_actor_id": actor_id,
                "evidence_uids": row["evidence_uids"][:5],
                "shared_sender_actor_ids": row["shared_sender_actor_ids"][:3],
                "shared_subject_families": row["shared_subject_families"][:3],
                "shared_day_window_count": int(row["shared_day_window_count"]),
                "confidence": "medium" if row["shared_day_window_count"] >= 1 and row["shared_subject_families"] else "low",
                "promotion_rule": "review_facing_only_explicit_comparator_override_required",
            }
        )
    return results


def _comparator_actor_id(comparators, email):
    for comparator in comparators:
        if str(comparator.get("email") or "").lower() == email:
            return str(comparator.get("actor_id") or "")
    return ""


def shared_comparator_points_from_summaries(comparator_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Delegate to comparative_treatment_matrix.shared_comparator_points_from_summaries.

    This is a re-export for convenience.

    Args:
        comparator_summaries: List of comparator summary dictionaries.

    Returns:
        List of normalized comparator point dictionaries.

    """
    from .comparative_treatment_matrix import shared_comparator_points_from_summaries as _shared_points

    return _shared_points(comparator_summaries)


def compare_treatment(
    *, scope: dict[str, Any], candidates: list[dict[str, Any]], full_map: dict[str, Any], target_actor_id: str
) -> dict[str, Any]:
    """Delegate to comparative_treatment_runtime.compare_treatment.

    This is a re-export for convenience that passes the helpers module.

    Args:
        scope: Dictionary containing case scope information.
        candidates: List of candidate message dictionaries.
        full_map: Dictionary mapping UIDs to full email data.
        target_actor_id: The actor ID of the target person.

    Returns:
        A dictionary containing the comparative treatment analysis results.

    """
    from .comparative_treatment_runtime import compare_treatment as _compare_treatment

    helpers = sys.modules[__name__]
    return _compare_treatment(
        scope=scope,
        candidates=candidates,
        full_map=full_map,
        target_actor_id=target_actor_id,
        helpers=helpers,
    )
