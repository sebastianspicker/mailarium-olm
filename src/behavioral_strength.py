"""Rule-backed strength scoring for behavioural-analysis findings."""
# pylint: disable=too-many-locals

from __future__ import annotations

from collections import Counter
from typing import Any

from src._utils import as_dict, as_list

BEHAVIORAL_STRENGTH_VERSION = "1"


def _label_from_score(score: int) -> str:
    """Map a bounded integer score to the BA13 strength label set."""
    if score >= 5:
        return "strong_indicator"
    if score >= 3:
        return "moderate_indicator"
    if score >= 1:
        return "weak_indicator"
    return "insufficient_evidence"


def _confidence_label(score: int) -> str:
    """Map a bounded integer score to a compact confidence label."""
    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _generated_alternatives(finding: dict[str, Any], supporting: list[dict[str, Any]]) -> list[str]:
    """Return conservative alternative explanations for one finding."""
    finding_scope = str(finding.get("finding_scope") or "")
    alternatives: list[str] = []
    text_origins = {str((as_dict(citation.get("text_attribution"))).get("text_origin") or "") for citation in supporting}
    if finding_scope == "communication_graph":
        alternatives.append("Recipient visibility patterns may reflect operational routing or process stage differences.")
    if finding_scope == "comparative_treatment":
        alternatives.append("The comparator may not be sufficiently similar in role, context, or process stage.")
    if finding_scope == "retaliation_analysis":
        alternatives.append("Before/after changes may reflect independent operational developments rather than retaliation.")
    if finding_scope in {"case_pattern", "directional_summary"}:
        alternatives.append("The pattern may reflect repeated process friction rather than targeted hostility.")
    if "metadata" in text_origins and "authored" not in text_origins and "quoted" not in text_origins:
        alternatives.append("The current support relies on message metadata more than direct authored text.")
    quote_ambiguity = as_dict(finding.get("quote_ambiguity"))
    if bool(quote_ambiguity.get("downgraded_due_to_quote_ambiguity")):
        alternatives.append("Quoted content may belong to a different speaker than the current inference suggests.")
    return list(dict.fromkeys(alternatives))


