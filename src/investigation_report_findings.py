"""Finding- and triage-oriented helpers for investigation reports."""

from __future__ import annotations

from typing import Any

from .behavioral_interpretation_policy import classify_claim_level, guarded_statement_for_finding
from .investigation_report_sections import _as_dict, _as_list, _title


def strength_rank(label: str) -> int:
    """Rank evidence-strength labels for stable ordering."""
    return {
        "strong_indicator": 4,
        "moderate_indicator": 3,
        "weak_indicator": 2,
        "insufficient_evidence": 1,
    }.get(str(label or ""), 0)


def supporting_citation_ids(finding: dict[str, Any], *, max_items: int = 2) -> list[str]:
    """Return a stable short list of supporting citation ids."""
    citation_ids: list[str] = []
    for citation in _as_list(finding.get("supporting_evidence")):
        if not isinstance(citation, dict):
            continue
        citation_id = str(citation.get("citation_id") or "")
        if citation_id:
            citation_ids.append(citation_id)
        if len(citation_ids) >= max_items:
            break
    return citation_ids


def supporting_uids(finding: dict[str, Any], *, max_items: int = 3) -> list[str]:
    """Return a stable short list of supporting message/document ids."""
    uids: list[str] = []
    for citation in _as_list(finding.get("supporting_evidence")):
        if not isinstance(citation, dict):
            continue
        uid = str(citation.get("message_or_document_id") or "")
        if uid and uid not in uids:
            uids.append(uid)
        if len(uids) >= max_items:
            break
    return uids


def finding_entries(findings: list[dict[str, Any]], *, max_items: int = 3) -> list[dict[str, Any]]:
    """Return guarded finding entries for report sections."""
    ordered = sorted(
        findings,
        key=lambda finding: (
            -strength_rank(str(_as_dict(finding.get("evidence_strength")).get("label") or "")),
            str(finding.get("finding_id") or ""),
        ),
    )
    entries: list[dict[str, Any]] = []
    for index, finding in enumerate(ordered[:max_items], start=1):
        statement, claim_level, policy_reason, ambiguity_disclosures, alternatives = guarded_statement_for_finding(finding)
        entries.append(
            {
                "entry_id": f"{finding.get('finding_id') or 'finding'}:entry:{index}",
                "statement": statement,
                "claim_level": claim_level,
                "policy_reason": policy_reason,
                "ambiguity_disclosures": ambiguity_disclosures,
                "alternative_explanations": alternatives,
                "supporting_finding_ids": [str(finding.get("finding_id") or "")],
                "supporting_citation_ids": supporting_citation_ids(finding),
                "supporting_uids": supporting_uids(finding),
            }
        )
    return entries


