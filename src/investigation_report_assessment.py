"""Assessment-oriented helpers for investigation reports."""
# pylint: disable=too-many-branches,too-many-locals

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .behavioral_interpretation_policy import guarded_statement_for_finding
from .investigation_report_sections import _as_dict, _as_list, _section_with_entries, _title

ASSESSMENT_ORDER = [
    "retaliation_concern",
    "discrimination_concern",
    "unequal_treatment_concern",
    "mobbing_like_pattern_concern",
    "targeted_hostility_concern",
    "ordinary_workplace_conflict",
    "poor_communication_or_process_noise",
    "insufficient_evidence",
]

NON_WEAK_STRENGTHS = {"strong_indicator", "moderate_indicator"}
DISCRIMINATION_PROTECTED_CONTEXTS = {"illness", "disability"}
_CLASSIFICATION_WEAK_PREFIX = (
    "The current record remains best classified as insufficient evidence because the supported findings do not rise above "
)
_MIXED_EVIDENCE_STATEMENT = (
    "The record remains mixed: some supported indicators point toward a problematic pattern, "
    "but material counterarguments and alternative explanations remain live."
)
_MIXED_EVIDENCE_POLICY = (
    "The overall assessment must surface mixed-evidence conditions when support and counterweight both matter."
)
_SECONDARY_POLICY = "Multiple bounded review categories remain plausible, so the renderer keeps alternative readings visible."


def derive_primary_assessment(
    findings: list[dict[str, Any]],
    *,
    case_bundle: dict[str, Any],
    comparative_treatment: dict[str, Any],
    strongest_label: str,
    dominant_claim_level: str,
) -> tuple[str, list[str]]:
    """Return one bounded primary assessment plus secondary plausible interpretations."""
    if not findings:
        return "insufficient_evidence", []

    metrics = _assessment_metrics(findings)
    discrimination_supported = supports_discrimination_concern(
        findings=findings,
        case_bundle=case_bundle,
        comparative_treatment=comparative_treatment,
        strongest_label=strongest_label,
    )

    if strongest_label == "weak_indicator":
        ordered_secondary = [
            candidate
            for candidate in ASSESSMENT_ORDER
            if candidate in _weak_assessment_candidates(metrics) and candidate != "insufficient_evidence"
        ]
        return "insufficient_evidence", ordered_secondary[:2]
    candidates = _assessment_candidates(metrics, discrimination_supported, strongest_label, dominant_claim_level)
    ordered = [candidate for candidate in ASSESSMENT_ORDER if candidate in candidates]
    primary = ordered[0] if ordered else "insufficient_evidence"
    secondary = [candidate for candidate in ordered[1:] if candidate != primary][:2]
    return primary, secondary


def _assessment_metrics(findings: list[dict[str, Any]]) -> dict[str, Any]:
    scopes = Counter(str(finding.get("finding_scope") or "") for finding in findings)
    return {
        "scopes": scopes,
        "direct": scopes.get("message_behavior", 0),
        "patterns": sum(scopes.get(scope, 0) for scope in ("case_pattern", "communication_graph", "retaliation_analysis")),
        "strong": sum(
            1 for finding in findings if str(_as_dict(finding.get("evidence_strength")).get("label") or "") in NON_WEAK_STRENGTHS
        ),
    }


def _weak_assessment_candidates(metrics: dict[str, Any]) -> list[str]:
    scopes = metrics["scopes"]
    candidates = ["poor_communication_or_process_noise"]
    if scopes.get("retaliation_analysis", 0):
        candidates.append("retaliation_concern")
    if scopes.get("comparative_treatment", 0):
        candidates.append("unequal_treatment_concern")
    if metrics["direct"]:
        candidates.append("ordinary_workplace_conflict")
    return candidates


def _assessment_candidates(metrics: dict[str, Any], discrimination: bool, strongest: str, claim_level: str) -> list[str]:
    scopes, direct, patterns = metrics["scopes"], metrics["direct"], metrics["patterns"]
    candidates = [
        name
        for name, enabled in (
            ("retaliation_concern", bool(scopes.get("retaliation_analysis", 0))),
            ("discrimination_concern", discrimination),
            ("unequal_treatment_concern", bool(scopes.get("comparative_treatment", 0))),
            ("mobbing_like_pattern_concern", metrics["strong"] >= 3 and direct and scopes.get("case_pattern", 0)),
            ("targeted_hostility_concern", _supports_targeted_hostility(scopes, direct)),
            ("ordinary_workplace_conflict", claim_level == "observed_fact" and direct and not patterns),
            ("poor_communication_or_process_noise", _supports_process_noise(scopes, direct, patterns, strongest)),
        )
        if enabled
    ]
    return candidates or ["insufficient_evidence"]


