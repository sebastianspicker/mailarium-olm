"""Assessment-oriented helpers for investigation reports."""

from __future__ import annotations

from collections import Counter
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

    scopes = Counter(str(finding.get("finding_scope") or "") for finding in findings)
    direct_message_count = sum(1 for finding in findings if str(finding.get("finding_scope") or "") == "message_behavior")
    pattern_count = sum(
        1
        for finding in findings
        if str(finding.get("finding_scope") or "") in {"case_pattern", "communication_graph", "retaliation_analysis"}
    )
    strong_or_moderate_count = sum(
        1 for finding in findings if str(_as_dict(finding.get("evidence_strength")).get("label") or "") in NON_WEAK_STRENGTHS
    )
    has_pattern_support = pattern_count >= 1
    has_direct_behavior_support = direct_message_count >= 1
    all_supported_findings_are_weak = strongest_label == "weak_indicator"
    discrimination_supported = supports_discrimination_concern(
        findings=findings,
        case_bundle=case_bundle,
        comparative_treatment=comparative_treatment,
        strongest_label=strongest_label,
    )

    if all_supported_findings_are_weak:
        secondary_candidates: list[str] = []
        if scopes.get("retaliation_analysis", 0) > 0:
            secondary_candidates.append("retaliation_concern")
        if scopes.get("comparative_treatment", 0) > 0:
            secondary_candidates.append("unequal_treatment_concern")
        if direct_message_count >= 1:
            secondary_candidates.append("ordinary_workplace_conflict")
        secondary_candidates.append("poor_communication_or_process_noise")
        ordered_secondary = [
            candidate
            for candidate in ASSESSMENT_ORDER
            if candidate in secondary_candidates and candidate != "insufficient_evidence"
        ]
        return "insufficient_evidence", ordered_secondary[:2]

    candidates: list[str] = []
    if scopes.get("retaliation_analysis", 0) > 0:
        candidates.append("retaliation_concern")
    if discrimination_supported:
        candidates.append("discrimination_concern")
    if scopes.get("comparative_treatment", 0) > 0:
        candidates.append("unequal_treatment_concern")
    if strong_or_moderate_count >= 3 and has_direct_behavior_support and scopes.get("case_pattern", 0) > 0:
        candidates.append("mobbing_like_pattern_concern")
    if (
        has_direct_behavior_support
        or scopes.get("case_pattern", 0) > 0
        or scopes.get("communication_graph", 0) > 0
        or scopes.get("comparative_treatment", 0) > 0
    ):
        candidates.append("targeted_hostility_concern")
    if dominant_claim_level == "observed_fact" and has_direct_behavior_support and not has_pattern_support:
        candidates.append("ordinary_workplace_conflict")
    if (
        not has_pattern_support
        and not has_direct_behavior_support
        and scopes.get("comparative_treatment", 0) == 0
        and strongest_label in NON_WEAK_STRENGTHS
    ):
        candidates.append("poor_communication_or_process_noise")
    if not candidates:
        candidates.append("insufficient_evidence")

    ordered = [candidate for candidate in ASSESSMENT_ORDER if candidate in candidates]
    primary = ordered[0] if ordered else "insufficient_evidence"
    secondary = [candidate for candidate in ordered[1:] if candidate != primary][:2]
    return primary, secondary


def has_mixed_evidence(findings: list[dict[str, Any]]) -> bool:
    """Return true when the record has meaningful support alongside material contrary indicators."""
    if not findings:
        return False
    has_non_weak_support = any(
        str(_as_dict(finding.get("evidence_strength")).get("label") or "") in NON_WEAK_STRENGTHS for finding in findings
    )
    if not has_non_weak_support:
        return False
    alternative_count = sum(
        1
        for finding in findings
        if _as_list(finding.get("alternative_explanations")) or _as_list(finding.get("counter_indicators"))
    )
    low_confidence = any(
        str(_as_dict(_as_dict(finding.get("confidence_split")).get("interpretation_confidence")).get("label") or "") == "low"
        for finding in findings
    )
    quote_ambiguity = any(
        bool(_as_dict(finding.get("quote_ambiguity")).get("downgraded_due_to_quote_ambiguity")) for finding in findings
    )
    weak_support_present = any(
        str(_as_dict(finding.get("evidence_strength")).get("label") or "") == "weak_indicator" for finding in findings
    )
    return alternative_count >= 2 or (alternative_count >= 1 and (low_confidence or quote_ambiguity or weak_support_present))


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
    reasons: list[str] = []
    if strongest_label == "weak_indicator":
        reasons.append("The strongest supported findings remain in the weak-indicator range.")
    if any(
        str(_as_dict(_as_dict(finding.get("confidence_split")).get("interpretation_confidence")).get("label") or "") == "low"
        for finding in findings
    ):
        reasons.append("At least one relevant finding has low interpretation confidence.")
    if any(bool(_as_dict(finding.get("quote_ambiguity")).get("downgraded_due_to_quote_ambiguity")) for finding in findings):
        reasons.append("Quoted-speaker ambiguity downgrades part of the current record.")
    if any(str(_as_dict(finding.get("evidence_strength")).get("label") or "") == "insufficient_evidence" for finding in findings):
        reasons.append("Some findings remain too weak for stronger interpretation.")
    if has_mixed_evidence(findings):
        reasons.append("The current record contains mixed evidence and material alternative explanations.")
    scope = _as_dict(case_bundle.get("scope"))
    allegation_focus = {str(item) for item in _as_list(scope.get("allegation_focus")) if item}
    if "discrimination" in allegation_focus and not supports_discrimination_concern(
        findings=findings,
        case_bundle=case_bundle,
        comparative_treatment=comparative_treatment,
        strongest_label=strongest_label,
    ):
        reasons.append(
            "Discrimination concern remains gated because the current record lacks explicit discriminatory content, "
            "high-quality comparator asymmetry, or structured protected-context support."
        )
    return reasons


