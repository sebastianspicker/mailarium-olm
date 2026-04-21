"""Employer-side skeptical review with paired repair guidance."""

from __future__ import annotations

from typing import Any

from .behavioral_interpretation_policy import cautious_rewrite_for_weakness, classify_claim_level
from .comparative_treatment import shared_comparator_points

SKEPTICAL_EMPLOYER_REVIEW_VERSION = "1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _weakness(
    *,
    weakness_id: str,
    category: str,
    critique: str,
    why_it_matters: str,
    how_to_fix: str,
    evidence_that_would_repair: str,
    subject: str,
    supporting_finding_ids: list[str] | None = None,
    supporting_citation_ids: list[str] | None = None,
    supporting_uids: list[str] | None = None,
    supporting_exhibit_ids: list[str] | None = None,
    supporting_chronology_ids: list[str] | None = None,
    supporting_issue_ids: list[str] | None = None,
    supporting_source_ids: list[str] | None = None,
    linked_date_gap_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "weakness_id": weakness_id,
        "category": category,
        "critique": critique,
        "why_it_matters": why_it_matters,
        "supporting_finding_ids": supporting_finding_ids or [],
        "supporting_citation_ids": supporting_citation_ids or [],
        "supporting_uids": supporting_uids or [],
        "supporting_exhibit_ids": supporting_exhibit_ids or [],
        "supporting_chronology_ids": supporting_chronology_ids or [],
        "supporting_issue_ids": supporting_issue_ids or [],
        "supporting_source_ids": supporting_source_ids or [],
        "linked_date_gap_ids": linked_date_gap_ids or [],
        "repair_guidance": {
            "how_to_fix": how_to_fix,
            "evidence_that_would_repair": evidence_that_would_repair,
            "cautious_rewrite": cautious_rewrite_for_weakness(
                weakness_category=category,
                subject=subject,
            ),
        },
    }


