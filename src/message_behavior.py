"""Stable facade for message-behavior analysis and payload normalization."""

from __future__ import annotations

from .message_behavior_analysis import analyze_message_behavior, inject_reply_pairing_findings
from .message_behavior_models import (
    MESSAGE_BEHAVIOR_VERSION,
    BehaviorCandidate,
    BehaviorCandidateId,
    BehaviorConfidence,
    BehaviorEvidence,
    BehaviorEvidenceScope,
    CommunicationClass,
    CommunicationClassification,
    MessageBehaviorAnalysis,
    ProcessSignal,
    RelevantWording,
    empty_message_behavior_analysis,
    normalize_message_behavior_analysis,
    normalize_message_findings_payload,
)

__all__ = [
    "MESSAGE_BEHAVIOR_VERSION",
    "BehaviorCandidate",
    "BehaviorCandidateId",
    "BehaviorConfidence",
    "BehaviorEvidence",
    "BehaviorEvidenceScope",
    "CommunicationClass",
    "CommunicationClassification",
    "MessageBehaviorAnalysis",
    "ProcessSignal",
    "RelevantWording",
    "analyze_message_behavior",
    "empty_message_behavior_analysis",
    "inject_reply_pairing_findings",
    "normalize_message_behavior_analysis",
    "normalize_message_findings_payload",
]
