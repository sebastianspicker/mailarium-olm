"""Rule-backed strength scoring for behavioural-analysis findings."""

from __future__ import annotations

from collections import Counter
from typing import Any

BEHAVIORAL_STRENGTH_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    """Return one dict or an empty dict."""
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    """Return one list or an empty list."""
    return value if isinstance(value, list) else []


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
    text_origins = {str((_as_dict(citation.get("text_attribution"))).get("text_origin") or "") for citation in supporting}
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
    quote_ambiguity = _as_dict(finding.get("quote_ambiguity"))
    if bool(quote_ambiguity.get("downgraded_due_to_quote_ambiguity")):
        alternatives.append("Quoted content may belong to a different speaker than the current inference suggests.")
    return list(dict.fromkeys(alternatives))


def _score_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Return BA13 strength scoring for one finding."""
    supporting = [citation for citation in _as_list(finding.get("supporting_evidence")) if isinstance(citation, dict)]
    contradictory = [citation for citation in _as_list(finding.get("contradictory_evidence")) if isinstance(citation, dict)]
    counter_indicators = [str(item) for item in _as_list(finding.get("counter_indicators")) if str(item).strip()]
    quote_ambiguity = _as_dict(finding.get("quote_ambiguity"))

    reasons: list[str] = []
    evidence_score = 0

    if supporting:
        evidence_score += 1
        reasons.append("At least one supporting citation is present.")
    if len(supporting) >= 2:
        evidence_score += 1
        reasons.append("Multiple supporting citations are present.")

    evidence_handles = {
        str((_as_dict(citation.get("provenance"))).get("evidence_handle") or "")
        for citation in supporting
        if str((_as_dict(citation.get("provenance"))).get("evidence_handle") or "")
    }
    message_ids = {
        str(citation.get("message_or_document_id") or "")
        for citation in supporting
        if citation.get("message_or_document_id")
    }
    text_statuses = Counter(
        str((_as_dict(citation.get("text_attribution"))).get("authored_quoted_inferred_status") or "")
        for citation in supporting
    )

    if len(evidence_handles) >= 2 or len(message_ids) >= 2:
        evidence_score += 1
        reasons.append("Support spans more than one evidence handle or message/document.")
    if text_statuses.get("authored", 0) >= 1:
        evidence_score += 1
        reasons.append("Direct authored-text support is present.")
    if text_statuses.get("quoted", 0) >= 1:
        evidence_score += 1
        reasons.append("Quoted support is present with non-inferred ownership.")
    if text_statuses.get("metadata", 0) >= 1 and text_statuses.get("authored", 0) == 0 and text_statuses.get("quoted", 0) == 0:
        evidence_score -= 1
        reasons.append("Support is metadata-heavy without direct authored or quoted text.")

    if contradictory:
        evidence_score -= 1
        reasons.append("Contradictory evidence is present.")
    if len(counter_indicators) >= 2:
        evidence_score -= 1
        reasons.append("Multiple counter-indicators weaken the current evidence read.")
    if bool(quote_ambiguity.get("downgraded_due_to_quote_ambiguity")):
        evidence_score -= 1
        reasons.append("Quoted-speaker ambiguity reduces evidentiary strength.")

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


def apply_behavioral_strength(
    finding_evidence_index: dict[str, Any],
    evidence_table: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Apply BA13 strength scoring to the BA12 finding and table outputs."""
    findings = [finding for finding in _as_list(finding_evidence_index.get("findings")) if isinstance(finding, dict)]
    enriched_findings: list[dict[str, Any]] = []
    strength_counts: Counter[str] = Counter()
    evidence_confidence_counts: Counter[str] = Counter()
    interpretation_confidence_counts: Counter[str] = Counter()
    assessment_by_id: dict[str, dict[str, Any]] = {}

    for finding in findings:
        assessment = _score_finding(finding)
        enriched = {**finding, **assessment}
        enriched_findings.append(enriched)
        finding_id = str(finding.get("finding_id") or "")
        assessment_by_id[finding_id] = assessment
        strength_counts[str(assessment["evidence_strength"]["label"])] += 1
        evidence_confidence_counts[str(assessment["confidence_split"]["evidence_confidence"]["label"])] += 1
        interpretation_confidence_counts[str(assessment["confidence_split"]["interpretation_confidence"]["label"])] += 1

    rows = [row for row in _as_list(evidence_table.get("rows")) if isinstance(row, dict)]
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        finding_id = str(row.get("finding_id") or "")
        assessment = assessment_by_id.get(finding_id, {})
        evidence_strength = _as_dict(assessment.get("evidence_strength"))
        confidence_split = _as_dict(assessment.get("confidence_split"))
        enriched_rows.append(
            {
                **row,
                "evidence_strength": str(evidence_strength.get("label") or ""),
                "evidence_confidence": str(_as_dict(confidence_split.get("evidence_confidence")).get("label") or ""),
                "interpretation_confidence": str(
                    _as_dict(confidence_split.get("interpretation_confidence")).get("label") or ""
                ),
            }
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
