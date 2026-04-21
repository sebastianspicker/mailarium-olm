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
    "selective_politeness",
    "procedural_intimidation",
    "passive_aggressive_deflection",
    "status_marking",
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
            re.compile(r"\bwie bereits (?:gesagt|erklaert|erklärt|mitgeteilt|erklaert)\b", re.IGNORECASE),
            re.compile(r"\bbitte einfach\b", re.IGNORECASE),
            re.compile(r"\bnur kurz zur erinnerung\b", re.IGNORECASE),
            re.compile(r"\bwie schon mehrfach (?:erklaert|erklärt|mitgeteilt)\b", re.IGNORECASE),
            re.compile(r"\bnochmals zur klarstellung\b", re.IGNORECASE),
            re.compile(r"\bwie bereits bekannt sein duerfte\b", re.IGNORECASE),
            re.compile(r"\bwie bereits bekannt sein dürfte\b", re.IGNORECASE),
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
            re.compile(r"\bich erklaere es noch einmal\b", re.IGNORECASE),
            re.compile(r"\bich erkläre es noch einmal\b", re.IGNORECASE),
            re.compile(r"\bwie sie sicher wissen\b", re.IGNORECASE),
            re.compile(r"\bzu ihrem verstaendnis\b", re.IGNORECASE),
            re.compile(r"\bzu ihrem verständnis\b", re.IGNORECASE),
            re.compile(r"\bzu ihrer orientierung\b", re.IGNORECASE),
            re.compile(r"\bich fuehre das gern noch einmal aus\b", re.IGNORECASE),
            re.compile(r"\bich führe das gern noch einmal aus\b", re.IGNORECASE),
            re.compile(r"\bfalls ihnen das nicht klar sein sollte\b", re.IGNORECASE),
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
            re.compile(r"\bsie haben (?:es versaeumt|es versäumt|unterlassen|verweigert)\b", re.IGNORECASE),
            re.compile(r"\bihr(?:e|en)? (?:versaeumnis|versäumnis|weigerung|unterlassung)\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "competence_framing",
        "label": "Competence Framing",
        "confidence": "medium",
        "rationale": "Frames the recipient as confused, unreliable, or otherwise less credible.",
        "patterns": [
            re.compile(r"\b(?:confused|misunderstood|inaccurate|careless|unreliable|not capable)\b", re.IGNORECASE),
            re.compile(
                r"\b(?:verwirrt|missverstanden|ungenau|nachlaessig|nachlässig|"
                r"unzuverlaessig|unzuverlässig)\b",
                re.IGNORECASE,
            ),
            re.compile(r"\bdas scheint sie zu ueberfordern\b", re.IGNORECASE),
            re.compile(r"\bdas scheint sie zu überfordern\b", re.IGNORECASE),
            re.compile(r"\bihre darstellung ist erneut unzutreffend\b", re.IGNORECASE),
            re.compile(r"\bihre darstellung ist unzutreffend\b", re.IGNORECASE),
            re.compile(r"\bist ihre darstellung unzutreffend\b", re.IGNORECASE),
            re.compile(r"\bwie ueblich unpraezise\b", re.IGNORECASE),
            re.compile(r"\bwie üblich unpräzise\b", re.IGNORECASE),
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
            re.compile(r"\bzur dokumentation\b", re.IGNORECASE),
            re.compile(r"\bnichtbeachtung\b", re.IGNORECASE),
            re.compile(r"\b(?:hr-mailbox|disziplinar|compliance|formaler prozess)\b", re.IGNORECASE),
            re.compile(r"\bmit blick auf den vorgang\b", re.IGNORECASE),
            re.compile(r"\bim rahmen des vorgangs\b", re.IGNORECASE),
            re.compile(r"\bzur weiteren vorlage\b", re.IGNORECASE),
            re.compile(r"\bmit entsprechender aktennotiz\b", re.IGNORECASE),
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
            re.compile(r"\bes steht im raum\b", re.IGNORECASE),
            re.compile(r"\bwie es scheint\b", re.IGNORECASE),
            re.compile(r"\boffenbar\b", re.IGNORECASE),
            re.compile(r"\bder eindruck entsteht\b", re.IGNORECASE),
            re.compile(r"\bnach hiesigem kenntnisstand\b", re.IGNORECASE),
            re.compile(r"\bohne dies hier weiter zu vertiefen\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "selective_politeness",
        "label": "Selective Politeness",
        "confidence": "low",
        "rationale": (
            "Uses formal politeness markers together with distancing or corrective framing that can read as selectively cold."
        ),
        "patterns": [
            re.compile(r"\bwith all due respect\b", re.IGNORECASE),
            re.compile(r"\bkindly note\b", re.IGNORECASE),
            re.compile(r"\bbitte nehmen sie zur kenntnis\b", re.IGNORECASE),
            re.compile(r"\bmit allem respekt\b", re.IGNORECASE),
            re.compile(r"\bwir bitten sie höflich um kenntnisnahme\b", re.IGNORECASE),
            re.compile(r"\bfreundlicherweise beachten sie\b", re.IGNORECASE),
            re.compile(r"\bwir erlauben uns den hinweis\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "procedural_intimidation",
        "label": "Procedural Intimidation",
        "confidence": "medium",
        "rationale": (
            "Leans on rules, documentation, or escalation procedure in a way "
            "that can function as pressure rather than neutral coordination."
        ),
        "patterns": [
            re.compile(r"\bthis will be documented\b", re.IGNORECASE),
            re.compile(r"\bwe will have to escalate this formally\b", re.IGNORECASE),
            re.compile(r"\bnon-?compliance will be noted\b", re.IGNORECASE),
            re.compile(r"\bdies wird dokumentiert\b", re.IGNORECASE),
            re.compile(r"\bdass dies dokumentiert wird\b", re.IGNORECASE),
            re.compile(r"\bwir werden dies formal eskalieren\b", re.IGNORECASE),
            re.compile(r"\bdie nichtbeachtung wird vermerkt\b", re.IGNORECASE),
            re.compile(r"\bwir sehen uns gehalten, dies festzuhalten\b", re.IGNORECASE),
            re.compile(r"\bder vorgang wird entsprechend vermerkt\b", re.IGNORECASE),
            re.compile(r"\bdies wird entsprechend vermerkt\b", re.IGNORECASE),
            re.compile(r"\bdass der vorgang entsprechend vermerkt wird\b", re.IGNORECASE),
            re.compile(r"\beine weitere eskalation behalten wir uns vor\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "passive_aggressive_deflection",
        "label": "Passive-aggressive Deflection",
        "confidence": "low",
        "rationale": (
            "Uses superficially neutral phrasing to redirect responsibility or "
            "close discussion without engaging the substance directly."
        ),
        "patterns": [
            re.compile(r"\bi trust this clarifies matters\b", re.IGNORECASE),
            re.compile(r"\bif anything remains unclear, that is on you\b", re.IGNORECASE),
            re.compile(r"\bwie ich hoffe, ist die sache damit geklaert\b", re.IGNORECASE),
            re.compile(r"\bdamit duerfte alles gesagt sein\b", re.IGNORECASE),
            re.compile(r"\bdamit dürfte alles gesagt sein\b", re.IGNORECASE),
            re.compile(r"\bweitere rueckfragen eruebrigen sich\b", re.IGNORECASE),
            re.compile(r"\bweitere rückfragen erübrigen sich\b", re.IGNORECASE),
            re.compile(r"\bich gehe davon aus, dass damit alles geklaert ist\b", re.IGNORECASE),
            re.compile(r"\bich gehe davon aus, dass damit alles geklärt ist\b", re.IGNORECASE),
            re.compile(r"\bich gehe davon aus, dass sich weitere rueckfragen eruebrigen\b", re.IGNORECASE),
            re.compile(r"\bich gehe davon aus, dass sich weitere rückfragen erübrigen\b", re.IGNORECASE),
            re.compile(r"\bgehe ich davon aus, dass sich weitere rueckfragen eruebrigen\b", re.IGNORECASE),
            re.compile(r"\bgehe ich davon aus, dass sich weitere rückfragen erübrigen\b", re.IGNORECASE),
        ],
    },
    {
        "signal_id": "status_marking",
        "label": "Status Marking",
        "confidence": "low",
        "rationale": "Highlights hierarchy or role status in a way that can add social pressure beyond the content itself.",
        "patterns": [
            re.compile(r"\bas your manager\b", re.IGNORECASE),
            re.compile(r"\bin my capacity as\b", re.IGNORECASE),
            re.compile(r"\bin meiner funktion als\b", re.IGNORECASE),
            re.compile(r"\bals ihre? vorgesetzte?r?\b", re.IGNORECASE),
            re.compile(r"\bals leitung\b", re.IGNORECASE),
            re.compile(r"\bals verantwortliche stelle\b", re.IGNORECASE),
            re.compile(r"\bals zuständige stelle\b", re.IGNORECASE),
        ],
    },
]

_ALREADY_STATED_RE = re.compile(r"\bas already (?:stated|explained|noted)\b", re.IGNORECASE)
_GERMAN_ALREADY_STATED_RE = re.compile(
    r"\b(?:wie bereits|wie schon mehrfach) (?:gesagt|erklaert|erklärt|mitgeteilt)\b",
    re.IGNORECASE,
)
_CORRECTION_RE = re.compile(
    r"\b(?:you are mistaken|you misunderstood|you are confused|sie irren sich|"
    r"sie haben das missverstanden|sie sind offenbar verwirrt|"
    r"das ist unzutreffend|ihre darstellung ist unzutreffend|"
    r"ist ihre darstellung unzutreffend|"
    r"sie stellen den sachverhalt falsch dar)\b",
    re.IGNORECASE,
)


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
    if not prior_statement:
        prior_statement = _GERMAN_ALREADY_STATED_RE.search(text)
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
