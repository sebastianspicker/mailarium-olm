"""Guarded wording policy for workplace-conflict behavioural-analysis output."""

from __future__ import annotations

from typing import Any

BEHAVIORAL_INTERPRETATION_POLICY_VERSION = "1"

_DIRECT_FINDING_SCOPES = {"message_behavior", "quoted_message_behavior"}
_INTERPRETIVE_FINDING_SCOPES = {
    "case_pattern",
    "comparative_treatment",
    "communication_graph",
    "directional_summary",
    "retaliation_analysis",
}
_CONCERN_CEILING_SCOPES = {"comparative_treatment", "communication_graph", "retaliation_analysis"}
_CONCERN_CEILING_LABEL_TERMS = ("discrimin", "retaliat", "mobb", "hostile environment")


def _as_dict(value: Any) -> dict[str, Any]:
    """Return one dict or an empty dict."""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Return one list or an empty list."""
    return value if isinstance(value, list) else []


def _title(label: str) -> str:
    """Return a compact human-readable label."""
    return str(label or "").replace("_", " ").capitalize()


def _direct_text_support(finding: dict[str, Any]) -> bool:
    """Return whether the finding has direct authored or canonical quoted support."""
    for citation in _as_list(finding.get("supporting_evidence")):
        if not isinstance(citation, dict):
            continue
        attribution = _as_dict(citation.get("text_attribution"))
        status = str(attribution.get("authored_quoted_inferred_status") or "")
        if status in {"authored", "quoted"}:
            return True
    return False


def _requires_concern_ceiling(finding: dict[str, Any]) -> bool:
    """Return whether the finding must remain capped at concern wording."""
    finding_scope = str(finding.get("finding_scope") or "")
    if finding_scope in _CONCERN_CEILING_SCOPES:
        return True
    label = str(finding.get("finding_label") or "").lower()
    return any(term in label for term in _CONCERN_CEILING_LABEL_TERMS)


def _ambiguity_disclosures(finding: dict[str, Any]) -> list[str]:
    """Return compact ambiguity and uncertainty disclosures for one finding."""
    disclosures: list[str] = []
    quote_ambiguity = _as_dict(finding.get("quote_ambiguity"))
    if bool(quote_ambiguity.get("downgraded_due_to_quote_ambiguity")):
        disclosures.append("Quoted-speaker ownership remains ambiguous in the cited material.")
    confidence_split = _as_dict(finding.get("confidence_split"))
    interpretation_confidence = _as_dict(confidence_split.get("interpretation_confidence"))
    if str(interpretation_confidence.get("label") or "") == "low":
        disclosures.append("Interpretation confidence remains low for this finding.")
    evidence_strength = _as_dict(finding.get("evidence_strength"))
    if str(evidence_strength.get("label") or "") == "weak_indicator":
        disclosures.append("The available support is limited and should be read cautiously.")
    return disclosures


def classify_claim_level(finding: dict[str, Any]) -> tuple[str, str]:
    """Return the BA17 claim level and a short policy reason for one finding."""
    finding_scope = str(finding.get("finding_scope") or "")
    evidence_strength = str(_as_dict(finding.get("evidence_strength")).get("label") or "insufficient_evidence")
    interpretation_confidence = str(
        _as_dict(_as_dict(finding.get("confidence_split")).get("interpretation_confidence")).get("label") or "low"
    )
    quote_ambiguity = bool(_as_dict(finding.get("quote_ambiguity")).get("downgraded_due_to_quote_ambiguity"))
    direct_text_support = _direct_text_support(finding)
    support_count = len([item for item in _as_list(finding.get("supporting_evidence")) if isinstance(item, dict)])

    if evidence_strength == "insufficient_evidence" or support_count == 0:
        return (
            "insufficient_evidence",
            "The current record does not contain enough direct support for a reliable interpretation.",
        )

    if finding_scope in _DIRECT_FINDING_SCOPES and direct_text_support and not quote_ambiguity:
        if evidence_strength in {"strong_indicator", "moderate_indicator"}:
            return (
                "observed_fact",
                "The cited material supports a direct observation about wording or behaviour in the message itself.",
            )
        return (
            "pattern_concern",
            "The message contains some direct support, but not enough for a firmer factual characterization.",
        )

    if finding_scope in _INTERPRETIVE_FINDING_SCOPES:
        if _requires_concern_ceiling(finding):
            return (
                "pattern_concern",
                "This high-stakes interpretive finding must remain at concern wording rather than stronger attribution.",
            )
        if evidence_strength == "strong_indicator" and interpretation_confidence in {"high", "medium"}:
            return (
                "stronger_interpretation",
                "The finding aggregates multiple signals, but it remains an interpretation rather than a legal conclusion.",
            )
        return (
            "pattern_concern",
            "The available record raises a concern pattern, but alternative explanations remain viable.",
        )

    if evidence_strength in {"strong_indicator", "moderate_indicator"} and interpretation_confidence in {"high", "medium"}:
        return (
            "observed_fact",
            "The current support allows a bounded factual summary without extending to motive or legality.",
        )

    return (
        "pattern_concern",
        "The available support is suggestive but remains too limited for a stronger interpretation.",
    )


def guarded_statement_for_finding(finding: dict[str, Any]) -> tuple[str, str, str, list[str], list[str]]:
    """Return a guarded BA17 statement bundle for one finding."""
    label = _title(str(finding.get("finding_label") or "finding")).lower()
    claim_level, policy_reason = classify_claim_level(finding)
    alternatives = [str(item) for item in _as_list(finding.get("alternative_explanations")) if str(item).strip()]
    ambiguity_disclosures = _ambiguity_disclosures(finding)

    if claim_level == "observed_fact":
        statement = f"The cited material directly supports {label} as an observed communication feature in the available record."
    elif claim_level == "stronger_interpretation":
        statement = (
            f"Taken together, the available evidence may indicate {label} as a broader case-level pattern. "
            "This does not establish motive or a legal conclusion on its own."
        )
    elif claim_level == "pattern_concern":
        statement = (
            f"The available material raises a concern pattern consistent with {label}, "
            "but alternative explanations remain viable."
        )
    else:
        statement = f"The current material is insufficient to support a reliable interpretation of {label}."

    return statement, claim_level, policy_reason, ambiguity_disclosures, alternatives


def cautious_rewrite_for_weakness(*, weakness_category: str, subject: str) -> str:
    """Return a conservative rewrite that lowers overstatement for one weakness type."""
    normalized_subject = _title(subject).lower() if subject else "the current point"
    rewrites = {
        "chronology_problem": (
            f"On the current record, {normalized_subject} remains chronology-sensitive and should stay provisional "
            "until the missing sequence is documented."
        ),
        "overstated_comparison": (
            f"{normalized_subject.capitalize()} may justify further comparator review, but role similarity and policy context "
            "remain too incomplete for a stronger unequal-treatment formulation."
        ),
        "alternative_explanation": (
            f"{normalized_subject.capitalize()} can currently be read in more than one way, so the safer formulation is that "
            "the record raises a concern pattern rather than proving a one-sided explanation."
        ),
        "missing_documentation": (
            f"{normalized_subject.capitalize()} should be framed as incomplete until "
            "the underlying documentary support is obtained."
        ),
        "factual_leap": (
            f"The current record supports a bounded concern about {normalized_subject}, "
            "not a firmer factual or motive attribution."
        ),
        "unsupported_motive_claim": (
            f"Any reference to {normalized_subject} should stay at concern wording and should not be framed as a motive finding."
        ),
        "weak_legal_evidence_linkage": (
            f"{normalized_subject.capitalize()} may remain legally relevant for review, but "
            "the evidence linkage is still too thin "
            "for a stronger legal-facing formulation."
        ),
        "internal_inconsistency": (
            f"{normalized_subject.capitalize()} should be presented as contested or incomplete "
            "until the internal inconsistencies are resolved."
        ),
        "ordinary_management_explanation": (
            f"The safer formulation is that {normalized_subject} may reflect ordinary "
            "management or process explanations on the current record."
        ),
    }
    return rewrites.get(
        weakness_category,
        f"The current record supports only a cautious, provisional formulation of {normalized_subject}.",
    )


def interpretation_policy_payload() -> dict[str, Any]:
    """Return the stable BA17 wording-policy contract."""
    return {
        "version": BEHAVIORAL_INTERPRETATION_POLICY_VERSION,
        "refuse_to_overclaim": True,
        "claim_levels": [
            "observed_fact",
            "pattern_concern",
            "stronger_interpretation",
            "insufficient_evidence",
        ],
        "rule_summary": [
            "Direct authored or canonically attributed quoted text may support observed-fact statements.",
            (
                "Pattern, graph, comparator, and retaliation findings must use concern "
                "or interpretation wording rather than motive claims."
            ),
            "Unsupported motive claims and legal conclusions are prohibited unless separately established outside this report.",
            "Alternative explanations and ambiguity disclosures must be surfaced when they materially weaken the current read.",
            (
                "Retaliation, comparator, graph, discrimination-style, and mobbing-style findings stay at concern "
                "wording in this layer."
            ),
            (
                "Employer-side skeptical review must lower overstatement through "
                "explicit cautious rewrites rather than warnings alone."
            ),
        ],
        "prohibited_claims": [
            "unsupported motive attribution",
            "unsupported legal conclusion",
            "unsupported protected-category inference",
            "psychiatric labeling of actors",
            "unsupported character judgment",
            "invented coordination claim",
            "certainty beyond the cited record",
        ],
        "refusal_rules": [
            "Do not claim legal liability or legal standard satisfaction from this layer alone.",
            "Do not assert motive from hostility, exclusion, chronology, or comparator asymmetry alone.",
            (
                "Do not infer protected-category basis unless explicit record support or structured protected-context "
                "support is present."
            ),
            "Do not use psychiatric, diagnosis-style, or character-judgment labels for actors.",
        ],
    }