def overall_assessment_section(
    findings: list[dict[str, Any]],
    *,
    case_bundle: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    """Return the overall-assessment section."""
    if not findings:
        section = _section_with_entries(
            section_id="overall_assessment",
            title="Overall Assessment",
            entries=[],
            insufficiency_reason="The current case bundle does not yet support an overall assessment.",
        )
        section["primary_assessment"] = "insufficient_evidence"
        section["secondary_plausible_interpretations"] = []
        section["assessment_strength"] = "insufficient_evidence"
        section["downgrade_reasons"] = []
        return section
    strength_counts = Counter(
        str(_as_dict(finding.get("evidence_strength")).get("label") or "insufficient_evidence") for finding in findings
    )
    strongest = next(
        (label for label in ("strong_indicator", "moderate_indicator", "weak_indicator") if strength_counts.get(label, 0) > 0),
        "insufficient_evidence",
    )
    strongest_findings = [
        finding for finding in findings if str(_as_dict(finding.get("evidence_strength")).get("label") or "") == strongest
    ]
    claim_levels = Counter(guarded_statement_for_finding(finding)[1] for finding in findings)
    dominant_claim_level = next(
        (
            level
            for level in ("stronger_interpretation", "pattern_concern", "observed_fact", "insufficient_evidence")
            if claim_levels.get(level, 0) > 0
        ),
        "insufficient_evidence",
    )
    alternative_explanations: list[str] = []
    ambiguity_disclosures: list[str] = []
    for finding in findings:
        _, _, _, finding_ambiguity, finding_alternatives = guarded_statement_for_finding(finding)
        for item in finding_alternatives:
            if item not in alternative_explanations:
                alternative_explanations.append(item)
        for item in finding_ambiguity:
            if item not in ambiguity_disclosures:
                ambiguity_disclosures.append(item)
    primary_assessment, secondary_interpretations = derive_primary_assessment(
        findings,
        case_bundle=case_bundle,
        comparative_treatment=comparative_treatment,
        strongest_label=strongest,
        dominant_claim_level=dominant_claim_level,
    )
    downgrade_reasons = overall_downgrade_reasons(
        findings,
        case_bundle=case_bundle,
        comparative_treatment=comparative_treatment,
        strongest_label=strongest,
    )
    mixed_evidence = has_mixed_evidence(findings)
    classification_statement = (
        f"The current record is best classified as {_title(primary_assessment).lower()}, "
        f"with the strongest findings reaching {_title(strongest).lower()} across {len(strongest_findings)} finding(s)."
    )
    if primary_assessment == "insufficient_evidence" and strongest == "weak_indicator":
        classification_statement = (
            "The current record remains best classified as insufficient evidence because the supported findings "
            f"do not rise above {_title(strongest).lower()}."
        )
    entries = [
        {
            "entry_id": "overall:strength",
            "statement": classification_statement,
            "claim_level": dominant_claim_level,
            "policy_reason": (
                "The overall assessment stays within the strongest claim level defensible from the current finding set."
            ),
            "ambiguity_disclosures": ambiguity_disclosures,
            "alternative_explanations": alternative_explanations,
            "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in strongest_findings[:3]],
            "supporting_citation_ids": [],
            "supporting_uids": [],
        }
    ]
    if mixed_evidence:
        entries.append(
            {
                "entry_id": "overall:mixed_evidence",
                "statement": (
                    "The record remains mixed: some supported indicators point toward a problematic pattern, "
                    "but material counterarguments and alternative explanations remain live."
                ),
                "claim_level": "pattern_concern",
                "policy_reason": (
                    "The overall assessment must surface mixed-evidence conditions when support and counterweight both matter."
                ),
                "ambiguity_disclosures": ambiguity_disclosures[:3],
                "alternative_explanations": alternative_explanations[:3],
                "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in findings[:3]],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    if secondary_interpretations:
        entries.append(
            {
                "entry_id": "overall:secondary_interpretations",
                "statement": (
                    "Secondary plausible interpretations remain in play: "
                    + ", ".join(_title(item).lower() for item in secondary_interpretations)
                    + "."
                ),
                "claim_level": "pattern_concern",
                "policy_reason": (
                    "Multiple bounded review categories remain plausible, so the renderer keeps alternative readings visible."
                ),
                "ambiguity_disclosures": [],
                "alternative_explanations": [],
                "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in findings[:3]],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    if alternative_explanations:
        entries.append(
            {
                "entry_id": "overall:alternatives",
                "statement": "Alternative explanations remain relevant and should be considered alongside the current read.",
                "claim_level": "pattern_concern",
                "policy_reason": "BA17 requires contrary or neutral explanations to stay visible in the overall assessment.",
                "ambiguity_disclosures": [],
                "alternative_explanations": alternative_explanations[:3],
                "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in findings[:3]],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    section = _section_with_entries(
        section_id="overall_assessment",
        title="Overall Assessment",
        entries=entries,
        insufficiency_reason="The current case bundle does not yet support an overall assessment.",
    )
    section["primary_assessment"] = primary_assessment
    section["secondary_plausible_interpretations"] = secondary_interpretations
    section["assessment_strength"] = strongest
    section["downgrade_reasons"] = downgrade_reasons
    return section
