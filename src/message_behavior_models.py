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
    text: str
    source_scope: BehaviorEvidenceScope
    basis_id: str


class ProcessSignal(TypedDict):
    signal: str
    summary: str


class CommunicationClassification(TypedDict):
    primary_class: CommunicationClass
    applied_classes: list[CommunicationClass]
    confidence: BehaviorConfidence
    rationale: str


class MessageBehaviorAnalysis(TypedDict):
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
    return {
        "primary_class": "neutral",
        "applied_classes": ["neutral"],
        "confidence": "low",
        "rationale": "",
    }


def normalize_communication_classification(value: Any) -> CommunicationClassification:
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
    base = empty_message_behavior_analysis(text_scope)
    if not isinstance(analysis, dict):
        return base

    behavior_candidates = cast(
        list[BehaviorCandidate],
        [item for item in analysis.get("behavior_candidates", []) if isinstance(item, dict)],
    )
    relevant_wording = cast(
        list[RelevantWording],
        [item for item in analysis.get("relevant_wording", []) if isinstance(item, dict)],
    )
    process_signals = cast(
        list[ProcessSignal],
        [item for item in analysis.get("omissions_or_process_signals", []) if isinstance(item, dict)],
    )
    included_actors = [str(item) for item in analysis.get("included_actors", []) if str(item).strip()]
    excluded_actors = [str(item) for item in analysis.get("excluded_actors", []) if str(item).strip()]
    wording_only_signal_ids = [str(item) for item in analysis.get("wording_only_signal_ids", []) if str(item).strip()]
    counter_indicators = [str(item) for item in analysis.get("counter_indicators", []) if str(item).strip()]
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


def normalize_message_findings_payload(message_findings: dict[str, Any] | None) -> dict[str, Any]:
    findings = message_findings if isinstance(message_findings, dict) else {}
    authored = normalize_message_behavior_analysis(findings.get("authored_text"), text_scope="authored_text")

    quoted_blocks: list[dict[str, Any]] = []
    for block in findings.get("quoted_blocks", []) if isinstance(findings.get("quoted_blocks"), list) else []:
        if not isinstance(block, dict):
            continue
        quoted_blocks.append(
            {
                "segment_ordinal": int(block.get("segment_ordinal") or 0),
                "segment_type": str(block.get("segment_type") or ""),
                "speaker_email": str(block.get("speaker_email") or ""),
                "speaker_source": str(block.get("speaker_source") or ""),
                "speaker_confidence": float(block.get("speaker_confidence") or 0.0),
                "quote_attribution_status": str(block.get("quote_attribution_status") or ""),
                "quote_attribution_reason": str(block.get("quote_attribution_reason") or ""),
                "candidate_emails": [str(item) for item in block.get("candidate_emails", []) if str(item).strip()],
                "downgraded_due_to_quote_ambiguity": bool(block.get("downgraded_due_to_quote_ambiguity", True)),
                "findings": normalize_message_behavior_analysis(block.get("findings"), text_scope="quoted_text"),
            }
        )

    summary = dict(findings.get("summary") or {})
    if "authored_behavior_candidate_count" not in summary:
        summary["authored_behavior_candidate_count"] = int(authored.get("behavior_candidate_count") or 0)
    if "quoted_behavior_candidate_count" not in summary:
        summary["quoted_behavior_candidate_count"] = sum(
            int(block["findings"].get("behavior_candidate_count") or 0) for block in quoted_blocks
        )
    if "total_behavior_candidate_count" not in summary:
        summary["total_behavior_candidate_count"] = int(summary["authored_behavior_candidate_count"]) + int(
            summary["quoted_behavior_candidate_count"]
        )
    if "wording_only_signal_count" not in summary:
        summary["wording_only_signal_count"] = len(authored.get("wording_only_signal_ids", [])) + sum(
            len(block["findings"].get("wording_only_signal_ids", [])) for block in quoted_blocks
        )

    return {
        "version": str(findings.get("version") or MESSAGE_BEHAVIOR_VERSION),
        "authored_text": authored,
        "quoted_blocks": quoted_blocks,
        "summary": summary,
    }