def factual_summary_entry(
    *,
    candidates: list[dict[str, Any]],
    timeline: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return one neutral factual summary entry for the executive section."""
    date_range = _as_dict(timeline.get("date_range"))
    first_date = str(date_range.get("first") or "unknown")
    last_date = str(date_range.get("last") or "unknown")
    message_count = len([candidate for candidate in candidates if isinstance(candidate, dict)])
    finding_count = len(findings)
    return {
        "entry_id": "executive:factual_summary",
        "statement": (
            f"The current case bundle contains {message_count} analyzed message(s) and {finding_count} finding(s) "
            f"spanning {first_date} to {last_date}."
        ),
        "claim_level": "observed_fact",
        "policy_reason": "This entry is a neutral factual summary of the analyzed record rather than an interpretation.",
        "ambiguity_disclosures": [],
        "alternative_explanations": [],
        "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in findings[:3]],
        "supporting_citation_ids": [],
        "supporting_uids": [
            str(uid)
            for uid in [
                timeline.get("first_uid"),
                timeline.get("key_transition_uid"),
                timeline.get("last_uid"),
            ]
            if uid
        ],
    }


def report_highlights(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Return strongest-indicator and counterargument highlight blocks."""
    ordered_findings = sorted(
        findings,
        key=lambda finding: (
            -strength_rank(str(_as_dict(finding.get("evidence_strength")).get("label") or "")),
            str(finding.get("finding_id") or ""),
        ),
    )
    strongest_indicator_entries: list[dict[str, Any]] = []
    strongest_counterarguments: list[dict[str, Any]] = []
    seen_counterarguments: set[str] = set()

    for finding in ordered_findings[:3]:
        statement, claim_level, policy_reason, ambiguity_disclosures, alternatives = guarded_statement_for_finding(finding)
        strongest_indicator_entries.append(
            {
                "finding_id": str(finding.get("finding_id") or ""),
                "finding_label": str(finding.get("finding_label") or ""),
                "statement": statement,
                "claim_level": claim_level,
                "policy_reason": policy_reason,
                "supporting_citation_ids": supporting_citation_ids(finding),
                "supporting_uids": supporting_uids(finding),
                "ambiguity_disclosures": ambiguity_disclosures,
            }
        )
        for item in [*alternatives, *_as_list(finding.get("counter_indicators"))]:
            text = str(item).strip()
            if not text or text in seen_counterarguments:
                continue
            seen_counterarguments.add(text)
            strongest_counterarguments.append(
                {
                    "text": text,
                    "related_finding_id": str(finding.get("finding_id") or ""),
                    "supporting_citation_ids": supporting_citation_ids(finding, max_items=1),
                    "supporting_uids": supporting_uids(finding, max_items=1),
                }
            )
            if len(strongest_counterarguments) >= 3:
                break
        if len(strongest_counterarguments) >= 3:
            continue

    return {
        "strongest_indicators": strongest_indicator_entries,
        "strongest_counterarguments": strongest_counterarguments[:3],
    }


def ordered_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return findings in stable triage order."""
    return sorted(
        findings,
        key=lambda finding: (
            -strength_rank(str(_as_dict(finding.get("evidence_strength")).get("label") or "")),
            str(finding.get("finding_id") or ""),
        ),
    )


def triage_entry_for_finding(
    finding: dict[str, Any],
    *,
    entry_prefix: str,
    statement: str,
    policy_reason: str,
    ambiguity_disclosures: list[str],
    alternative_explanations: list[str],
) -> dict[str, Any]:
    """Return one evidence-triage entry anchored to a source finding."""
    return {
        "entry_id": f"{entry_prefix}:{finding.get('finding_id') or 'finding'}",
        "statement": statement,
        "policy_reason": policy_reason,
        "ambiguity_disclosures": ambiguity_disclosures,
        "alternative_explanations": alternative_explanations,
        "supporting_finding_ids": [str(finding.get("finding_id") or "")],
        "supporting_citation_ids": supporting_citation_ids(finding),
        "supporting_uids": supporting_uids(finding),
    }


def unresolved_reason_list(
    *,
    claim_level: str,
    evidence_strength: str,
    interpretation_confidence: str,
    ambiguity_disclosures: list[str],
    alternative_explanations: list[str],
) -> list[str]:
    """Return compact reasons why a point remains unresolved or not yet proven."""
    reasons = list(ambiguity_disclosures)
    if evidence_strength == "weak_indicator":
        reasons.append("The current support remains in the weak-indicator range.")
    if interpretation_confidence == "low":
        reasons.append("Interpretation confidence remains low on the current record.")
    if claim_level == "insufficient_evidence":
        reasons.append("The present record does not yet support a reliable conclusion.")
    for item in alternative_explanations:
        if item not in reasons:
            reasons.append(item)
    return reasons[:4]


def evidence_triage_section(
    findings: list[dict[str, Any]],
    *,
    missing_information_section: dict[str, Any],
) -> dict[str, Any]:
    """Return a counsel-facing triage split for direct support, inference, and open proof gaps."""
    direct_evidence: list[dict[str, Any]] = []
    reasonable_inference: list[dict[str, Any]] = []
    unresolved_points: list[dict[str, Any]] = []

    for finding in ordered_findings(findings):
        statement, _, policy_reason, ambiguity_disclosures, alternative_explanations = guarded_statement_for_finding(finding)
        claim_level, _ = classify_claim_level(finding)
        evidence_strength = str(_as_dict(finding.get("evidence_strength")).get("label") or "insufficient_evidence")
        interpretation_confidence = str(
            _as_dict(_as_dict(finding.get("confidence_split")).get("interpretation_confidence")).get("label") or "low"
        )

        if claim_level == "observed_fact":
            direct_evidence.append(
                triage_entry_for_finding(
                    finding,
                    entry_prefix="triage:direct",
                    statement=statement,
                    policy_reason=policy_reason,
                    ambiguity_disclosures=ambiguity_disclosures,
                    alternative_explanations=alternative_explanations,
                )
            )
        elif claim_level in {"pattern_concern", "stronger_interpretation"}:
            reasonable_inference.append(
                triage_entry_for_finding(
                    finding,
                    entry_prefix="triage:inference",
                    statement=statement,
                    policy_reason=policy_reason,
                    ambiguity_disclosures=ambiguity_disclosures,
                    alternative_explanations=alternative_explanations,
                )
            )

        unresolved_reasons = unresolved_reason_list(
            claim_level=claim_level,
            evidence_strength=evidence_strength,
            interpretation_confidence=interpretation_confidence,
            ambiguity_disclosures=ambiguity_disclosures,
            alternative_explanations=alternative_explanations,
        )
        if unresolved_reasons:
            label = _title(str(finding.get("finding_label") or "finding")).lower()
            unresolved_points.append(
                triage_entry_for_finding(
                    finding,
                    entry_prefix="triage:unresolved",
                    statement=f"Whether the current record ultimately proves {label} remains unresolved.",
                    policy_reason=(
                        "This point remains outside the direct-evidence layer because ambiguity, weakness, low confidence, "
                        "or live alternative explanations still limit the current read."
                    ),
                    ambiguity_disclosures=unresolved_reasons,
                    alternative_explanations=alternative_explanations,
                )
            )

    missing_proof = [
        {
            "entry_id": f"triage:missing:{entry.get('entry_id') or index}",
            "statement": str(entry.get("statement") or ""),
            "policy_reason": "This missing-proof item identifies evidence the current record still lacks.",
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": [],
        }
        for index, entry in enumerate(_as_list(missing_information_section.get("entries")), start=1)
        if isinstance(entry, dict) and str(entry.get("statement") or "").strip()
    ]

    summary = {
        "direct_evidence_count": len(direct_evidence),
        "reasonable_inference_count": len(reasonable_inference),
        "unresolved_point_count": len(unresolved_points),
        "missing_proof_count": len(missing_proof),
    }
    has_content = any(summary.values())
    return {
        "section_id": "evidence_triage",
        "title": "Evidence Triage",
        "status": "supported" if has_content else "insufficient_evidence",
        "entries": [],
        "insufficiency_reason": (
            ""
            if has_content
            else (
                "The current case bundle does not yet contain enough evidence to triage direct support, "
                "inference, unresolved points, or missing proof."
            )
        ),
        "summary": summary,
        "direct_evidence": direct_evidence[:4],
        "reasonable_inference": reasonable_inference[:4],
        "unresolved_points": unresolved_points[:4],
        "missing_proof": missing_proof[:4],
    }
