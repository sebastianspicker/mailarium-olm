"""Reply-pairing augmentation helpers for message-behavior analysis."""

from __future__ import annotations

from typing import Any, cast

from .message_behavior_evidence import _candidate, _metadata_evidence
from .message_behavior_models import (
    BehaviorConfidence,
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
    if not isinstance(reply_pairing, dict):
        return analysis
    behavior_candidates = list(analysis.get("behavior_candidates", []))
    counter_indicators = list(analysis.get("counter_indicators", []))
    response_status = str(reply_pairing.get("response_status") or "")
    relevant_actor_emails = [str(email) for email in reply_pairing.get("relevant_actor_emails", []) if email]
    later_activity_uids = [str(uid) for uid in reply_pairing.get("later_activity_uids", []) if uid]
    if bool(reply_pairing.get("supports_selective_non_response_inference")):
        behavior_candidates.append(
            _candidate(
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
                        f"{relevant_actor_emails or ['unknown']} showed later activity "
                        f"{later_activity_uids or ['unknown']} without a direct reply to the target-authored request."
                    ),
                    matched_text=response_status or "indirect_activity_without_direct_reply",
                ),
                derived_from_signal_ids=[],
                neutral_alternatives=[
                    "The reply may have happened outside the current evidence slice or through another channel.",
                    "Later activity in the same thread does not always imply an obligation to respond directly.",
                ],
            )
        )
        process_signals = list(analysis.get("omissions_or_process_signals", []))
        process_signals.append(
            {
                "signal": "selective_non_response_inference",
                "summary": "Reply-pairing metadata supports a non-response concern in the current evidence slice.",
            }
        )
        current_classification = analysis.get("communication_classification") or {
            "primary_class": "neutral",
            "applied_classes": ["neutral"],
            "confidence": "low",
            "rationale": "",
        }
        classification: CommunicationClassification = {
            "primary_class": cast(CommunicationClass, str(current_classification.get("primary_class") or "neutral")),
            "applied_classes": [
                cast(CommunicationClass, str(label))
                for label in list(current_classification.get("applied_classes") or [])
                if str(label).strip()
            ],
            "confidence": cast(BehaviorConfidence, str(current_classification.get("confidence") or "low")),
            "rationale": str(current_classification.get("rationale") or ""),
        }
        applied_classes = [str(label) for label in classification.get("applied_classes", []) if str(label).strip()]
        if "retaliatory" not in applied_classes:
            applied_classes.append("retaliatory")
        classification = {
            "primary_class": "retaliatory",
            "applied_classes": [cast(CommunicationClass, label) for label in ordered_unique(applied_classes)],
            "confidence": "high" if len(behavior_candidates) >= 2 else "medium",
            "rationale": (
                "Reply-pairing metadata adds a retaliatory communication read because a direct reply was "
                "missing despite later relevant activity."
            ),
        }
        relevant_wording = list(analysis.get("relevant_wording", []))
        relevant_wording.append(
            {
                "text": response_status or "indirect_activity_without_direct_reply",
                "source_scope": "message_metadata",
                "basis_id": "behavior:selective_non_response",
            }
        )
    else:
        for item in reply_pairing.get("counter_indicators", []):
            text = str(item).strip()
            if text and text not in counter_indicators:
                counter_indicators.append(text)
        process_signals = list(analysis.get("omissions_or_process_signals", []))
        classification = analysis.get("communication_classification") or {
            "primary_class": "neutral",
            "applied_classes": ["neutral"],
            "confidence": "low",
            "rationale": "",
        }
        relevant_wording = list(analysis.get("relevant_wording", []))
    return {
        **analysis,
        "behavior_candidate_count": len(behavior_candidates),
        "behavior_candidates": behavior_candidates,
        "counter_indicators": counter_indicators,
        "relevant_wording": relevant_wording,
        "omissions_or_process_signals": process_signals,
        "communication_classification": classification,
        "tone_summary": _tone_summary(
            classification=classification,
            behavior_candidates=behavior_candidates,
            signal_ids=[],
        ),
    }