def build_skeptical_employer_review(
    *,
    findings: list[dict[str, Any]] | None,
    master_chronology: dict[str, Any] | None,
    matter_evidence_index: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    lawyer_issue_matrix: dict[str, Any] | None,
    overall_assessment: dict[str, Any] | None,
    retaliation_timeline_assessment: dict[str, Any] | None = None,
    case_scope_quality: dict[str, Any] | None = None,
    analysis_limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an employer-side weaknesses memo with paired repair guidance."""
    findings = [item for item in (findings or []) if isinstance(item, dict)]
    chronology_summary = _as_dict(_as_dict(master_chronology).get("summary"))
    matter_index = _as_dict(matter_evidence_index)
    comparison_summary = _as_dict(_as_dict(comparative_treatment).get("summary"))
    comparison_rows = shared_comparator_points(_as_dict(comparative_treatment))
    lawyer_rows = [row for row in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(row, dict)]
    overall = _as_dict(overall_assessment)
    retaliation_timeline = _as_dict(retaliation_timeline_assessment)
    scope_quality = _as_dict(case_scope_quality)
    limits = _as_dict(analysis_limits)
    weaknesses: list[dict[str, Any]] = []
    chronology_entries_by_id = {
        str(entry.get("chronology_id") or ""): entry
        for entry in _as_list(_as_dict(master_chronology).get("entries"))
        if isinstance(entry, dict) and str(entry.get("chronology_id") or "")
    }

    date_gaps = [gap for gap in _as_list(chronology_summary.get("date_gaps_and_unexplained_sequences")) if isinstance(gap, dict)]
    if date_gaps:
        gap = date_gaps[0]
        linked_chronology_ids = [
            str(item) for item in [gap.get("from_chronology_id"), gap.get("to_chronology_id")] if str(item or "").strip()
        ]
        linked_entries = [chronology_entries_by_id[item] for item in linked_chronology_ids if item in chronology_entries_by_id]
        weaknesses.append(
            _weakness(
                weakness_id="weakness:chronology_problem",
                category="chronology_problem",
                critique=(
                    "Employer-side review would argue that the chronology still contains material unexplained gaps "
                    f"around {gap.get('gap_id') or 'the current sequence'}."
                ),
                why_it_matters="Timeline gaps weaken temporal attribution and make sequencing challenges easier.",
                how_to_fix="Fill the gap with dated documents, meeting records, or contemporaneous correspondence.",
                evidence_that_would_repair=(
                    "Dated documents that bridge the missing period, especially records tied to the same issue track."
                ),
                subject="chronology gap",
                supporting_uids=[
                    str(item) for entry in linked_entries for item in _as_list(entry.get("supporting_uids")) if str(item).strip()
                ][:4],
                supporting_chronology_ids=linked_chronology_ids,
                supporting_source_ids=[
                    str(item)
                    for entry in linked_entries
                    for item in _as_list(_as_dict(entry.get("source_linkage")).get("source_ids"))
                    if str(item).strip()
                ][:4],
                linked_date_gap_ids=[str(gap.get("gap_id") or "")] if str(gap.get("gap_id") or "") else [],
            )
        )

    comparator_support_rows = [
        row for row in comparison_rows if str(row.get("comparison_strength") or "") in {"strong", "moderate"}
    ]
    weak_or_missing_rows = [
        row for row in comparison_rows if str(row.get("comparison_strength") or "") in {"weak", "not_comparable"}
    ]
    has_weak_or_missing_comparators = int(comparison_summary.get("no_suitable_comparator_count") or 0) > 0 or (
        weak_or_missing_rows and not comparator_support_rows
    )
    if has_weak_or_missing_comparators:
        first_point = weak_or_missing_rows[0] if weak_or_missing_rows else {}
        weaknesses.append(
            _weakness(
                weakness_id="weakness:overstated_comparison",
                category="overstated_comparison",
                critique=(
                    "Employer-side review would challenge the comparator case as overstated because comparator quality "
                    "is weak, incomplete, or not yet role-matched."
                    + (
                        " The clearest current weakness appears in "
                        f"{first_point.get('issue_label') or 'the current comparator slice'}."
                        if first_point
                        else ""
                    )
                ),
                why_it_matters="Comparator weakness undermines unequal-treatment and burden-shifting arguments first.",
                how_to_fix=(
                    "Add role-matched comparators, same-policy examples, and context for why the comparator is truly comparable."
                ),
                evidence_that_would_repair=(
                    ", ".join(str(item) for item in _as_list(first_point.get("missing_proof"))[:2])
                    or "Parallel treatment records for similarly situated peers under the same manager or policy."
                ),
                subject="comparator case",
            )
        )

    alternative_explanations = [
        str(item) for finding in findings for item in _as_list(finding.get("alternative_explanations")) if str(item).strip()
    ]
    if alternative_explanations:
        first_alt = alternative_explanations[0]
        weaknesses.append(
            _weakness(
                weakness_id="weakness:alternative_explanation",
                category="alternative_explanation",
                critique=f"Employer-side review would foreground this competing explanation: {first_alt}",
                why_it_matters="A live neutral explanation lowers the force of one-sided claimant framing.",
                how_to_fix="Show why the alternative explanation does not fit the timing, document trail, or treatment pattern.",
                evidence_that_would_repair=(
                    "Records that distinguish the claimant's sequence from ordinary workflow or operational conditions."
                ),
                subject="competing explanation",
            )
        )

    missing_exhibits = [item for item in _as_list(matter_index.get("top_10_missing_exhibits")) if isinstance(item, dict)]
    if missing_exhibits:
        missing = missing_exhibits[0]
        weaknesses.append(
            _weakness(
                weakness_id="weakness:missing_documentation",
                category="missing_documentation",
                critique=(
                    "Employer-side review would argue that a key documentary gap remains open: "
                    f"{missing.get('requested_exhibit') or 'missing exhibit'}."
                ),
                why_it_matters="Missing primary documents make the current narrative easier to contest.",
                how_to_fix="Request the missing document directly and tie it to the relevant issue track or chronology gap.",
                evidence_that_would_repair=str(
                    missing.get("requested_exhibit") or "Primary documentary support that closes the current gap."
                ),
                subject="missing documentary support",
            )
        )

    high_stakes_findings = [
        finding
        for finding in findings
        if any(term in str(finding.get("finding_label") or "").lower() for term in ("retaliat", "discrimin", "mobb"))
    ]
    if high_stakes_findings:
        claim_level, _ = classify_claim_level(high_stakes_findings[0])
        if claim_level != "observed_fact":
            first = high_stakes_findings[0]
            weaknesses.append(
                _weakness(
                    weakness_id="weakness:factual_leap",
                    category="factual_leap",
                    critique=(
                        "Employer-side review would say the current record still relies on inferential steps for one or more "
                        "high-stakes points."
                    ),
                    why_it_matters="Inferential leaps are easy to attack when direct text or documentary support is thin.",
                    how_to_fix=(
                        "Anchor the point to direct text, documentary language, or a tighter chronology-to-document sequence."
                    ),
                    evidence_that_would_repair=(
                        "Direct authored wording or formal records that support the same point without inferential expansion."
                    ),
                    subject=str(first.get("finding_label") or "high-stakes point"),
                    supporting_finding_ids=[str(first.get("finding_id") or "")] if first.get("finding_id") else [],
                )
            )

    primary_assessment = str(overall.get("primary_assessment") or "")
    if primary_assessment in {"retaliation_concern", "discrimination_concern", "targeted_hostility_concern"}:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:unsupported_motive_claim",
                category="unsupported_motive_claim",
                critique=(
                    "Employer-side review would argue that motive remains inferential and should not be presented as proven "
                    "from the current record."
                ),
                why_it_matters="Motive overstatement is a common point of attack in workplace-dispute records.",
                how_to_fix="Keep the framing at concern level unless direct proof or stronger corroboration emerges.",
                evidence_that_would_repair=(
                    "Direct statements, stronger comparator asymmetry, or documentary sequence "
                    "evidence that narrows motive ambiguity."
                ),
                subject=primary_assessment,
            )
        )

    weak_link_rows = [
        row
        for row in lawyer_rows
        if str(row.get("legal_relevance_status") or "") in {"currently_under_supported", "potentially_relevant"}
        and _as_list(row.get("missing_proof"))
    ]
    if weak_link_rows:
        row = weak_link_rows[0]
        weaknesses.append(
            _weakness(
                weakness_id="weakness:weak_legal_evidence_linkage",
                category="weak_legal_evidence_linkage",
                critique=(
                    f"Employer-side review would say the legal relevance theory for {row.get('title') or 'this issue'} "
                    "still outruns the present proof."
                ),
                why_it_matters="A weak legal-to-evidence link makes the theory look asserted rather than demonstrated.",
                how_to_fix=(
                    "Pair each legal relevance point with a source-backed proof element and close the listed missing-proof items."
                ),
                evidence_that_would_repair=(
                    ", ".join(str(item) for item in _as_list(row.get("missing_proof"))[:2])
                    or "Proof elements tied to the issue row."
                ),
                subject=str(row.get("title") or "issue track"),
                supporting_finding_ids=[str(item) for item in _as_list(row.get("supporting_finding_ids")) if item][:3],
                supporting_citation_ids=[str(item) for item in _as_list(row.get("supporting_citation_ids")) if item][:3],
                supporting_uids=[str(item) for item in _as_list(row.get("supporting_uids")) if item][:3],
                supporting_issue_ids=[str(row.get("issue_id") or "")] if str(row.get("issue_id") or "") else [],
                supporting_source_ids=[str(item) for item in _as_list(row.get("supporting_source_ids")) if item][:3],
            )
        )

    missing_fields = {str(item) for item in _as_list(scope_quality.get("missing_recommended_fields")) if str(item).strip()}
    if "comparator_actors" in missing_fields:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:missing_comparator_scope",
                category="overstated_comparison",
                critique=(
                    "Employer-side review would argue that comparator analysis remains "
                    "underdeveloped because no comparator actors were supplied."
                ),
                why_it_matters=("Without named comparators, unequal-treatment arguments are easier to attack as overstated."),
                how_to_fix=(
                    "Add role-matched comparator actors and the records showing their treatment under the same manager or policy."
                ),
                evidence_that_would_repair=(
                    "Role-matched comparator emails, approvals, restrictions, and project-allocation records."
                ),
                subject="comparator scope",
            )
        )
    if "org_context" in missing_fields:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:missing_org_context",
                category="missing_documentation",
                critique=(
                    "Employer-side review would argue that hierarchy, gatekeeping, and "
                    "power analysis remain under-documented because no org context was supplied."
                ),
                why_it_matters="Missing org context makes ordinary-management explanations easier to advance.",
                how_to_fix="Add reporting lines, dependency relationships, and concrete role facts for the relevant actors.",
                evidence_that_would_repair=(
                    "Organization charts, role descriptions, approval paths, and calendar/email routing records."
                ),
                subject="org context",
            )
        )
    if "alleged_adverse_actions" in missing_fields or "retaliation_focus_without_alleged_adverse_actions" in {
        str(item) for item in _as_list(limits.get("downgrade_reasons")) if str(item).strip()
    }:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:missing_adverse_action_detail",
                category="factual_leap",
                critique=(
                    "Employer-side review would say the retaliation narrative is still "
                    "too abstract because the adverse actions are not described as dated concrete events."
                ),
                why_it_matters="Undated or generic adverse-action framing is easier to dismiss as ordinary management.",
                how_to_fix="List dated adverse actions with the documents or chronology entries that support each one.",
                evidence_that_would_repair=(
                    "Project withdrawal records, control-change emails, exclusion "
                    "threads, or attendance-control entries tied to dates."
                ),
                subject="retaliation adverse actions",
            )
        )

    if _as_list(chronology_summary.get("sequence_breaks_and_contradictions")) or any(
        "mixed evidence" in str(item).lower() for item in _as_list(overall.get("downgrade_reasons"))
    ):
        weaknesses.append(
            _weakness(
                weakness_id="weakness:internal_inconsistency",
                category="internal_inconsistency",
                critique=(
                    "Employer-side review would emphasize internal inconsistency, chronology conflict, or mixed evidence "
                    "instead of reading the record as one-directional."
                ),
                why_it_matters="Mixed or conflicting internal signals reduce the force of a clean claimant narrative.",
                how_to_fix=(
                    "Separate confirmed facts from disputed inferences and resolve chronology conflicts with primary records."
                ),
                evidence_that_would_repair=(
                    "Primary records that reconcile timing conflicts or explain why the conflicting signal is not material."
                ),
                subject="internal consistency",
            )
        )

    ordinary_management_signals = [
        item for item in _as_list(retaliation_timeline.get("strongest_non_retaliatory_explanations")) if isinstance(item, dict)
    ]
    temporal_correlation_rows = [
        item for item in _as_list(retaliation_timeline.get("temporal_correlation_analysis")) if isinstance(item, dict)
    ]
    confounder_summary = (
        _as_dict(_as_dict(temporal_correlation_rows[0]).get("confounder_summary")) if temporal_correlation_rows else {}
    )
    if ordinary_management_signals or alternative_explanations:
        explanation = ""
        if ordinary_management_signals:
            explanation = str(ordinary_management_signals[0].get("explanation") or "")
        elif alternative_explanations:
            explanation = alternative_explanations[0]
        confounder_weight = str(confounder_summary.get("confounder_weight") or "")
        weaknesses.append(
            _weakness(
                weakness_id="weakness:ordinary_management_explanation",
                category="ordinary_management_explanation",
                critique=(
                    "Employer-side review would argue that ordinary management, workflow, or process explanations remain "
                    f"available on the current record{': ' + explanation if explanation else '.'}"
                    + (f" Confounder weight is currently {confounder_weight}." if confounder_weight else "")
                ),
                why_it_matters="Ordinary-management explanations can deflate hostility or retaliation framing quickly.",
                how_to_fix=(
                    "Show why the sequence differs from routine supervision, policy enforcement, or ordinary workflow management."
                ),
                evidence_that_would_repair=(
                    "Manager practice comparisons, internal policy documents, or records showing departure from normal process."
                ),
                subject="ordinary management explanation",
            )
        )

    summary = {
        "weakness_count": len(weaknesses),
        "weakness_categories": sorted(
            {str(item.get("category") or "") for item in weaknesses if str(item.get("category") or "")}
        ),
    }
    return {
        "version": SKEPTICAL_EMPLOYER_REVIEW_VERSION,
        "summary": summary,
        "weaknesses": weaknesses,
    }
