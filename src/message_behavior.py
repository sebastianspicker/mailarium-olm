"""Per-message behavioural tagging helpers for behavioural analysis."""

from __future__ import annotations

import re
from typing import Literal, TypedDict, cast

from .language_rhetoric import MessageRhetoricAnalysis

MESSAGE_BEHAVIOR_VERSION = "1"

BehaviorCandidateId = Literal[
    "exclusion",
    "escalation",
    "public_correction",
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


class MessageBehaviorAnalysis(TypedDict):
    """Behaviour candidates for one authored or quoted text span."""

    text_scope: Literal["authored_text", "quoted_text"]
    behavior_candidate_count: int
    behavior_candidates: list[BehaviorCandidate]
    wording_only_signal_ids: list[str]
    counter_indicators: list[str]


_DEADLINE_RE = re.compile(
    r"\b(?:today|by end of day|by eod|immediately|without delay|as soon as possible|asap|by tomorrow)\b",
    re.IGNORECASE,
)
_ESCALATION_RE = re.compile(
    r"\b(?:escalat(?:e|ion)|hr|formal process|disciplinary|compliance|for the record)\b",
    re.IGNORECASE,
)
_SELECTIVE_ACCOUNTABILITY_RE = re.compile(
    r"\b(?:you alone|only you|solely your responsibility|you must ensure|your responsibility)\b",
    re.IGNORECASE,
)
_DECISION_UPDATE_RE = re.compile(
    r"\b(?:we decided|we will proceed|approved|decision has been made|update follows)\b",
    re.IGNORECASE,
)


def _signal_ids(rhetoric: MessageRhetoricAnalysis) -> list[str]:
    """Return the signal ids from one rhetoric analysis object."""
    return [str(signal["signal_id"]) for signal in rhetoric.get("signals", [])]


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


def analyze_message_behavior(
    text: str,
    *,
    text_scope: Literal["authored_text", "quoted_text"],
    rhetoric: MessageRhetoricAnalysis,
    recipient_count: int = 0,
    visible_recipient_emails: list[str] | None = None,
    case_target_email: str = "",
    case_target_name: str = "",
) -> MessageBehaviorAnalysis:
    """Return bounded message-level behaviour candidates derived from text and context."""
    visible_recipient_emails = [str(email).strip().lower() for email in (visible_recipient_emails or []) if email]
    target_email = case_target_email.strip().lower()
    signal_ids = _signal_ids(rhetoric)
    behavior_candidates: list[BehaviorCandidate] = []
    consumed_signal_ids: set[str] = set()
    counter_indicators: list[str] = []

    if "institutional_pressure_framing" in signal_ids:
        behavior_candidates.append(
            _candidate(
                behavior_id="escalation",
                label="Escalation",
                confidence="medium",
                taxonomy_ids=["escalation_pressure"],
                rationale=(
                    "Escalation or formal-process wording suggests a behaviour-level "
                    "pressure move rather than wording alone."
                ),
                evidence=_signal_evidence(rhetoric, signal_id="institutional_pressure_framing"),
                derived_from_signal_ids=["institutional_pressure_framing"],
                neutral_alternatives=[
                    "Routine escalation may be required by policy or time pressure.",
                ],
            )
        )
        consumed_signal_ids.add("institutional_pressure_framing")

    deadline_evidence = _match_evidence(text, pattern=_DEADLINE_RE, source_scope=text_scope)
    if deadline_evidence:
        behavior_candidates.append(
            _candidate(
                behavior_id="deadline_pressure",
                label="Deadline Pressure",
                confidence="medium",
                taxonomy_ids=["escalation_pressure", "unequal_demands"],
                rationale="Time-pressure wording suggests an action-demanding behavioural cue beyond tone alone.",
                evidence=deadline_evidence,
                derived_from_signal_ids=[],
                neutral_alternatives=[
                    "The deadline may be operationally justified or genuinely urgent.",
                ],
            )
        )

    if recipient_count > 1 and (
        "implicit_accusation" in signal_ids or "competence_framing" in signal_ids or "ridicule" in signal_ids
    ):
        derived_from = [
            signal_id
            for signal_id in ("implicit_accusation", "competence_framing", "ridicule")
            if signal_id in signal_ids
        ]
        evidence = (
            _signal_evidence(rhetoric, signal_id=derived_from[0])
            if derived_from
            else _metadata_evidence(
                excerpt=f"Message has {recipient_count} visible recipients.",
                matched_text=f"recipient_count={recipient_count}",
            )
        )
        behavior_candidates.append(
            _candidate(
                behavior_id="public_correction",
                label="Public Correction",
                confidence="medium",
                taxonomy_ids=["public_criticism"],
                rationale=(
                    "Corrective or accusatory wording sent to multiple visible "
                    "recipients can indicate a public-correction behaviour."
                ),
                evidence=evidence,
                derived_from_signal_ids=derived_from,
                neutral_alternatives=[
                    "A wider recipient list may be operationally necessary for shared work tracking.",
                ],
            )
        )
        consumed_signal_ids.update(derived_from)
    elif recipient_count <= 1:
        counter_indicators.append("No multi-recipient visibility for public-correction inference.")

    if {"competence_framing", "ridicule", "patronizing_wording"} & set(signal_ids):
        derived_from = [
            signal_id
            for signal_id in ("competence_framing", "ridicule", "patronizing_wording")
            if signal_id in signal_ids
        ]
        behavior_candidates.append(
            _candidate(
                behavior_id="undermining",
                label="Undermining",
                confidence="medium",
                taxonomy_ids=["undermining_credibility"],
                rationale="Credibility- or capability-framing can indicate an undermining behaviour rather than tone alone.",
                evidence=_signal_evidence(rhetoric, signal_id=derived_from[0]),
                derived_from_signal_ids=derived_from,
                neutral_alternatives=[
                    "The wording may reflect a one-off correction or performance "
                    "concern rather than a broader behavioural pattern.",
                ],
            )
        )
        consumed_signal_ids.update(derived_from)

    selective_accountability_evidence = _match_evidence(
        text,
        pattern=_SELECTIVE_ACCOUNTABILITY_RE,
        source_scope=text_scope,
    )
    if selective_accountability_evidence:
        behavior_candidates.append(
            _candidate(
                behavior_id="selective_accountability",
                label="Selective Accountability",
                confidence="medium",
                taxonomy_ids=["unequal_demands", "blame_shifting"],
                rationale=(
                    "Language assigning sole or exceptional responsibility suggests "
                    "a selective-accountability behaviour candidate."
                ),
                evidence=selective_accountability_evidence,
                derived_from_signal_ids=[],
                neutral_alternatives=[
                    "The actor may genuinely own the task in that specific workflow.",
                ],
            )
        )

    target_named = bool(case_target_name and case_target_name.lower() in (text or "").lower())
    target_excluded = bool(target_email and visible_recipient_emails and target_email not in visible_recipient_emails)
    if text_scope == "authored_text" and target_excluded and (target_named or target_email in (text or "").lower()):
        behavior_candidates.append(
            _candidate(
                behavior_id="exclusion",
                label="Exclusion",
                confidence="low",
                taxonomy_ids=["exclusion"],
                rationale=(
                    "The case target is referenced in the message context but is "
                    "absent from visible recipients, which can support an exclusion "
                    "hypothesis."
                ),
                evidence=_metadata_evidence(
                    excerpt=(
                        f"Target {target_email or case_target_name} absent from visible recipients "
                        f"{visible_recipient_emails}."
                    ),
                    matched_text=target_email or case_target_name,
                ),
                derived_from_signal_ids=[],
                neutral_alternatives=[
                    "The message may concern the target without requiring them as a recipient.",
                ],
            )
        )
        if _DECISION_UPDATE_RE.search(text or ""):
            behavior_candidates.append(
                _candidate(
                    behavior_id="withholding",
                    label="Withholding Information",
                    confidence="low",
                    taxonomy_ids=["withholding_information", "exclusion"],
                    rationale=(
                        "Decision- or update-framing combined with target absence can "
                        "suggest a withholding-information behaviour candidate."
                    ),
                    evidence=_metadata_evidence(
                        excerpt=(
                            f"Decision/update wording present while target {target_email or case_target_name} "
                            f"is absent from visible recipients {visible_recipient_emails}."
                        ),
                        matched_text=target_email or case_target_name,
                    ),
                    derived_from_signal_ids=[],
                    neutral_alternatives=[
                        "The update may be preparatory and later communicated to the target through another channel.",
                    ],
                )
            )
    elif text_scope == "authored_text" and target_email:
        counter_indicators.append(
            "Case target appears in visible recipients, so omission-based "
            "exclusion checks stayed negative."
        )
    elif text_scope == "authored_text" and not target_email:
        counter_indicators.append("No case target email available for omission-aware checks.")

    wording_only_signal_ids = [
        signal_id for signal_id in signal_ids if signal_id not in consumed_signal_ids
    ]
    if wording_only_signal_ids:
        counter_indicators.append(
            "Some rhetorical cues remained wording-only because message-level "
            "behavioural support was insufficient."
        )

    return {
        "text_scope": text_scope,
        "behavior_candidate_count": len(behavior_candidates),
        "behavior_candidates": behavior_candidates,
        "wording_only_signal_ids": wording_only_signal_ids,
        "counter_indicators": counter_indicators,
    }