def _score_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Return BA13 strength scoring for one finding."""
    supporting = [citation for citation in as_list(finding.get("supporting_evidence")) if isinstance(citation, dict)]
    contradictory = [citation for citation in as_list(finding.get("contradictory_evidence")) if isinstance(citation, dict)]
    counter_indicators = [str(item) for item in as_list(finding.get("counter_indicators")) if str(item).strip()]
    quote_ambiguity = as_dict(finding.get("quote_ambiguity"))

    evidence_score, reasons = _evidence_score(supporting, contradictory, counter_indicators, quote_ambiguity)

    evidence_strength = _label_from_score(evidence_score)

    interpretation_score = evidence_score
    finding_scope = str(finding.get("finding_scope") or "")
    if finding_scope in {"communication_graph", "comparative_treatment", "retaliation_analysis", "directional_summary"}:
        interpretation_score -= 1
        reasons.append("This finding requires inferential interpretation beyond direct wording.")
    if finding_scope == "case_pattern":
        interpretation_score -= 1
        reasons.append("Pattern aggregation is more interpretive than a single-message finding.")
    if not supporting:
        interpretation_score -= 1
    interpretation_score = max(0, interpretation_score)

    return {
        "evidence_strength": {
            "label": evidence_strength,
            "score": evidence_score,
            "rationale": reasons,
        },
        "confidence_split": {
            "evidence_confidence": {
                "label": _confidence_label(evidence_score),
                "score": evidence_score,
            },
            "interpretation_confidence": {
                "label": _confidence_label(interpretation_score),
                "score": interpretation_score,
            },
        },
        "alternative_explanations": _generated_alternatives(finding, supporting),
    }


def _evidence_score(
    supporting: list[dict[str, Any]],
    contradictory: list[dict[str, Any]],
    counter_indicators: list[str],
    quote_ambiguity: dict[str, Any],
) -> tuple[int, list[str]]:
    score, reasons = _support_score(supporting)
    deductions = (
        (bool(contradictory), "Contradictory evidence is present."),
        (len(counter_indicators) >= 2, "Multiple counter-indicators weaken the current evidence read."),
        (
            bool(quote_ambiguity.get("downgraded_due_to_quote_ambiguity")),
            "Quoted-speaker ambiguity reduces evidentiary strength.",
        ),
    )
    for applies, reason in deductions:
        if applies:
            score -= 1
            reasons.append(reason)
    return score, reasons


def _support_score(supporting: list[dict[str, Any]]) -> tuple[int, list[str]]:
    handles = _support_handles(supporting)
    message_ids = _support_message_ids(supporting)
    statuses = _support_statuses(supporting)
    checks = _presence_checks(supporting, handles, message_ids) + _attribution_checks(statuses)
    score = sum(delta for applies, delta, _reason in checks if applies)
    reasons = [reason for applies, _delta, reason in checks if applies]
    return score, reasons


def _support_handles(supporting: list[dict[str, Any]]) -> set[str]:
    return {
        str(as_dict(item.get("provenance")).get("evidence_handle") or "")
        for item in supporting
        if str(as_dict(item.get("provenance")).get("evidence_handle") or "")
    }


def _support_message_ids(supporting: list[dict[str, Any]]) -> set[str]:
    return {str(item.get("message_or_document_id") or "") for item in supporting if item.get("message_or_document_id")}


def _support_statuses(supporting: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(as_dict(item.get("text_attribution")).get("authored_quoted_inferred_status") or "") for item in supporting)


def _presence_checks(
    supporting: list[dict[str, Any]], handles: set[str], message_ids: set[str]
) -> tuple[tuple[bool, int, str], ...]:
    return (
        (bool(supporting), 1, "At least one supporting citation is present."),
        (len(supporting) >= 2, 1, "Multiple supporting citations are present."),
        (len(handles) >= 2 or len(message_ids) >= 2, 1, "Support spans more than one evidence handle or message/document."),
    )


def _attribution_checks(statuses: Counter[str]) -> tuple[tuple[bool, int, str], ...]:
    return (
        (statuses.get("authored", 0) >= 1, 1, "Direct authored-text support is present."),
        (statuses.get("quoted", 0) >= 1, 1, "Quoted support is present with non-inferred ownership."),
        (
            statuses.get("metadata", 0) >= 1 and statuses.get("authored", 0) == 0 and statuses.get("quoted", 0) == 0,
            -1,
            "Support is metadata-heavy without direct authored or quoted text.",
        ),
    )


def apply_behavioral_strength(
    finding_evidence_index: dict[str, Any],
    evidence_table: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Apply BA13 strength scoring to the BA12 finding and table outputs."""
    findings = [finding for finding in as_list(finding_evidence_index.get("findings")) if isinstance(finding, dict)]
    enriched_findings, assessment_by_id = _assess_findings(findings)
    enriched_rows = _assess_table_rows(evidence_table, assessment_by_id)
    strength_counts = Counter(str(as_dict(item.get("evidence_strength")).get("label") or "") for item in enriched_findings)
    evidence_confidence_counts = Counter(
        str(as_dict(as_dict(item.get("confidence_split")).get("evidence_confidence")).get("label") or "")
        for item in enriched_findings
    )
    interpretation_confidence_counts = Counter(
        str(as_dict(as_dict(item.get("confidence_split")).get("interpretation_confidence")).get("label") or "")
        for item in enriched_findings
    )

    rubric = {
        "version": BEHAVIORAL_STRENGTH_VERSION,
        "labels": ["strong_indicator", "moderate_indicator", "weak_indicator", "insufficient_evidence"],
        "rule_summary": [
            "Multiple independent supporting citations increase evidence strength.",
            "Direct authored or canonical quoted text increases evidence strength.",
            (
                "Metadata-only support, quote ambiguity, contradictory evidence, "
                "and multiple counter-indicators reduce evidence strength."
            ),
            (
                "Interpretation confidence is reduced for pattern, graph, comparator, "
                "and retaliation-level findings because they require more inference."
            ),
        ],
    }

    return (
        {
            **finding_evidence_index,
            "version": BEHAVIORAL_STRENGTH_VERSION,
            "findings": enriched_findings,
            "summary": {
                "finding_scope_counts": dict(
                    sorted(Counter(str(finding.get("finding_scope") or "") for finding in enriched_findings).items())
                ),
                "evidence_strength_counts": dict(sorted(strength_counts.items())),
                "evidence_confidence_counts": dict(sorted(evidence_confidence_counts.items())),
                "interpretation_confidence_counts": dict(sorted(interpretation_confidence_counts.items())),
            },
        },
        {
            **evidence_table,
            "version": BEHAVIORAL_STRENGTH_VERSION,
            "rows": enriched_rows,
        },
        rubric,
    )


def _assess_findings(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    enriched: list[dict[str, Any]] = []
    assessments: dict[str, dict[str, Any]] = {}
    for finding in findings:
        assessment = _score_finding(finding)
        enriched.append({**finding, **assessment})
        assessments[str(finding.get("finding_id") or "")] = assessment
    return enriched, assessments


def _assess_table_rows(evidence_table: dict[str, Any], assessments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [_assess_table_row(row, assessments) for row in as_list(evidence_table.get("rows")) if isinstance(row, dict)]


def _assess_table_row(row: dict[str, Any], assessments: dict[str, dict[str, Any]]) -> dict[str, Any]:
    assessment = assessments.get(str(row.get("finding_id") or ""), {})
    strength = as_dict(assessment.get("evidence_strength"))
    confidence = as_dict(assessment.get("confidence_split"))
    return {
        **row,
        "evidence_strength": str(strength.get("label") or ""),
        "evidence_confidence": str(as_dict(confidence.get("evidence_confidence")).get("label") or ""),
        "interpretation_confidence": str(as_dict(confidence.get("interpretation_confidence")).get("label") or ""),
    }
