"""Employer-side skeptical review with paired repair guidance."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any

from src._utils import _as_dict, _as_list

from .behavioral_interpretation_policy import cautious_rewrite_for_weakness, classify_claim_level
from .comparative_treatment import shared_comparator_points

SKEPTICAL_EMPLOYER_REVIEW_VERSION = "1"


def _weakness(
    *,
    weakness_id: str,
    category: str,
    critique: str,
    why_it_matters: str,
    how_to_fix: str,
    evidence_that_would_repair: str,
    subject: str,
    **links: list[str] | None,
) -> dict[str, Any]:
    """Construct a weakness dictionary with repair guidance.

    Creates a structured weakness entry for the skeptical employer review,
    including the critique, its significance, and guidance on how to address it.

    Args:
        weakness_id: Unique identifier for the weakness.
        category: Category of the weakness (e.g., 'chronology_problem', 'factual_leap').
        critique: Employer-side critique of the issue.
        why_it_matters: Explanation of why this weakness is significant.
        how_to_fix: Guidance on how to remediate the weakness.
        evidence_that_would_repair: Description of evidence that would resolve the issue.
        subject: Subject or topic of the weakness.
        supporting_finding_ids: Optional list of finding IDs supporting this weakness.
        supporting_citation_ids: Optional list of citation IDs supporting this weakness.
        supporting_uids: Optional list of document UIDs supporting this weakness.
        supporting_exhibit_ids: Optional list of exhibit IDs supporting this weakness.
        supporting_chronology_ids: Optional list of chronology IDs supporting this weakness.
        supporting_issue_ids: Optional list of issue IDs supporting this weakness.
        supporting_source_ids: Optional list of source IDs supporting this weakness.
        linked_date_gap_ids: Optional list of date gap IDs linked to this weakness.

    Returns:
        Dictionary containing the weakness structure with repair_guidance sub-dictionary.
    """
    return {
        "weakness_id": weakness_id,
        "category": category,
        "critique": critique,
        "why_it_matters": why_it_matters,
        "supporting_finding_ids": links.get("supporting_finding_ids") or [],
        "supporting_citation_ids": links.get("supporting_citation_ids") or [],
        "supporting_uids": links.get("supporting_uids") or [],
        "supporting_exhibit_ids": links.get("supporting_exhibit_ids") or [],
        "supporting_chronology_ids": links.get("supporting_chronology_ids") or [],
        "supporting_issue_ids": links.get("supporting_issue_ids") or [],
        "supporting_source_ids": links.get("supporting_source_ids") or [],
        "linked_date_gap_ids": links.get("linked_date_gap_ids") or [],
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
    findings = _dict_rows(findings)
    chronology_summary = _as_dict(_as_dict(master_chronology).get("summary"))
    matter_index = _as_dict(matter_evidence_index)
    comparison_summary = _as_dict(_as_dict(comparative_treatment).get("summary"))
    comparison_rows = shared_comparator_points(_as_dict(comparative_treatment))
    lawyer_rows = _dict_rows(_as_dict(lawyer_issue_matrix).get("rows"))
    overall = _as_dict(overall_assessment)
    retaliation_timeline = _as_dict(retaliation_timeline_assessment)
    scope_quality = _as_dict(case_scope_quality)
    limits = _as_dict(analysis_limits)
    weaknesses: list[dict[str, Any]] = []
    chronology_entries_by_id = _chronology_entry_map(master_chronology)

    _append_chronology_weakness(weaknesses, chronology_summary, chronology_entries_by_id)

    _append_comparator_weakness(weaknesses, comparison_rows, comparison_summary)

    alternative_explanations = _alternative_explanations(findings)
    _append_alternative_weakness(weaknesses, alternative_explanations)
    _append_missing_documentation_weakness(weaknesses, matter_index)

    _append_high_stakes_weakness(weaknesses, findings)
    _append_motive_weakness(weaknesses, overall)
    _append_legal_linkage_weakness(weaknesses, lawyer_rows)

    missing_fields = _nonempty_strings(scope_quality.get("missing_recommended_fields"))
    _append_scope_weaknesses(weaknesses, missing_fields, limits)

    _append_internal_consistency_weakness(weaknesses, chronology_summary, overall)

    _append_ordinary_management_weakness(weaknesses, retaliation_timeline, alternative_explanations)

    summary = _weakness_summary(weaknesses)
    return {
        "version": SKEPTICAL_EMPLOYER_REVIEW_VERSION,
        "summary": summary,
        "weaknesses": weaknesses,
    }


def _dict_rows(value) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _chronology_entry_map(master_chronology):
    entries = _dict_rows(_as_dict(master_chronology).get("entries"))
    return {entry_id: entry for entry in entries if (entry_id := str(entry.get("chronology_id") or ""))}


def _alternative_explanations(findings):
    return [str(item) for finding in findings for item in _as_list(finding.get("alternative_explanations")) if str(item).strip()]


def _nonempty_strings(value) -> set[str]:
    return {str(item) for item in _as_list(value) if str(item).strip()}


def _weakness_summary(weaknesses):
    categories = {str(item.get("category") or "") for item in weaknesses if str(item.get("category") or "")}
    return {"weakness_count": len(weaknesses), "weakness_categories": sorted(categories)}


def _append_chronology_weakness(weaknesses, summary, entries_by_id):
    gaps = [gap for gap in _as_list(summary.get("date_gaps_and_unexplained_sequences")) if isinstance(gap, dict)]
    if not gaps:
        return
    gap = gaps[0]
    ids = [str(item) for item in (gap.get("from_chronology_id"), gap.get("to_chronology_id")) if str(item or "").strip()]
    entries = [entries_by_id[item] for item in ids if item in entries_by_id]
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
            supporting_uids=_entry_values(entries, "supporting_uids")[:4],
            supporting_chronology_ids=ids,
            supporting_source_ids=_entry_source_ids(entries)[:4],
            linked_date_gap_ids=[str(gap.get("gap_id") or "")] if str(gap.get("gap_id") or "") else [],
        )
    )


def _entry_values(entries, key):
    return [str(item) for entry in entries for item in _as_list(entry.get(key)) if str(item).strip()]


def _entry_source_ids(entries):
    return [
        str(item)
        for entry in entries
        for item in _as_list(_as_dict(entry.get("source_linkage")).get("source_ids"))
        if str(item).strip()
    ]


def _append_comparator_weakness(weaknesses, rows, summary):
    supported = _rows_with_strength(rows, {"strong", "moderate"})
    weak = _rows_with_strength(rows, {"weak", "not_comparable"})
    if not _comparator_support_is_weak(summary, weak, supported):
        return
    point = weak[0] if weak else {}
    suffix = _comparator_suffix(point)
    weaknesses.append(
        _weakness(
            weakness_id="weakness:overstated_comparison",
            category="overstated_comparison",
            critique=(
                "Employer-side review would challenge the comparator case as overstated because comparator "
                "quality is weak, incomplete, or not yet role-matched."
            )
            + suffix,
            why_it_matters="Comparator weakness undermines unequal-treatment and burden-shifting arguments first.",
            how_to_fix=(
                "Add role-matched comparators, same-policy examples, and context for why the comparator is truly comparable."
            ),
            evidence_that_would_repair=", ".join(str(item) for item in _as_list(point.get("missing_proof"))[:2])
            or "Parallel treatment records for similarly situated peers under the same manager or policy.",
            subject="comparator case",
        )
    )


def _rows_with_strength(rows, strengths):
    return [row for row in rows if str(row.get("comparison_strength") or "") in strengths]


def _comparator_support_is_weak(summary, weak, supported):
    if int(summary.get("no_suitable_comparator_count") or 0) > 0:
        return True
    return bool(weak and not supported)


def _comparator_suffix(point):
    if not point:
        return ""
    return f" The clearest current weakness appears in {point.get('issue_label') or 'the current comparator slice'}."


def _append_alternative_weakness(weaknesses, alternatives):
    if alternatives:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:alternative_explanation",
                category="alternative_explanation",
                critique=f"Employer-side review would foreground this competing explanation: {alternatives[0]}",
                why_it_matters="A live neutral explanation lowers the force of one-sided claimant framing.",
                how_to_fix="Show why the alternative explanation does not fit the timing, document trail, or treatment pattern.",
                evidence_that_would_repair=(
                    "Records that distinguish the claimant's sequence from ordinary workflow or operational conditions."
                ),
                subject="competing explanation",
            )
        )


def _append_missing_documentation_weakness(weaknesses, matter_index):
    exhibits = [item for item in _as_list(matter_index.get("top_10_missing_exhibits")) if isinstance(item, dict)]
    if not exhibits:
        return
    missing = exhibits[0]
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


def _append_high_stakes_weakness(weaknesses, findings):
    high_stakes = [
        finding
        for finding in findings
        if any(term in str(finding.get("finding_label") or "").lower() for term in ("retaliat", "discrimin", "mobb"))
    ]
    if not high_stakes or classify_claim_level(high_stakes[0])[0] == "observed_fact":
        return
    first = high_stakes[0]
    weaknesses.append(
        _weakness(
            weakness_id="weakness:factual_leap",
            category="factual_leap",
            critique=(
                "Employer-side review would say the current record still relies on inferential steps for "
                "one or more high-stakes points."
            ),
            why_it_matters="Inferential leaps are easy to attack when direct text or documentary support is thin.",
            how_to_fix="Anchor the point to direct text, documentary language, or a tighter chronology-to-document sequence.",
            evidence_that_would_repair=(
                "Direct authored wording or formal records that support the same point without inferential expansion."
            ),
            subject=str(first.get("finding_label") or "high-stakes point"),
            supporting_finding_ids=[str(first.get("finding_id") or "")] if first.get("finding_id") else [],
        )
    )


def _append_motive_weakness(weaknesses, overall):
    assessment = str(overall.get("primary_assessment") or "")
    if assessment not in {"retaliation_concern", "discrimination_concern", "targeted_hostility_concern"}:
        return
    weaknesses.append(
        _weakness(
            weakness_id="weakness:unsupported_motive_claim",
            category="unsupported_motive_claim",
            critique=(
                "Employer-side review would argue that motive remains inferential and should not be "
                "presented as proven from the current record."
            ),
            why_it_matters="Motive overstatement is a common point of attack in workplace-dispute records.",
            how_to_fix="Keep the framing at concern level unless direct proof or stronger corroboration emerges.",
            evidence_that_would_repair=(
                "Direct statements, stronger comparator asymmetry, or documentary sequence evidence that "
                "narrows motive ambiguity."
            ),
            subject=assessment,
        )
    )


def _append_legal_linkage_weakness(weaknesses, lawyer_rows):
    rows = [
        row
        for row in lawyer_rows
        if str(row.get("legal_relevance_status") or "") in {"currently_under_supported", "potentially_relevant"}
        and _as_list(row.get("missing_proof"))
    ]
    if not rows:
        return
    row = rows[0]
    weaknesses.append(
        _weakness(
            weakness_id="weakness:weak_legal_evidence_linkage",
            category="weak_legal_evidence_linkage",
            critique=(
                "Employer-side review would say the legal relevance theory for "
                f"{row.get('title') or 'this issue'} still outruns the present proof."
            ),
            why_it_matters="A weak legal-to-evidence link makes the theory look asserted rather than demonstrated.",
            how_to_fix=(
                "Pair each legal relevance point with a source-backed proof element and close the listed missing-proof items."
            ),
            evidence_that_would_repair=", ".join(str(item) for item in _as_list(row.get("missing_proof"))[:2])
            or "Proof elements tied to the issue row.",
            subject=str(row.get("title") or "issue track"),
            supporting_finding_ids=_first_three(row, "supporting_finding_ids"),
            supporting_citation_ids=_first_three(row, "supporting_citation_ids"),
            supporting_uids=_first_three(row, "supporting_uids"),
            supporting_issue_ids=[str(row.get("issue_id") or "")] if str(row.get("issue_id") or "") else [],
            supporting_source_ids=_first_three(row, "supporting_source_ids"),
        )
    )


def _first_three(row, key):
    return [str(item) for item in _as_list(row.get(key)) if item][:3]


def _append_scope_weaknesses(weaknesses, missing_fields, limits):
    if "comparator_actors" in missing_fields:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:missing_comparator_scope",
                category="overstated_comparison",
                critique=(
                    "Employer-side review would argue that comparator analysis remains underdeveloped because "
                    "no comparator actors were supplied."
                ),
                why_it_matters="Without named comparators, unequal-treatment arguments are easier to attack as overstated.",
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
                    "Employer-side review would argue that hierarchy, gatekeeping, and power analysis remain "
                    "under-documented because no org context was supplied."
                ),
                why_it_matters="Missing org context makes ordinary-management explanations easier to advance.",
                how_to_fix="Add reporting lines, dependency relationships, and concrete role facts for the relevant actors.",
                evidence_that_would_repair=(
                    "Organization charts, role descriptions, approval paths, and calendar/email routing records."
                ),
                subject="org context",
            )
        )
    downgrade_reasons = {str(item) for item in _as_list(limits.get("downgrade_reasons")) if str(item).strip()}
    if "alleged_adverse_actions" in missing_fields or "retaliation_focus_without_alleged_adverse_actions" in downgrade_reasons:
        weaknesses.append(
            _weakness(
                weakness_id="weakness:missing_adverse_action_detail",
                category="factual_leap",
                critique=(
                    "Employer-side review would say the retaliation narrative is still too abstract because "
                    "the adverse actions are not described as dated concrete events."
                ),
                why_it_matters="Undated or generic adverse-action framing is easier to dismiss as ordinary management.",
                how_to_fix="List dated adverse actions with the documents or chronology entries that support each one.",
                evidence_that_would_repair=(
                    "Project withdrawal records, control-change emails, exclusion threads, or "
                    "attendance-control entries tied to dates."
                ),
                subject="retaliation adverse actions",
            )
        )


def _append_internal_consistency_weakness(weaknesses, chronology_summary, overall):
    mixed = any("mixed evidence" in str(item).lower() for item in _as_list(overall.get("downgrade_reasons")))
    if not (_as_list(chronology_summary.get("sequence_breaks_and_contradictions")) or mixed):
        return
    weaknesses.append(
        _weakness(
            weakness_id="weakness:internal_inconsistency",
            category="internal_inconsistency",
            critique=(
                "Employer-side review would emphasize internal inconsistency, chronology conflict, or "
                "mixed evidence instead of reading the record as one-directional."
            ),
            why_it_matters="Mixed or conflicting internal signals reduce the force of a clean claimant narrative.",
            how_to_fix="Separate confirmed facts from disputed inferences and resolve chronology conflicts with primary records.",
            evidence_that_would_repair=(
                "Primary records that reconcile timing conflicts or explain why the conflicting signal is not material."
            ),
            subject="internal consistency",
        )
    )


def _append_ordinary_management_weakness(weaknesses, timeline, alternatives):
    signals = _dict_rows(timeline.get("strongest_non_retaliatory_explanations"))
    correlations = _dict_rows(timeline.get("temporal_correlation_analysis"))
    if not signals and not alternatives:
        return
    explanation = _ordinary_explanation(signals, alternatives)
    confounders = _first_confounder_summary(correlations)
    weight = str(confounders.get("confounder_weight") or "")
    punctuation = ": " + explanation if explanation else "."
    weight_text = f" Confounder weight is currently {weight}." if weight else ""
    weaknesses.append(
        _weakness(
            weakness_id="weakness:ordinary_management_explanation",
            category="ordinary_management_explanation",
            critique=(
                "Employer-side review would argue that ordinary management, workflow, or process explanations "
                "remain available on the current record"
            )
            + punctuation
            + weight_text,
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


def _ordinary_explanation(signals, alternatives):
    if signals:
        return str(signals[0].get("explanation") or "")
    return alternatives[0]


def _first_confounder_summary(correlations):
    if not correlations:
        return {}
    return _as_dict(_as_dict(correlations[0]).get("confounder_summary"))
