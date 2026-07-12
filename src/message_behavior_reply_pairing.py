"""Reply-pairing augmentation helpers for message-behavior analysis."""

from __future__ import annotations

from typing import Any, cast

from .message_behavior_evidence import _candidate, _metadata_evidence
from .message_behavior_models import (
    CommunicationClass,
    CommunicationClassification,
    MessageBehaviorAnalysis,
    ordered_unique,
)


def _tone_summary(
    *,
    classification: CommunicationClassification,
    behavior_candidates: list[Any],
    signal_ids: list[str],
) -> str:
    """Generate a human-readable tone summary from classification and behavior candidates.

    Args:
        classification: The communication classification containing primary class and rationale.
        behavior_candidates: List of behavior candidates with labels and evidence.
        signal_ids: List of signal identifiers that were detected but not consumed.

    Returns:
        A string summarizing the tone based on available classification and behavior
        evidence, or a neutral default if no strong signals are present.

    """
    labels = [str(candidate.get("label") or "") for candidate in behavior_candidates if candidate.get("label")]
    if labels:
        return (
            f"{classification['primary_class'].capitalize()} communication cues appear, with behaviour-level support "
            f"from {', '.join(labels[:3])}."
        )
    if signal_ids:
        return (
            f"{classification['primary_class'].capitalize()} wording cues appear, but message-level behaviour support "
            "remains limited."
        )
    return "Neutral coordination wording appears in the authored text."


def inject_reply_pairing_findings(
    analysis: MessageBehaviorAnalysis,
    *,
    reply_pairing: dict[str, Any] | None,
) -> MessageBehaviorAnalysis:
    """Inject reply-pairing findings into a message behavior analysis.

    Args:
        analysis: The existing message behavior analysis to augment.
        reply_pairing: Reply pairing metadata containing response status, actor emails,
            and activity UIDs. Used to detect selective non-response patterns.

    Returns:
        The analysis enriched with reply-pairing findings, including additional
        behavior candidates (e.g., selective_non_response), process signals,
        classification updates, and relevant wording.

    """
    if not isinstance(reply_pairing, dict):
        return analysis
    behavior_candidates = list(analysis.get("behavior_candidates", []))
    counter_indicators = list(analysis.get("counter_indicators", []))
    response_status = str(reply_pairing.get("response_status") or "")
    relevant_actor_emails = [str(email) for email in reply_pairing.get("relevant_actor_emails", []) if email]
    later_activity_uids = [str(uid) for uid in reply_pairing.get("later_activity_uids", []) if uid]
    process_signals = list(analysis.get("omissions_or_process_signals", []))
    classification = analysis.get("communication_classification") or _neutral_classification()
    relevant_wording = list(analysis.get("relevant_wording", []))
    if bool(reply_pairing.get("supports_selective_non_response_inference")):
        behavior_candidates, process_signals, classification, relevant_wording = _selective_non_response_findings(
            analysis, behavior_candidates, response_status, relevant_actor_emails, later_activity_uids
        )
    else:
        _extend_counter_indicators(counter_indicators, reply_pairing.get("counter_indicators", []))
    return {
        **analysis,
        "behavior_candidate_count": len(behavior_candidates),
        "behavior_candidates": behavior_candidates,
        "counter_indicators": counter_indicators,
        "relevant_wording": relevant_wording,
        "omissions_or_process_signals": process_signals,
        "communication_classification": classification,
        "tone_summary": _tone_summary(classification=classification, behavior_candidates=behavior_candidates, signal_ids=[]),
    }


def _neutral_classification():
    return {"primary_class": "neutral", "applied_classes": ["neutral"], "confidence": "low", "rationale": ""}


def _selective_non_response_findings(analysis, behavior_candidates, response_status, actor_emails, activity_uids):
    behavior_candidates.append(_selective_non_response_candidate(response_status, actor_emails, activity_uids))
    process_signals = list(analysis.get("omissions_or_process_signals", []))
    process_signals.append(
        {
            "signal": "selective_non_response_inference",
            "summary": "Reply-pairing metadata supports a non-response concern in the current evidence slice.",
        }
    )
    classification = _retaliatory_classification(analysis, behavior_candidates)
    relevant_wording = list(analysis.get("relevant_wording", []))
    relevant_wording.append(
        {
            "text": response_status or "indirect_activity_without_direct_reply",
            "source_scope": "message_metadata",
            "basis_id": "behavior:selective_non_response",
        }
    )
    return behavior_candidates, process_signals, classification, relevant_wording


def _selective_non_response_candidate(response_status, actor_emails, activity_uids):
    return _candidate(
        behavior_id="selective_non_response",
        label="Selective Non-response",
        confidence="medium",
        taxonomy_ids=["selective_non_response", "retaliatory_sequence"],
        rationale=(
            "A target-authored request did not receive a direct reply from a relevant actor, even though "
            "that actor remained active in the same current evidence slice."
        ),
        evidence=_metadata_evidence(
            excerpt=(
                "Relevant actor(s) "
                f"{actor_emails or ['unknown']} showed later activity "
                f"{activity_uids or ['unknown']} without a direct reply to the target-authored request."
            ),
            matched_text=response_status or "indirect_activity_without_direct_reply",
        ),
        derived_from_signal_ids=[],
        neutral_alternatives=[
            "The reply may have happened outside the current evidence slice or through another channel.",
            "Later activity in the same thread does not always imply an obligation to respond directly.",
        ],
    )


def _retaliatory_classification(analysis, behavior_candidates):
    current = analysis.get("communication_classification") or _neutral_classification()
    applied_classes = [str(label) for label in list(current.get("applied_classes") or []) if str(label).strip()]
    if "retaliatory" not in applied_classes:
        applied_classes.append("retaliatory")
    return {
        "primary_class": "retaliatory",
        "applied_classes": [cast(CommunicationClass, label) for label in ordered_unique(applied_classes)],
        "confidence": "high" if len(behavior_candidates) >= 2 else "medium",
        "rationale": (
            "Reply-pairing metadata adds a retaliatory communication read because a direct reply was "
            "missing despite later relevant activity."
        ),
    }


def _extend_counter_indicators(counter_indicators, items):
    for item in items:
        text = str(item).strip()
        if text and text not in counter_indicators:
            counter_indicators.append(text)
