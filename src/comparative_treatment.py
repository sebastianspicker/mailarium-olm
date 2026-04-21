"""Comparative-treatment helpers for behavioural-analysis cases."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

COMPARATIVE_TREATMENT_VERSION = "1"

_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")


def _recipient_emails(full_email: dict[str, Any] | None) -> list[str]:
    """Return normalized visible recipient emails from one full-email row."""
    emails: list[str] = []
    for field in ("to", "cc", "bcc"):
        for value in ((full_email or {}).get(field) or []):
            match = _EMAIL_RE.search(str(value or ""))
            if not match:
                continue
            email = match.group(1).lower()
            if email not in emails:
                emails.append(email)
    return emails


def _behavior_ids(candidate: dict[str, Any]) -> list[str]:
    """Return authored behavior ids for one candidate."""
    findings = ((candidate.get("message_findings") or {}).get("authored_text") or {})
    return [
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict)
    ]


def _metrics(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """Return aggregate target/comparator metrics for one candidate bucket."""
    tone_signal_count = sum(
        int(((candidate.get("language_rhetoric") or {}).get("authored_text") or {}).get("signal_count") or 0)
        for candidate in candidates
    )
    behavior_ids = [behavior_id for candidate in candidates for behavior_id in _behavior_ids(candidate)]
    return {
        "message_count": len(candidates),
        "tone_signal_count": tone_signal_count,
        "escalation_count": sum(1 for behavior_id in behavior_ids if behavior_id == "escalation"),
        "criticism_count": sum(1 for behavior_id in behavior_ids if behavior_id in {"public_correction", "undermining"}),
        "demand_intensity_count": sum(
            1 for behavior_id in behavior_ids if behavior_id in {"deadline_pressure", "selective_accountability", "escalation"}
        ),
    }


def _situation_tags(candidates: list[dict[str, Any]]) -> set[str]:
    """Return coarse situation tags for bounded comparator similarity checks."""
    tags: set[str] = set()
    for candidate in candidates:
        behavior_ids = set(_behavior_ids(candidate))
        if behavior_ids & {"deadline_pressure", "selective_accountability"}:
            tags.add("request_type")
        if behavior_ids & {"public_correction", "undermining"}:
            tags.add("error_type")
        if "escalation" in behavior_ids:
            tags.add("escalation_context")
        if candidate.get("thread_group_id"):
            tags.add(f"thread:{candidate['thread_group_id']}")
    return tags


def _similarity_checks(target_candidates: list[dict[str, Any]], comparator_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return bounded similarity checks for comparator validity."""
    target_tags = _situation_tags(target_candidates)
    comparator_tags = _situation_tags(comparator_candidates)
    shared_tags = sorted(target_tags & comparator_tags)
    return {
        "shared_request_type": "request_type" in shared_tags,
        "shared_error_type": "error_type" in shared_tags,
        "shared_escalation_context": "escalation_context" in shared_tags,
        "shared_process_step": any(tag.startswith("thread:") for tag in shared_tags),
        "shared_tags": shared_tags,
        "similarity_score": len(shared_tags),
    }


def build_comparative_treatment(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
) -> dict[str, Any] | None:
    """Return conservative comparator analysis for the target versus named comparators."""
    scope = (case_bundle or {}).get("scope") if isinstance(case_bundle, dict) else None
    if not isinstance(scope, dict):
        return None
    target = scope.get("target_person")
    comparators = scope.get("comparator_actors")
    if not isinstance(target, dict) or not isinstance(comparators, list) or not comparators:
        return None

    target_email = str(target.get("email") or "").lower()
    target_actor_id = str(target.get("actor_id") or "")
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
                recipients = _recipient_emails(full_map.get(uid))
                if target_email and target_email in recipients:
                    target_candidates.append(candidate)
                if comparator_email and comparator_email in recipients:
                    comparator_candidates.append(candidate)
            if not target_candidates or not comparator_candidates:
                continue
            similarity = _similarity_checks(target_candidates, comparator_candidates)
            target_metrics = _metrics(target_candidates)
            comparator_metrics = _metrics(comparator_candidates)
            unequal_treatment_signals = []
            if target_metrics["tone_signal_count"] > comparator_metrics["tone_signal_count"]:
                unequal_treatment_signals.append("tone_to_target_harsher_than_to_comparator")
            if target_metrics["escalation_count"] > comparator_metrics["escalation_count"]:
                unequal_treatment_signals.append("same_sender_escalates_more_against_target")
            if target_metrics["criticism_count"] > comparator_metrics["criticism_count"]:
                unequal_treatment_signals.append("same_sender_criticizes_target_more")
            if target_metrics["demand_intensity_count"] > comparator_metrics["demand_intensity_count"]:
                unequal_treatment_signals.append("same_sender_demands_more_from_target")
            status = "comparator_available" if similarity["similarity_score"] > 0 else "weak_similarity"
            summary: dict[str, Any] = {
                "comparator_actor_id": comparator_actor_id,
                "comparator_email": comparator_email,
                "sender_actor_id": sender_actor_id,
                "status": status,
                "similarity_checks": similarity,
                "target_metrics": target_metrics,
                "comparator_metrics": comparator_metrics,
                "unequal_treatment_signals": unequal_treatment_signals,
                "evidence_chain": {
                    "target_uids": [str(candidate.get("uid") or "") for candidate in target_candidates],
                    "comparator_uids": [str(candidate.get("uid") or "") for candidate in comparator_candidates],
                },
            }
            current_score = int(summary["similarity_checks"]["similarity_score"])
            previous_score = int((((best_summary or {}).get("similarity_checks") or {}).get("similarity_score")) or 0)
            if best_summary is None or current_score > previous_score:
                best_summary = summary
        if best_summary is None:
            comparator_summaries.append(
                {
                    "comparator_actor_id": comparator_actor_id,
                    "comparator_email": comparator_email,
                    "status": "no_suitable_comparator",
                    "reason": (
                        "No same-sender message pair addressed both the target "
                        "and this comparator in the current evidence set."
                    ),
                    "similarity_checks": {
                        "shared_request_type": False,
                        "shared_error_type": False,
                        "shared_escalation_context": False,
                        "shared_process_step": False,
                        "shared_tags": [],
                        "similarity_score": 0,
                    },
                    "target_metrics": {},
                    "comparator_metrics": {},
                    "unequal_treatment_signals": [],
                    "evidence_chain": {
                        "target_uids": [],
                        "comparator_uids": [],
                    },
                }
            )
        else:
            comparator_summaries.append(best_summary)

    status_counts = Counter(str(summary.get("status") or "") for summary in comparator_summaries)
    available = [summary for summary in comparator_summaries if summary.get("status") == "comparator_available"]
    return {
        "version": COMPARATIVE_TREATMENT_VERSION,
        "target_actor_id": target_actor_id,
        "comparator_count": len(comparator_summaries),
        "summary": {
            "status_counts": dict(sorted(status_counts.items())),
            "available_comparator_count": len(available),
            "no_suitable_comparator_count": sum(
                1 for summary in comparator_summaries if summary.get("status") == "no_suitable_comparator"
            ),
        },
        "comparator_summaries": comparator_summaries,
    }