def _supports_targeted_hostility(scopes: Counter[str], direct: int) -> bool:
    return bool(
        direct or scopes.get("case_pattern", 0) or scopes.get("communication_graph", 0) or scopes.get("comparative_treatment", 0)
    )


def _supports_process_noise(scopes: Counter[str], direct: int, patterns: int, strongest: str) -> bool:
    return not patterns and not direct and not scopes.get("comparative_treatment", 0) and strongest in NON_WEAK_STRENGTHS


def has_mixed_evidence(findings: list[dict[str, Any]]) -> bool:
    """Return true when the record has meaningful support alongside material contrary indicators."""
    if not findings:
        return False
    if not _has_non_weak_support(findings):
        return False
    alternative_count = _alternative_count(findings)
    low_confidence = _has_low_confidence(findings)
    quote_ambiguity = _has_quote_ambiguity(findings)
    weak_support_present = _has_weak_support(findings)
    return alternative_count >= 2 or (alternative_count >= 1 and (low_confidence or quote_ambiguity or weak_support_present))


def _has_non_weak_support(findings: list[dict[str, Any]]) -> bool:
    return any(str(_as_dict(finding.get("evidence_strength")).get("label") or "") in NON_WEAK_STRENGTHS for finding in findings)


def _alternative_count(findings: list[dict[str, Any]]) -> int:
    return sum(
        1
        for finding in findings
        if _as_list(finding.get("alternative_explanations")) or _as_list(finding.get("counter_indicators"))
    )


def _has_low_confidence(findings: list[dict[str, Any]]) -> bool:
    return any(
        str(_as_dict(_as_dict(finding.get("confidence_split")).get("interpretation_confidence")).get("label") or "") == "low"
        for finding in findings
    )


def _has_quote_ambiguity(findings: list[dict[str, Any]]) -> bool:
    return any(bool(_as_dict(finding.get("quote_ambiguity")).get("downgraded_due_to_quote_ambiguity")) for finding in findings)


def _has_weak_support(findings: list[dict[str, Any]]) -> bool:
    return any(str(_as_dict(finding.get("evidence_strength")).get("label") or "") == "weak_indicator" for finding in findings)


def scope_has_protected_context(case_bundle: dict[str, Any]) -> bool:
    """Return whether the structured intake carries protected-context support."""
    scope = _as_dict(case_bundle.get("scope"))
    org_context = _as_dict(scope.get("org_context"))
    vulnerability_contexts = [
        context for context in _as_list(org_context.get("vulnerability_contexts")) if isinstance(context, dict)
    ]
    return any(str(context.get("context_type") or "") in DISCRIMINATION_PROTECTED_CONTEXTS for context in vulnerability_contexts)


def supports_discrimination_concern(
    *,
    findings: list[dict[str, Any]],
    case_bundle: dict[str, Any],
    comparative_treatment: dict[str, Any],
    strongest_label: str,
) -> bool:
    """Return whether the current record satisfies the bounded discrimination gate."""
    labels = [str(finding.get("finding_label") or "").lower() for finding in findings]
    explicit_discriminatory_content = any("discrimination" in label for label in labels) and strongest_label == "strong_indicator"
    if explicit_discriminatory_content:
        return True
    if not scope_has_protected_context(case_bundle):
        return False
    comparator_summaries = [
        summary for summary in _as_list(comparative_treatment.get("comparator_summaries")) if isinstance(summary, dict)
    ]
    return any(bool(summary.get("supports_discrimination_concern")) for summary in comparator_summaries)


def overall_downgrade_reasons(
    findings: list[dict[str, Any]],
    *,
    case_bundle: dict[str, Any],
    comparative_treatment: dict[str, Any],
    strongest_label: str,
) -> list[str]:
    """Return stable downgrade reasons for the overall assessment block."""
    reasons = _base_downgrade_reasons(findings, strongest_label)
    if _discrimination_remains_gated(findings, case_bundle, comparative_treatment, strongest_label):
        reasons.append(_DISCRIMINATION_GATE_REASON)
    return reasons


