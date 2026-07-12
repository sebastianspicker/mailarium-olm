"""Stable message-behavior payload models and normalization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, TypedDict, cast

from . import message_behavior_evidence as _message_behavior_evidence

MESSAGE_BEHAVIOR_VERSION = "1"

BehaviorCandidateId = _message_behavior_evidence.BehaviorCandidateId
BehaviorConfidence = _message_behavior_evidence.BehaviorConfidence
BehaviorEvidenceScope = _message_behavior_evidence.BehaviorEvidenceScope
BehaviorEvidence = _message_behavior_evidence.BehaviorEvidence
BehaviorCandidate = _message_behavior_evidence.BehaviorCandidate

CommunicationClass = Literal[
    "neutral",
    "tense",
    "dismissive",
    "controlling",
    "defensive",
    "retaliatory",
    "exclusionary",
]


class RelevantWording(TypedDict):
    """A snippet of text identified as relevant to behavior analysis.

    Attributes:
        text: The actual text snippet.
        source_scope: The scope from which the text was extracted.
        basis_id: Identifier for the basis of this wording (e.g., signal or behavior ID).

    """

    text: str
    source_scope: BehaviorEvidenceScope
    basis_id: str


class ProcessSignal(TypedDict):
    """A process signal detected during behavior analysis.

    Attributes:
        signal: The signal identifier.
        summary: A human-readable summary of the signal.

    """

    signal: str
    summary: str


class CommunicationClassification(TypedDict):
    """Classification of communication style/behavior.

    Attributes:
        primary_class: The primary communication class.
        applied_classes: List of all applied communication classes.
        confidence: Confidence level in the classification.
        rationale: Explanation for the classification.

    """

    primary_class: CommunicationClass
    applied_classes: list[CommunicationClass]
    confidence: BehaviorConfidence
    rationale: str


class MessageBehaviorAnalysis(TypedDict):
    """Complete behavior analysis for a message.

    Attributes:
        text_scope: Whether the analysis is for authored or quoted text.
        behavior_candidate_count: Number of behavior candidates detected.
        behavior_candidates: List of behavior candidates with evidence.
        wording_only_signal_ids: Signal IDs that were only wording-level.
        counter_indicators: Factors arguing against behavior findings.
        tone_summary: Human-readable summary of the message tone.
        relevant_wording: Key wording snippets supporting findings.
        omissions_or_process_signals: Process-level signals detected.
        included_actors: Actors included in the message.
        excluded_actors: Actors excluded from the message.
        communication_classification: Overall communication classification.

    """

    text_scope: Literal["authored_text", "quoted_text"]
    behavior_candidate_count: int
    behavior_candidates: list[BehaviorCandidate]
    wording_only_signal_ids: list[str]
    counter_indicators: list[str]
    tone_summary: str
    relevant_wording: list[RelevantWording]
    omissions_or_process_signals: list[ProcessSignal]
    included_actors: list[str]
    excluded_actors: list[str]
    communication_classification: CommunicationClassification


def ordered_unique(values: Sequence[str]) -> list[str]:
    """Return a list of unique, non-empty string values preserving original order.

    Args:
        values: A sequence of string values, possibly with duplicates and empty strings.

    Returns:
        A list containing only the first occurrence of each non-empty string value,
        in the order they first appeared in the input.

    """
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def class_rank(label: CommunicationClass) -> int:
    """Return the numeric rank (severity/importance) of a communication class.

    Higher ranks indicate more severe or concerning communication patterns.

    Args:
        label: The communication class to rank.

    Returns:
        An integer rank where neutral=0, tense=1, dismissive=2, defensive=2,
        controlling=3, exclusionary=4, retaliatory=5. Returns 0 for unknown labels.

    """
    return {
        "neutral": 0,
        "tense": 1,
        "dismissive": 2,
        "defensive": 2,
        "controlling": 3,
        "exclusionary": 4,
        "retaliatory": 5,
    }.get(label, 0)


def empty_communication_classification() -> CommunicationClassification:
    """Return an empty/neutral communication classification.

    Returns:
        A CommunicationClassification with neutral primary class, low confidence,
        and empty rationale.

    """
    return {
        "primary_class": "neutral",
        "applied_classes": ["neutral"],
        "confidence": "low",
        "rationale": "",
    }


def normalize_communication_classification(value: Any) -> CommunicationClassification:
    """Normalize a value into a valid CommunicationClassification.

    Args:
        value: A dict-like value to normalize, or any other value.

    Returns:
        A valid CommunicationClassification with normalized primary_class,
        applied_classes (deduplicated and ordered), confidence, and rationale.
        Falls back to neutral classification if input is invalid.

    """
    classification = value if isinstance(value, dict) else {}
    primary_class = str(classification.get("primary_class") or "neutral")
    confidence = str(classification.get("confidence") or "low")
    applied_classes = [
        cast(CommunicationClass, label)
        for label in ordered_unique([str(item) for item in classification.get("applied_classes", []) if str(item).strip()])
    ]
    if not applied_classes:
        applied_classes = ["neutral"]
    return {
        "primary_class": cast(CommunicationClass, primary_class),
        "applied_classes": applied_classes,
        "confidence": cast(BehaviorConfidence, confidence),
        "rationale": str(classification.get("rationale") or ""),
    }


def empty_message_behavior_analysis(
    text_scope: Literal["authored_text", "quoted_text"] = "authored_text",
) -> MessageBehaviorAnalysis:
    """Return an empty message behavior analysis with the given text scope.

    Args:
        text_scope: The scope of text being analyzed (authored or quoted).

    Returns:
        A MessageBehaviorAnalysis with zero counts, empty lists, and neutral
        classification.

    """
    return {
        "text_scope": text_scope,
        "behavior_candidate_count": 0,
        "behavior_candidates": [],
        "wording_only_signal_ids": [],
        "counter_indicators": [],
        "tone_summary": "",
        "relevant_wording": [],
        "omissions_or_process_signals": [],
        "included_actors": [],
        "excluded_actors": [],
        "communication_classification": empty_communication_classification(),
    }


def normalize_message_behavior_analysis(
    analysis: dict[str, Any] | MessageBehaviorAnalysis | None,
    *,
    text_scope: Literal["authored_text", "quoted_text"] = "authored_text",
) -> MessageBehaviorAnalysis:
    """Normalize a value into a valid MessageBehaviorAnalysis.

    Args:
        analysis: A dict-like analysis to normalize, or None.
        text_scope: The default text scope to use if not present in analysis.

    Returns:
        A valid MessageBehaviorAnalysis with normalized fields. Falls back to
        empty analysis if input is None or invalid.

    """
    base = empty_message_behavior_analysis(text_scope)
    if not isinstance(analysis, dict):
        return base
    analysis = cast(dict[str, Any], analysis)

    behavior_candidates = cast(list[BehaviorCandidate], _dict_items(analysis, "behavior_candidates"))
    relevant_wording = cast(list[RelevantWording], _dict_items(analysis, "relevant_wording"))
    process_signals = cast(list[ProcessSignal], _dict_items(analysis, "omissions_or_process_signals"))
    included_actors = _string_items(analysis, "included_actors")
    excluded_actors = _string_items(analysis, "excluded_actors")
    wording_only_signal_ids = _string_items(analysis, "wording_only_signal_ids")
    counter_indicators = _string_items(analysis, "counter_indicators")
    normalized_scope = str(analysis.get("text_scope") or text_scope)

    return {
        "text_scope": cast(Literal["authored_text", "quoted_text"], normalized_scope),
        "behavior_candidate_count": int(analysis.get("behavior_candidate_count") or len(behavior_candidates)),
        "behavior_candidates": behavior_candidates,
        "wording_only_signal_ids": wording_only_signal_ids,
        "counter_indicators": counter_indicators,
        "tone_summary": str(analysis.get("tone_summary") or ""),
        "relevant_wording": relevant_wording,
        "omissions_or_process_signals": process_signals,
        "included_actors": included_actors,
        "excluded_actors": excluded_actors,
        "communication_classification": normalize_communication_classification(analysis.get("communication_classification")),
    }


def _dict_items(value: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in value.get(key, []) if isinstance(item, dict)]


def _string_items(value: dict[str, Any], key: str) -> list[str]:
    return [str(item) for item in value.get(key, []) if str(item).strip()]


def normalize_message_findings_payload(message_findings: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a message findings payload into a consistent structure.

    Args:
        message_findings: A dict containing authored_text analysis and quoted_blocks,
            or None.

    Returns:
        A normalized findings payload with version, authored_text (normalized),
        quoted_blocks (normalized), and summary (with computed counts).

    """
    findings = message_findings if isinstance(message_findings, dict) else {}
    authored = normalize_message_behavior_analysis(findings.get("authored_text"), text_scope="authored_text")

    quoted_blocks = [_normalized_quoted_block(block) for block in _dict_items(findings, "quoted_blocks")]

    summary = _normalized_findings_summary(findings, authored, quoted_blocks)

    return {
        "version": str(findings.get("version") or MESSAGE_BEHAVIOR_VERSION),
        "authored_text": authored,
        "quoted_blocks": quoted_blocks,
        "summary": summary,
    }


