"""Evidence and candidate helpers for message-level behaviour analysis."""

from __future__ import annotations

import re
from typing import Literal, TypedDict, cast

from .language_rhetoric import MessageRhetoricAnalysis

BehaviorCandidateId = Literal[
    "exclusion",
    "escalation",
    "blame_shifting",
    "public_correction",
    "selective_non_response",
    "withholding",
    "selective_accountability",
    "deadline_pressure",
    "undermining",
]
BehaviorConfidence = Literal["high", "medium", "low"]
BehaviorEvidenceScope = Literal["authored_text", "quoted_text", "message_metadata"]


class BehaviorEvidence(TypedDict):
    """Concrete textual or metadata support for one behavioural candidate."""

    source_scope: BehaviorEvidenceScope
    excerpt: str
    matched_text: str
    start: int
    end: int


class BehaviorCandidate(TypedDict):
    """One message-level behaviour candidate."""

    behavior_id: BehaviorCandidateId
    label: str
    confidence: BehaviorConfidence
    taxonomy_ids: list[str]
    rationale: str
    evidence: list[BehaviorEvidence]
    derived_from_signal_ids: list[str]
    neutral_alternatives: list[str]


def _signal_evidence(
    rhetoric: MessageRhetoricAnalysis,
    *,
    signal_id: str,
) -> list[BehaviorEvidence]:
    """Reuse the first matching rhetoric evidence item for a behaviour candidate."""
    for signal in rhetoric.get("signals", []):
        if str(signal.get("signal_id") or "") != signal_id:
            continue
        evidence = signal.get("evidence") or []
        if not evidence:
            return []
        first = evidence[0]
        source_scope = cast(
            BehaviorEvidenceScope,
            str(first.get("source_text_scope") or "authored_text"),
        )
        return [
            {
                "source_scope": source_scope,
                "excerpt": str(first.get("excerpt") or ""),
                "matched_text": str(first.get("matched_text") or ""),
                "start": int(first.get("start") or 0),
                "end": int(first.get("end") or 0),
            }
        ]
    return []


def _match_evidence(
    text: str,
    *,
    pattern: re.Pattern[str],
    source_scope: BehaviorEvidenceScope,
) -> list[BehaviorEvidence]:
    """Return concrete pattern evidence for one text match, if any."""
    match = pattern.search(text or "")
    if not match:
        return []
    left = max(0, match.start() - 48)
    right = min(len(text), match.end() + 48)
    return [
        {
            "source_scope": source_scope,
            "excerpt": " ".join(text[left:right].split()),
            "matched_text": match.group(0),
            "start": match.start(),
            "end": match.end(),
        }
    ]


def _metadata_evidence(*, excerpt: str, matched_text: str) -> list[BehaviorEvidence]:
    """Return one metadata-only evidence item for omission-aware findings."""
    return [
        {
            "source_scope": "message_metadata",
            "excerpt": excerpt,
            "matched_text": matched_text,
            "start": 0,
            "end": 0,
        }
    ]


def _candidate(
    *,
    behavior_id: BehaviorCandidateId,
    label: str,
    confidence: BehaviorConfidence,
    taxonomy_ids: list[str],
    rationale: str,
    evidence: list[BehaviorEvidence],
    derived_from_signal_ids: list[str],
    neutral_alternatives: list[str],
) -> BehaviorCandidate:
    """Build one behaviour candidate."""
    return {
        "behavior_id": behavior_id,
        "label": label,
        "confidence": confidence,
        "taxonomy_ids": taxonomy_ids,
        "rationale": rationale,
        "evidence": evidence,
        "derived_from_signal_ids": derived_from_signal_ids,
        "neutral_alternatives": neutral_alternatives,
    }