_DISCRIMINATION_GATE_REASON = (
    "Discrimination concern remains gated because the current record lacks explicit discriminatory content, "
    "high-quality comparator asymmetry, or structured protected-context support."
)


def _base_downgrade_reasons(findings: list[dict[str, Any]], strongest_label: str) -> list[str]:
    checks = (
        (strongest_label == "weak_indicator", "The strongest supported findings remain in the weak-indicator range."),
        (_has_low_confidence(findings), "At least one relevant finding has low interpretation confidence."),
        (_has_quote_ambiguity(findings), "Quoted-speaker ambiguity downgrades part of the current record."),
        (_has_insufficient_support(findings), "Some findings remain too weak for stronger interpretation."),
        (has_mixed_evidence(findings), "The current record contains mixed evidence and material alternative explanations."),
    )
    return [reason for enabled, reason in checks if enabled]


def _has_insufficient_support(findings: list[dict[str, Any]]) -> bool:
    return any(
        str(_as_dict(finding.get("evidence_strength")).get("label") or "") == "insufficient_evidence" for finding in findings
    )


def _discrimination_remains_gated(
    findings: list[dict[str, Any]], case_bundle: dict[str, Any], comparative: dict[str, Any], strongest: str
) -> bool:
    focus = {str(item) for item in _as_list(_as_dict(case_bundle.get("scope")).get("allegation_focus")) if item}
    return "discrimination" in focus and not supports_discrimination_concern(
        findings=findings, case_bundle=case_bundle, comparative_treatment=comparative, strongest_label=strongest
    )


