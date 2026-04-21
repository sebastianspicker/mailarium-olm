"""Per-message language and rhetoric tagging helpers for behavioural analysis."""

from __future__ import annotations

import re
from typing import Literal, TypedDict

LANGUAGE_RHETORIC_VERSION = "1"

RhetoricalSignalId = Literal[
    "dismissiveness",
    "ridicule",
    "patronizing_wording",
    "implicit_accusation",
    "competence_framing",
    "institutional_pressure_framing",
    "strategic_ambiguity",
    "gaslighting_like_contradiction",
]
RhetoricalConfidence = Literal["high", "medium", "low"]
RhetoricalTextScope = Literal["authored_text", "quoted_text"]


class RhetoricalEvidence(TypedDict):
    """Concrete textual support for one rhetorical signal."""

    source_text_scope: RhetoricalTextScope
    excerpt: str
    matched_text: str
    start: int
    end: int


class RhetoricalSignal(TypedDict):
    """One detected rhetorical signal with bounded evidence."""

    signal_id: RhetoricalSignalId
    label: str
    confidence: RhetoricalConfidence
    rationale: str
    evidence: list[RhetoricalEvidence]


class MessageRhetoricAnalysis(TypedDict):
    """Per-surface language analysis for one authored or quoted text span."""

    text_scope: RhetoricalTextScope
    signal_count: int
    signals: list[RhetoricalSignal]


class _SignalPattern(TypedDict):
    signal_id: RhetoricalSignalId
    label: str
    confidence: RhetoricalConfidence
    rationale: str
    patterns: list[re.Pattern[str]]


_SIGNAL_PATTERNS: list[_SignalPattern] = [
    {
        "signal_id": "dismissiveness",
        "label": "Dismissiveness",
        "confidence": "medium",
        "rationale": "Contains minimizing or shorthand-dismissive phrasing aimed at closing discussion.",
        "patterns": [
            re.compile(r"\bas already (?:stated|explained|noted)\b", re.IGNORECASE),
            re.compile(r"\bplease just\b", re.IGNORECASE),
            re.compile(r"\bsimply\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "ridicule",
        "label": "Ridicule",
        "confidence": "high",
        "rationale": "Uses openly derisive wording instead of neutral criticism.",
        "patterns": [
            re.compile(r"\b(?:ridiculous|absurd|laughable|nonsense)\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "patronizing_wording",
        "label": "Patronizing Wording",
        "confidence": "medium",
        "rationale": "Uses wording that positions the recipient as less capable or less informed.",
        "patterns": [
            re.compile(r"\blet me explain again\b", re.IGNORECASE),
            re.compile(r"\bas you surely know\b", re.IGNORECASE),
            re.compile(r"\bfor your understanding\b", re.IGNORECASE),
            re.compile(r"\bperhaps you are unaware\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "implicit_accusation",
        "label": "Implicit Accusation",
        "confidence": "medium",
        "rationale": "Frames the recipient as having failed, refused, or omitted something without neutral phrasing.",
        "patterns": [
            re.compile(r"\byou (?:failed|refused|neglected|omitted)\b", re.IGNORECASE),
            re.compile(r"\byour (?:failure|refusal|omission)\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "competence_framing",
        "label": "Competence Framing",
        "confidence": "medium",
        "rationale": "Frames the recipient as confused, unreliable, or otherwise less credible.",
        "patterns": [
            re.compile(r"\b(?:confused|misunderstood|inaccurate|careless|unreliable|not capable)\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "institutional_pressure_framing",
        "label": "Institutional Pressure Framing",
        "confidence": "high",
        "rationale": "Invokes formal process, escalation, or compliance language as pressure rather than neutral coordination.",
        "patterns": [
            re.compile(r"\bfor the record\b", re.IGNORECASE),
            re.compile(r"\bfailure to comply\b", re.IGNORECASE),
            re.compile(r"\bescalat(?:e|ion)\b", re.IGNORECASE),
            re.compile(r"\b(?:hr|formal process|disciplinary|compliance)\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "strategic_ambiguity",
        "label": "Strategic Ambiguity",
        "confidence": "low",
        "rationale": "Uses vague concern-framing without clearly stating the underlying claim or basis.",
        "patterns": [
            re.compile(r"\bconcerns have been raised\b", re.IGNORECASE),
            re.compile(r"\bit appears\b", re.IGNORECASE),
            re.compile(r"\bit seems\b", re.IGNORECASE),
            re.compile(r"\bquestions remain\b", re.IGNORECASE),
        ],
    },
]

_ALREADY_STATED_RE = re.compile(r"\bas already (?:stated|explained|noted)\b", re.IGNORECASE)
_CORRECTION_RE = re.compile(r"\b(?:you are mistaken|you misunderstood|you are confused)\b", re.IGNORECASE)


def _excerpt(text: str, start: int, end: int, *, radius: int = 48) -> str:
    """Return a compact excerpt around the matched text."""
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())


def _pattern_signal(
    *,
    signal_pattern: _SignalPattern,
    text: str,
    text_scope: RhetoricalTextScope,
) -> RhetoricalSignal | None:
    """Return one signal object for the first matching pattern, if any."""
    evidence: list[RhetoricalEvidence] = []
    for pattern in signal_pattern["patterns"]:
        match = pattern.search(text)
        if not match:
            continue
        evidence.append(
            {
                "source_text_scope": text_scope,
                "excerpt": _excerpt(text, match.start(), match.end()),
                "matched_text": match.group(0),
                "start": match.start(),
                "end": match.end(),
            }
        )
        break
    if not evidence:
        return None
    return {
        "signal_id": signal_pattern["signal_id"],
        "label": signal_pattern["label"],
        "confidence": signal_pattern["confidence"],
        "rationale": signal_pattern["rationale"],
        "evidence": evidence,
    }


def _gaslighting_like_signal(text: str, text_scope: RhetoricalTextScope) -> RhetoricalSignal | None:
    """Return a bounded contradiction-pattern signal when both cue families are present."""
    prior_statement = _ALREADY_STATED_RE.search(text)
    correction = _CORRECTION_RE.search(text)
    if not prior_statement or not correction:
        return None
    return {
        "signal_id": "gaslighting_like_contradiction",
        "label": "Gaslighting-like Contradiction Pattern",
        "confidence": "low",
        "rationale": (
            "Pairs prior-statement framing with recipient-confusion framing, "
            "which can support a contradiction-style pressure reading."
        ),
        "evidence": [
            {
                "source_text_scope": text_scope,
                "excerpt": _excerpt(text, prior_statement.start(), correction.end()),
                "matched_text": f"{prior_statement.group(0)} / {correction.group(0)}",
                "start": prior_statement.start(),
                "end": correction.end(),
            }
        ],
    }


def analyze_message_rhetoric(text: str, *, text_scope: RhetoricalTextScope) -> MessageRhetoricAnalysis:
    """Return bounded rhetorical-signal analysis for one authored or quoted text span."""
    signals: list[RhetoricalSignal] = []
    for signal_pattern in _SIGNAL_PATTERNS:
        signal = _pattern_signal(signal_pattern=signal_pattern, text=text or "", text_scope=text_scope)
        if signal is not None:
            signals.append(signal)
    contradiction_signal = _gaslighting_like_signal(text or "", text_scope)
    if contradiction_signal is not None:
        signals.append(contradiction_signal)
    return {
        "text_scope": text_scope,
        "signal_count": len(signals),
        "signals": signals,
    }
