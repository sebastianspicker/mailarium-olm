"""Deterministic investigation-style report renderer for behavioural-analysis cases."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .behavioral_interpretation_policy import (
    guarded_statement_for_finding,
    interpretation_policy_payload,
)

INVESTIGATION_REPORT_VERSION = "1"
SECTION_ORDER = [
    "executive_summary",
    "chronological_pattern_analysis",
    "language_analysis",
    "behaviour_analysis",
    "power_context_analysis",
    "evidence_table",
    "overall_assessment",
    "missing_information",
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strength_rank(label: str) -> int:
    return {
        "strong_indicator": 4,
        "moderate_indicator": 3,
        "weak_indicator": 2,
        "insufficient_evidence": 1,
    }.get(str(label or ""), 0)


def _title(label: str) -> str:
    return str(label or "").replace("_", " ").capitalize()


def _supporting_citation_ids(finding: dict[str, Any], *, max_items: int = 2) -> list[str]:
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


def _supporting_uids(finding: dict[str, Any], *, max_items: int = 3) -> list[str]:
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


def _finding_entries(findings: list[dict[str, Any]], *, max_items: int = 3) -> list[dict[str, Any]]:
    ordered = sorted(
        findings,
        key=lambda finding: (
            -_strength_rank(str(_as_dict(finding.get("evidence_strength")).get("label") or "")),
            str(finding.get("finding_id") or ""),
        ),
    )
    entries: list[dict[str, Any]] = []
    for index, finding in enumerate(ordered[:max_items], start=1):
        statement, claim_level, policy_reason, ambiguity_disclosures, alternatives = guarded_statement_for_finding(
            finding
        )
        entries.append(
            {
                "entry_id": f"{finding.get('finding_id') or 'finding'}:entry:{index}",
                "statement": statement,
                "claim_level": claim_level,
                "policy_reason": policy_reason,
                "ambiguity_disclosures": ambiguity_disclosures,
                "alternative_explanations": alternatives,
                "supporting_finding_ids": [str(finding.get("finding_id") or "")],
                "supporting_citation_ids": _supporting_citation_ids(finding),
                "supporting_uids": _supporting_uids(finding),
            }
        )
    return entries


def _section_with_entries(
    *,
    section_id: str,
    title: str,
    entries: list[dict[str, Any]],
    insufficiency_reason: str,
) -> dict[str, Any]:
    if entries:
        return {
            "section_id": section_id,
            "title": title,
            "status": "supported",
            "entries": entries,
            "insufficiency_reason": "",
        }
    return {
        "section_id": section_id,
        "title": title,
        "status": "insufficient_evidence",
        "entries": [],
        "insufficiency_reason": insufficiency_reason,
    }


def _language_section(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    signal_counts: Counter[str] = Counter()
    signal_uids: dict[str, list[str]] = {}
    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        rhetoric = _as_dict(candidate.get("language_rhetoric"))
        authored_text = _as_dict(rhetoric.get("authored_text"))
        for signal in _as_list(authored_text.get("signals")):
            if not isinstance(signal, dict):
                continue
            signal_id = str(signal.get("signal_id") or "")
            if not signal_id:
                continue
            signal_counts[signal_id] += 1
            signal_uids.setdefault(signal_id, [])
            if uid and uid not in signal_uids[signal_id]:
                signal_uids[signal_id].append(uid)
    entries = [
        {
            "entry_id": f"language:{signal_id}",
            "statement": f"{_title(signal_id)} appears in {count} authored message(s).",
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": signal_uids.get(signal_id, [])[:3],
        }
        for signal_id, count in signal_counts.most_common(3)
    ]
    return _section_with_entries(
        section_id="language_analysis",
        title="Language Analysis",
        entries=entries,
        insufficiency_reason="No authored language-signal evidence was detected in the current case bundle.",
    )


def _timeline_section(timeline: dict[str, Any], case_patterns: dict[str, Any]) -> dict[str, Any]:
    events = [event for event in _as_list(timeline.get("events")) if isinstance(event, dict)]
    entries: list[dict[str, Any]] = []
    for index, event in enumerate(events[:3], start=1):
        uid = str(event.get("uid") or "")
        date = str(event.get("date") or "")
        entries.append(
            {
                "entry_id": f"timeline:{uid or index}",
                "statement": f"Timeline anchor message on {date[:10] or 'unknown date'} remains part of the current chronology.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [uid] if uid else [],
            }
        )
    for summary in _as_list(case_patterns.get("behavior_patterns"))[:2]:
        if not isinstance(summary, dict):
            continue
        cluster_id = str(summary.get("cluster_id") or "")
        recurrence = str(summary.get("primary_recurrence") or "")
        key = str(summary.get("key") or "pattern")
        entries.append(
            {
                "entry_id": f"pattern:{cluster_id}",
                "statement": f"{_title(key)} currently reads as {recurrence or 'unclassified'} over the available chronology.",
                "supporting_finding_ids": [cluster_id] if cluster_id else [],
                "supporting_citation_ids": [],
                "supporting_uids": [str(uid) for uid in _as_list(summary.get("message_uids"))[:3] if uid],
            }
        )
    return _section_with_entries(
        section_id="chronological_pattern_analysis",
        title="Chronological Pattern Analysis",
        entries=entries[:4],
        insufficiency_reason=(
            "The current case bundle does not yet contain enough chronological "
            "evidence to describe a pattern over time."
        ),
    )


def _power_section(
    power_context: dict[str, Any],
    communication_graph: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    supplied_role_facts = _as_list(power_context.get("supplied_role_facts"))
    if supplied_role_facts:
        entries.append(
            {
                "entry_id": "power:supplied_role_facts",
                "statement": f"Structured org context provides {len(supplied_role_facts)} supplied role fact(s) for this case.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    graph_findings = [finding for finding in _as_list(communication_graph.get("graph_findings")) if isinstance(finding, dict)]
    if graph_findings:
        first = graph_findings[0]
        entries.append(
            {
                "entry_id": f"power:{first.get('finding_id') or 'graph'}",
                "statement": (
                    "Communication-graph evidence highlights "
                    f"{_title(str(first.get('graph_signal_type') or 'graph signal')).lower()}."
                ),
                "supporting_finding_ids": [str(first.get("finding_id") or "")],
                "supporting_citation_ids": [],
                "supporting_uids": [
                    str(uid)
                    for uid in _as_list(_as_dict(first.get("evidence_chain")).get("message_uids"))[:3]
                    if uid
                ],
            }
        )
    comparator_summaries = [
        summary for summary in _as_list(comparative_treatment.get("comparator_summaries")) if isinstance(summary, dict)
    ]
    available = next((summary for summary in comparator_summaries if summary.get("status") == "comparator_available"), None)
    if isinstance(available, dict):
        finding_id = str(available.get("finding_id") or "")
        entries.append(
            {
                "entry_id": f"power:{finding_id or 'comparator'}",
                "statement": "Comparator evidence is available for target-versus-comparator treatment review.",
                "supporting_finding_ids": [finding_id] if finding_id else [],
                "supporting_citation_ids": [],
                "supporting_uids": [
                    str(uid)
                    for uid in _as_list(_as_dict(available.get("evidence_chain")).get("target_uids"))[:2]
                    if uid
                ],
            }
        )
    return _section_with_entries(
        section_id="power_context_analysis",
        title="Power and Context Analysis",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle lacks enough role, hierarchy, or comparator "
            "support to assess power dynamics confidently."
        ),
    )


def _evidence_table_section(evidence_table: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in _as_list(evidence_table.get("rows")) if isinstance(row, dict)]
    entries = [
        {
            "entry_id": f"evidence_table:{index}",
            "statement": (
                f"Evidence row for {_title(str(row.get('finding_label') or 'finding')).lower()} "
                f"remains exportable with handle {row.get('evidence_handle') or 'unknown'}."
            ),
            "supporting_finding_ids": [str(row.get("finding_id") or "")] if row.get("finding_id") else [],
            "supporting_citation_ids": [],
            "supporting_uids": [str(row.get("message_or_document_id") or "")] if row.get("message_or_document_id") else [],
        }
        for index, row in enumerate(rows[:3], start=1)
    ]
    return _section_with_entries(
        section_id="evidence_table",
        title="Evidence Table",
        entries=entries,
        insufficiency_reason="No exportable evidence rows are available for this case bundle.",
    )


def _overall_assessment_section(findings: list[dict[str, Any]]) -> dict[str, Any]:
    if not findings:
        return _section_with_entries(
            section_id="overall_assessment",
            title="Overall Assessment",
            entries=[],
            insufficiency_reason="The current case bundle does not yet support an overall assessment.",
        )
    strength_counts = Counter(
        str(_as_dict(finding.get("evidence_strength")).get("label") or "insufficient_evidence") for finding in findings
    )
    strongest = next(
        (
            label
            for label in ("strong_indicator", "moderate_indicator", "weak_indicator")
            if strength_counts.get(label, 0) > 0
        ),
        "insufficient_evidence",
    )
    strongest_findings = [
        finding
        for finding in findings
        if str(_as_dict(finding.get("evidence_strength")).get("label") or "") == strongest
    ]
    claim_levels = Counter(guarded_statement_for_finding(finding)[1] for finding in findings)
    dominant_claim_level = next(
        (
            level
            for level in (
                "stronger_interpretation",
                "pattern_concern",
                "observed_fact",
                "insufficient_evidence",
            )
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
    entries = [
        {
            "entry_id": "overall:strength",
            "statement": (
                f"The current record supports {_title(dominant_claim_level).lower()} wording, "
                f"with the strongest findings reaching {_title(strongest).lower()} across {len(strongest_findings)} finding(s)."
            ),
            "claim_level": dominant_claim_level,
            "policy_reason": (
                "The overall assessment stays within the strongest claim level defensible from the current finding set."
            ),
            "ambiguity_disclosures": ambiguity_disclosures,
            "alternative_explanations": alternative_explanations,
            "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in strongest_findings[:3]],
            "supporting_citation_ids": [
                citation_id
                for finding in strongest_findings[:2]
                for citation_id in _supporting_citation_ids(finding, max_items=1)
            ][:3],
            "supporting_uids": [
                uid for finding in strongest_findings[:2] for uid in _supporting_uids(finding, max_items=1)
            ][:3],
        }
    ]
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
    return _section_with_entries(
        section_id="overall_assessment",
        title="Overall Assessment",
        entries=entries,
        insufficiency_reason="The current case bundle does not yet support an overall assessment.",
    )


def _missing_information_section(
    case_bundle: dict[str, Any],
    power_context: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    scope = _as_dict(case_bundle.get("scope"))
    entries: list[dict[str, Any]] = []
    if not bool(_as_list(scope.get("trigger_events"))):
        entries.append(
            {
                "entry_id": "missing:trigger_events",
                "statement": "No explicit trigger events were supplied, so before/after retaliation analysis may remain limited.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    if bool(power_context.get("missing_org_context")):
        entries.append(
            {
                "entry_id": "missing:org_context",
                "statement": "Structured org or dependency context is missing, which limits power-dynamics interpretation.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    no_suitable = int(_as_dict(comparative_treatment.get("summary")).get("no_suitable_comparator_count") or 0)
    if no_suitable > 0:
        entries.append(
            {
                "entry_id": "missing:comparators",
                "statement": "Some comparator paths remain unavailable, which limits unequal-treatment assessment.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    return _section_with_entries(
        section_id="missing_information",
        title="Missing Information / Further Evidence Needed",
        entries=entries,
        insufficiency_reason="No additional missing-information markers were detected in the current case bundle.",
    )


def build_investigation_report(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    timeline: dict[str, Any] | None,
    power_context: dict[str, Any] | None,
    case_patterns: dict[str, Any] | None,
    retaliation_analysis: dict[str, Any] | None,
    comparative_treatment: dict[str, Any] | None,
    communication_graph: dict[str, Any] | None,
    finding_evidence_index: dict[str, Any] | None,
    evidence_table: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Render a structured investigation report from the current case-scoped payload."""
    if not isinstance(case_bundle, dict):
        return None
    findings = [
        finding for finding in _as_list(_as_dict(finding_evidence_index).get("findings")) if isinstance(finding, dict)
    ]
    executive_findings = [
        finding
        for finding in findings
        if str(finding.get("finding_scope") or "")
        in {"message_behavior", "case_pattern", "retaliation_analysis", "comparative_treatment", "communication_graph"}
    ]
    behaviour_findings = [
        finding
        for finding in findings
        if str(finding.get("finding_scope") or "")
        in {"message_behavior", "quoted_message_behavior", "case_pattern", "comparative_treatment", "communication_graph"}
    ]
    sections = {
        "executive_summary": _section_with_entries(
            section_id="executive_summary",
            title="Executive Summary",
            entries=_finding_entries(executive_findings, max_items=3),
            insufficiency_reason=(
                "The current case bundle does not yet contain enough supported "
                "findings for an executive summary."
            ),
        ),
        "chronological_pattern_analysis": _timeline_section(
            _as_dict(timeline),
            _as_dict(case_patterns),
        ),
        "language_analysis": _language_section(candidates),
        "behaviour_analysis": _section_with_entries(
            section_id="behaviour_analysis",
            title="Behaviour Analysis",
            entries=_finding_entries(behaviour_findings, max_items=4),
            insufficiency_reason="The current case bundle does not yet contain enough supported behaviour findings.",
        ),
        "power_context_analysis": _power_section(
            _as_dict(power_context),
            _as_dict(communication_graph),
            _as_dict(comparative_treatment),
        ),
        "evidence_table": _evidence_table_section(_as_dict(evidence_table)),
        "overall_assessment": _overall_assessment_section(findings),
        "missing_information": _missing_information_section(
            case_bundle,
            _as_dict(power_context),
            _as_dict(comparative_treatment),
        ),
    }
    supported_section_count = sum(1 for section in sections.values() if section.get("status") == "supported")
    return {
        "version": INVESTIGATION_REPORT_VERSION,
        "report_format": "investigation_briefing",
        "interpretation_policy": interpretation_policy_payload(),
        "section_order": SECTION_ORDER,
        "summary": {
            "section_count": len(SECTION_ORDER),
            "supported_section_count": supported_section_count,
            "insufficient_section_count": len(SECTION_ORDER) - supported_section_count,
        },
        "sections": sections,
    }


def compact_investigation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller BA16 report representation for tight response budgets."""
    compact_sections: dict[str, Any] = {}
    sections = _as_dict(report.get("sections"))
    for section_id in SECTION_ORDER:
        section = _as_dict(sections.get(section_id))
        entries = [entry for entry in _as_list(section.get("entries")) if isinstance(entry, dict)]
        compact_sections[section_id] = {
            "title": str(section.get("title") or ""),
            "status": str(section.get("status") or "insufficient_evidence"),
            "entry_count": len(entries),
            "entries": entries[:1],
            "insufficiency_reason": str(section.get("insufficiency_reason") or ""),
        }
    return {
        "version": str(report.get("version") or INVESTIGATION_REPORT_VERSION),
        "report_format": str(report.get("report_format") or "investigation_briefing"),
        "interpretation_policy": _as_dict(report.get("interpretation_policy")),
        "section_order": list(report.get("section_order") or SECTION_ORDER),
        "summary": dict(report.get("summary") or {}),
        "sections": compact_sections,
    }
