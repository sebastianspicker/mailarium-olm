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
    alternatives = [
        str(item)
        for item in _as_list(finding.get("alternative_explanations"))
        if str(item).strip()
    ]
    ambiguity_disclosures = _ambiguity_disclosures(finding)

    if claim_level == "observed_fact":
        statement = (
            f"The cited material directly supports {label} as an observed communication feature in the available record."
        )
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


def interpretation_policy_payload() -> dict[str, Any]:
    """Return the stable BA17 wording-policy contract."""
    return {
        "version": BEHAVIORAL_INTERPRETATION_POLICY_VERSION,
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
        ],
        "prohibited_claims": [
            "unsupported motive attribution",
            "unsupported legal conclusion",
            "invented coordination claim",
            "certainty beyond the cited record",
        ],
    }