def overall_assessment_section(
    findings: list[dict[str, Any]],
    *,
    case_bundle: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    """Return the overall-assessment section."""
    if not findings:
        return _empty_assessment_section()
    context = _assessment_context(findings, case_bundle, comparative_treatment)
    entries = _assessment_entries(context)
    section = _section_with_entries(
        section_id="overall_assessment",
        title="Overall Assessment",
        entries=entries,
        insufficiency_reason="The current case bundle does not yet support an overall assessment.",
    )
    section.update(
        {
            "primary_assessment": context.primary,
            "secondary_plausible_interpretations": context.secondary,
            "assessment_strength": context.strongest,
            "downgrade_reasons": context.downgrades,
        }
    )
    return section


@dataclass(frozen=True)
class _AssessmentContext:
    findings: list[dict[str, Any]]
    strongest: str
    strongest_findings: list[dict[str, Any]]
    claim_level: str
    primary: str
    secondary: list[str]
    ambiguities: list[str]
    alternatives: list[str]
    mixed: bool
    downgrades: list[str]


def _empty_assessment_section() -> dict[str, Any]:
    section = _section_with_entries(
        section_id="overall_assessment",
        title="Overall Assessment",
        entries=[],
        insufficiency_reason="The current case bundle does not yet support an overall assessment.",
    )
    section.update(
        {
            "primary_assessment": "insufficient_evidence",
            "secondary_plausible_interpretations": [],
            "assessment_strength": "insufficient_evidence",
            "downgrade_reasons": [],
        }
    )
    return section


def _assessment_context(
    findings: list[dict[str, Any]], case_bundle: dict[str, Any], comparative: dict[str, Any]
) -> _AssessmentContext:
    strongest = _strongest_label(findings)
    claim_level = _dominant_claim_level(findings)
    ambiguities, alternatives = _assessment_disclosures(findings)
    primary, secondary = derive_primary_assessment(
        findings,
        case_bundle=case_bundle,
        comparative_treatment=comparative,
        strongest_label=strongest,
        dominant_claim_level=claim_level,
    )
    downgrades = overall_downgrade_reasons(
        findings, case_bundle=case_bundle, comparative_treatment=comparative, strongest_label=strongest
    )
    return _AssessmentContext(
        findings,
        strongest,
        _findings_with_strength(findings, strongest),
        claim_level,
        primary,
        secondary,
        ambiguities,
        alternatives,
        has_mixed_evidence(findings),
        downgrades,
    )


def _strongest_label(findings: list[dict[str, Any]]) -> str:
    counts = Counter(str(_as_dict(item.get("evidence_strength")).get("label") or "insufficient_evidence") for item in findings)
    return next(
        (label for label in ("strong_indicator", "moderate_indicator", "weak_indicator") if counts.get(label, 0)),
        "insufficient_evidence",
    )


def _findings_with_strength(findings: list[dict[str, Any]], strength: str) -> list[dict[str, Any]]:
    return [item for item in findings if str(_as_dict(item.get("evidence_strength")).get("label") or "") == strength]


def _dominant_claim_level(findings: list[dict[str, Any]]) -> str:
    counts = Counter(guarded_statement_for_finding(item)[1] for item in findings)
    return next(
        (
            level
            for level in ("stronger_interpretation", "pattern_concern", "observed_fact", "insufficient_evidence")
            if counts.get(level, 0)
        ),
        "insufficient_evidence",
    )


def _assessment_disclosures(findings: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    ambiguities: list[str] = []
    alternatives: list[str] = []
    for finding in findings:
        _, _, _, finding_ambiguities, finding_alternatives = guarded_statement_for_finding(finding)
        _append_unique(alternatives, finding_alternatives)
        _append_unique(ambiguities, finding_ambiguities)
    return ambiguities, alternatives


def _append_unique(target: list[str], items: list[str]) -> None:
    for item in items:
        if item not in target:
            target.append(item)


def _assessment_entries(context: _AssessmentContext) -> list[dict[str, Any]]:
    entries = [_assessment_strength_entry(context)]
    if context.mixed:
        entries.append(_mixed_evidence_entry(context))
    if context.secondary:
        entries.append(_secondary_interpretations_entry(context))
    if context.alternatives:
        entries.append(_alternatives_entry(context))
    return entries


def _assessment_strength_entry(context: _AssessmentContext) -> dict[str, Any]:
    statement = _classification_statement(context)
    return {
        "entry_id": "overall:strength",
        "statement": statement,
        "claim_level": context.claim_level,
        "policy_reason": "The overall assessment stays within the strongest claim level defensible from the current finding set.",
        "ambiguity_disclosures": context.ambiguities,
        "alternative_explanations": context.alternatives,
        "supporting_finding_ids": _finding_ids(context.strongest_findings),
        "supporting_citation_ids": [],
        "supporting_uids": [],
    }


def _classification_statement(context: _AssessmentContext) -> str:
    if context.primary == "insufficient_evidence" and context.strongest == "weak_indicator":
        return _CLASSIFICATION_WEAK_PREFIX + _title(context.strongest).lower() + "."
    primary = _title(context.primary).lower()
    strongest = _title(context.strongest).lower()
    count = len(context.strongest_findings)
    return (
        f"The current record is best classified as {primary}, with the strongest findings reaching {strongest} "
        f"across {count} finding(s)."
    )


def _mixed_evidence_entry(context: _AssessmentContext) -> dict[str, Any]:
    return {
        "entry_id": "overall:mixed_evidence",
        "statement": _MIXED_EVIDENCE_STATEMENT,
        "claim_level": "pattern_concern",
        "policy_reason": _MIXED_EVIDENCE_POLICY,
        "ambiguity_disclosures": context.ambiguities[:3],
        "alternative_explanations": context.alternatives[:3],
        "supporting_finding_ids": _finding_ids(context.findings),
        "supporting_citation_ids": [],
        "supporting_uids": [],
    }


def _secondary_interpretations_entry(context: _AssessmentContext) -> dict[str, Any]:
    return {
        "entry_id": "overall:secondary_interpretations",
        "statement": "Secondary plausible interpretations remain in play: "
        + ", ".join(_title(item).lower() for item in context.secondary)
        + ".",
        "claim_level": "pattern_concern",
        "policy_reason": _SECONDARY_POLICY,
        "ambiguity_disclosures": [],
        "alternative_explanations": [],
        "supporting_finding_ids": _finding_ids(context.findings),
        "supporting_citation_ids": [],
        "supporting_uids": [],
    }


def _alternatives_entry(context: _AssessmentContext) -> dict[str, Any]:
    return {
        "entry_id": "overall:alternatives",
        "statement": "Alternative explanations remain relevant and should be considered alongside the current read.",
        "claim_level": "pattern_concern",
        "policy_reason": "BA17 requires contrary or neutral explanations to stay visible in the overall assessment.",
        "ambiguity_disclosures": [],
        "alternative_explanations": context.alternatives[:3],
        "supporting_finding_ids": _finding_ids(context.findings),
        "supporting_citation_ids": [],
        "supporting_uids": [],
    }


def _finding_ids(findings: list[dict[str, Any]]) -> list[str]:
    return [str(finding.get("finding_id") or "") for finding in findings[:3]]