def _normalized_quoted_block(block):
    return {
        "segment_ordinal": int(block.get("segment_ordinal") or 0),
        "segment_type": str(block.get("segment_type") or ""),
        "speaker_email": str(block.get("speaker_email") or ""),
        "speaker_source": str(block.get("speaker_source") or ""),
        "speaker_confidence": float(block.get("speaker_confidence") or 0.0),
        "quote_attribution_status": str(block.get("quote_attribution_status") or ""),
        "quote_attribution_reason": str(block.get("quote_attribution_reason") or ""),
        "candidate_emails": _string_items(block, "candidate_emails"),
        "downgraded_due_to_quote_ambiguity": bool(block.get("downgraded_due_to_quote_ambiguity", True)),
        "findings": normalize_message_behavior_analysis(block.get("findings"), text_scope="quoted_text"),
    }


def _normalized_findings_summary(findings, authored, quoted_blocks):
    summary = dict(findings.get("summary") or {})
    summary.setdefault("authored_behavior_candidate_count", int(authored.get("behavior_candidate_count") or 0))
    summary.setdefault(
        "quoted_behavior_candidate_count",
        sum(int(block["findings"].get("behavior_candidate_count") or 0) for block in quoted_blocks),
    )
    summary.setdefault(
        "total_behavior_candidate_count",
        int(summary["authored_behavior_candidate_count"]) + int(summary["quoted_behavior_candidate_count"]),
    )
    summary.setdefault(
        "wording_only_signal_count",
        len(authored.get("wording_only_signal_ids", []))
        + sum(len(block["findings"].get("wording_only_signal_ids", [])) for block in quoted_blocks),
    )
    return summary
