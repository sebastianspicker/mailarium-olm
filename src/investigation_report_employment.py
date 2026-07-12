"""Employment-issue and chronology helpers for investigation reports."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals,too-many-statements,redefined-outer-name

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .employment_issue_frameworks import ISSUE_TRACK_DEFINITIONS
from .investigation_report_assessment import NON_WEAK_STRENGTHS, scope_has_protected_context
from .investigation_report_findings import supporting_citation_ids, supporting_uids
from .investigation_report_sections import _as_dict, _as_list, _section_with_entries


def text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return whether any keyword occurs in normalized text."""
    normalized = " ".join(str(text or "").lower().split())
    return any(keyword in normalized for keyword in keywords)


def _add_issue_tag(
    summary: dict[str, list[dict[str, str]]],
    seen_by_basis: dict[str, set[str]],
    tag: Any,
) -> None:
    tag_data = _as_dict(tag)
    basis = str(tag_data.get("assignment_basis") or "")
    tag_id = str(tag_data.get("tag_id") or "")
    if basis not in summary or not tag_id or tag_id in seen_by_basis[basis]:
        return
    seen_by_basis[basis].add(tag_id)
    summary[basis].append(
        {
            "tag_id": tag_id,
            "label": str(tag_data.get("label") or ""),
            "evidence_status": str(tag_data.get("evidence_status") or ""),
        }
    )


def _issue_tag_summary(matter_evidence_index: dict[str, Any] | None) -> dict[str, list[dict[str, str]]]:
    summary: dict[str, list[dict[str, str]]] = {
        "operator_supplied": [],
        "direct_document_content": [],
        "bounded_inference": [],
    }
    seen_by_basis: dict[str, set[str]] = {basis: set() for basis in summary}
    rows = _as_list(_as_dict(matter_evidence_index).get("rows"))
    for row in rows:
        for tag in _as_list(_as_dict(row).get("issue_tags")):
            _add_issue_tag(summary, seen_by_basis, tag)
    return summary


@dataclass(frozen=True)
class _EmploymentIssueContext:
    case_bundle: dict[str, Any]
    scope: dict[str, Any]
    context_notes: str
    overall_primary: str
    overall_secondary: set[str]
    finding_scopes: set[str]
    strong_or_moderate: bool
    missing_statements: list[str]
    comparator_summaries: list[dict[str, Any]]
    comparative_treatment: dict[str, Any]


def _string_set(value: Any) -> set[str]:
    return {str(item) for item in _as_list(value) if item}


def _finding_scopes(findings: list[dict[str, Any]]) -> set[str]:
    return {str(finding.get("finding_scope") or "") for finding in findings}


def _has_non_weak_finding(findings: list[dict[str, Any]]) -> bool:
    return any(str(_as_dict(finding.get("evidence_strength")).get("label") or "") in NON_WEAK_STRENGTHS for finding in findings)


def _entry_statements(value: Any) -> list[str]:
    return [str(entry.get("statement") or "") for entry in _as_list(value) if isinstance(entry, dict)]


def _dict_entries_unbounded(value: Any) -> list[dict[str, Any]]:
    return [entry for entry in _as_list(value) if isinstance(entry, dict)]


def _employment_issue_context(
    *,
    case_bundle: dict[str, Any],
    findings: list[dict[str, Any]],
    comparative_treatment: dict[str, Any],
    overall_assessment: dict[str, Any],
    missing_information_section: dict[str, Any],
) -> _EmploymentIssueContext:
    scope = _as_dict(case_bundle.get("scope"))
    return _EmploymentIssueContext(
        case_bundle=case_bundle,
        scope=scope,
        context_notes=str(scope.get("context_notes") or ""),
        overall_primary=str(overall_assessment.get("primary_assessment") or ""),
        overall_secondary=_string_set(overall_assessment.get("secondary_plausible_interpretations")),
        finding_scopes=_finding_scopes(findings),
        strong_or_moderate=_has_non_weak_finding(findings),
        missing_statements=_entry_statements(missing_information_section.get("entries")),
        comparator_summaries=_dict_entries_unbounded(comparative_treatment.get("comparator_summaries")),
        comparative_treatment=comparative_treatment,
    )


def _disability_support(context: _EmploymentIssueContext) -> tuple[str, str]:
    supported = scope_has_protected_context(context.case_bundle) and (
        context.overall_primary in {"discrimination_concern", "unequal_treatment_concern"}
        or any(bool(summary.get("supports_discrimination_concern")) for summary in context.comparator_summaries)
    )
    if supported:
        return (
            "supported_by_current_record",
            "Protected-context support and current unequal-treatment or discrimination indicators are both present.",
        )
    return "alleged_but_not_yet_evidenced", "The current record does not yet contain enough issue-specific support."


def _retaliation_support(context: _EmploymentIssueContext) -> tuple[str, str]:
    supported = bool(_as_list(context.scope.get("trigger_events"))) and (
        "retaliation_analysis" in context.finding_scopes
        or context.overall_primary == "retaliation_concern"
        or "retaliation_concern" in context.overall_secondary
    )
    if supported:
        return (
            "supported_by_current_record",
            "A trigger event is present and the current record still supports retaliation-style review.",
        )
    return "alleged_but_not_yet_evidenced", "The current record does not yet contain enough issue-specific support."


def _classification_support(context: _EmploymentIssueContext) -> tuple[str, str]:
    default = "The current record does not yet contain enough issue-specific support."
    if not text_contains_any(context.context_notes, ("eingruppierung", "entgeltgruppe", "vergütungsgruppe", "tarif", "td ")):
        return "alleged_but_not_yet_evidenced", default
    has_support = context.strong_or_moderate and (
        "comparative_treatment" in context.finding_scopes
        or "communication_graph" in context.finding_scopes
        or int(_as_dict(context.comparative_treatment.get("summary")).get("available_comparator_count") or 0) > 0
    )
    if has_support:
        return (
            "supported_by_current_record",
            "The intake names a classification dispute and the current record contains non-trivial supporting evidence.",
        )
    return (
        "alleged_but_not_yet_evidenced",
        "The intake names a classification dispute, but stronger role or HR-document support is still missing.",
    )


def _prevention_support(context: _EmploymentIssueContext) -> tuple[str, str]:
    has_concern = scope_has_protected_context(context.case_bundle) and text_contains_any(
        context.context_notes, ("bem", "prävention", "praevention", "sgb ix", "167", "workability")
    )
    if has_concern and context.strong_or_moderate:
        return (
            "supported_by_current_record",
            "Health-context support and prevention-process cues are both visible in the current record.",
        )
    if has_concern:
        return (
            "alleged_but_not_yet_evidenced",
            "A prevention-oriented concern is visible, but the current record is still too thin for stronger support.",
        )
    return "alleged_but_not_yet_evidenced", "The current record does not yet contain enough issue-specific support."


def _participation_support(context: _EmploymentIssueContext) -> tuple[str, str]:
    has_concern = text_contains_any(
        context.context_notes,
        ("sbv", "schwerbehindertenvertretung", "personalrat", "betriebsrat", "mitbestimmung", "participation"),
    )
    has_support = context.strong_or_moderate or any(
        "participation" in statement.lower() for statement in context.missing_statements
    )
    if has_concern and has_support:
        return (
            "supported_by_current_record",
            "The intake names a participation path and the current record contains at least "
            "some process support for that concern.",
        )
    if has_concern:
        return (
            "alleged_but_not_yet_evidenced",
            "A participation issue is alleged, but the current record still lacks concrete consultation proof.",
        )
    return "alleged_but_not_yet_evidenced", "The current record does not yet contain enough issue-specific support."


def _issue_support(issue_track: str, context: _EmploymentIssueContext) -> tuple[str, str]:
    evaluators = {
        "disability_disadvantage": _disability_support,
        "retaliation_after_protected_event": _retaliation_support,
        "eingruppierung_dispute": _classification_support,
        "prevention_duty_gap": _prevention_support,
        "participation_duty_gap": _participation_support,
    }
    evaluator = evaluators.get(issue_track)
    if evaluator is None:
        return "alleged_but_not_yet_evidenced", "The current record does not yet contain enough issue-specific support."
    return evaluator(context)


def _finding_ids(findings: list[dict[str, Any]]) -> list[str]:
    return [str(finding.get("finding_id") or "") for finding in findings[:3]]


def _supporting_citations(findings: list[dict[str, Any]]) -> list[str]:
    return [citation_id for finding in findings[:2] for citation_id in supporting_citation_ids(finding, max_items=1)][:3]


def _supporting_uids(findings: list[dict[str, Any]]) -> list[str]:
    return [uid for finding in findings[:2] for uid in supporting_uids(finding, max_items=1)][:3]


def _why_not_supported(status: str, support_reason: str, missing_statements: list[str]) -> list[str]:
    if status == "supported_by_current_record":
        return []
    return list(dict.fromkeys(missing_statements))[:3] or [support_reason]


def _issue_payload(
    *,
    issue_track: str,
    definition: dict[str, Any],
    findings: list[dict[str, Any]],
    context: _EmploymentIssueContext,
) -> dict[str, Any]:
    status, support_reason = _issue_support(issue_track, context)
    return {
        "issue_track": issue_track,
        "title": str(definition.get("title") or issue_track),
        "neutral_question": str(definition.get("neutral_question") or ""),
        "status": status,
        "support_reason": support_reason,
        "required_proof_elements": list(definition.get("required_proof_elements") or []),
        "normal_alternative_explanations": list(definition.get("normal_alternative_explanations") or []),
        "missing_document_checklist": list(definition.get("missing_document_checklist") or []),
        "minimum_source_quality_expectations": list(definition.get("minimum_source_quality_expectations") or []),
        "why_not_yet_supported": _why_not_supported(status, support_reason, context.missing_statements),
        "supporting_finding_ids": _finding_ids(findings),
        "supporting_citation_ids": _supporting_citations(findings),
        "supporting_uids": _supporting_uids(findings),
    }


def _empty_employment_issue_section(issue_tag_summary: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    section = _section_with_entries(
        section_id="employment_issue_frameworks",
        title="Employment Issue Frameworks",
        entries=[],
        insufficiency_reason="No employment issue tracks were selected for this case.",
    )
    section["issue_tag_summary"] = issue_tag_summary
    return section


def _employment_issue_entry(issue_track: str, issue_payload: dict[str, Any]) -> dict[str, Any]:
    status = str(issue_payload["status"])
    support_reason = str(issue_payload["support_reason"])
    return {
        "entry_id": f"employment_issue:{issue_track}",
        "statement": (f"{issue_payload['title']} is currently marked as {status.replace('_', ' ')}. {support_reason}"),
        "supporting_finding_ids": issue_payload["supporting_finding_ids"],
        "supporting_citation_ids": issue_payload["supporting_citation_ids"],
        "supporting_uids": issue_payload["supporting_uids"],
    }


def employment_issue_frameworks_section(
    *,
    case_bundle: dict[str, Any],
    findings: list[dict[str, Any]],
    comparative_treatment: dict[str, Any],
    overall_assessment: dict[str, Any],
    missing_information_section: dict[str, Any],
    matter_evidence_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return neutral employment-matter issue frameworks for selected issue tracks."""
    scope = _as_dict(case_bundle.get("scope"))
    issue_tracks = [track for track in _as_list(scope.get("employment_issue_tracks")) if isinstance(track, str)]
    issue_tag_summary = _issue_tag_summary(matter_evidence_index)
    if not issue_tracks:
        return _empty_employment_issue_section(issue_tag_summary)

    context = _employment_issue_context(
        case_bundle=case_bundle,
        findings=findings,
        comparative_treatment=comparative_treatment,
        overall_assessment=overall_assessment,
        missing_information_section=missing_information_section,
    )

    issue_payloads: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    for issue_track in issue_tracks:
        definition = ISSUE_TRACK_DEFINITIONS.get(issue_track)
        if definition is None:
            continue

        issue_payload = _issue_payload(
            issue_track=issue_track,
            definition=definition,
            findings=findings,
            context=context,
        )
        issue_payloads.append(issue_payload)
        entries.append(_employment_issue_entry(issue_track, issue_payload))

    section = _section_with_entries(
        section_id="employment_issue_frameworks",
        title="Employment Issue Frameworks",
        entries=entries,
        insufficiency_reason="No employment issue tracks were selected for this case.",
    )
    section["issue_tracks"] = issue_payloads
    section["issue_tag_summary"] = issue_tag_summary
    return section


def _string_items(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value) if item]


def _compact_event_support_matrix(value: Any) -> dict[str, dict[str, Any]]:
    return {
        str(read_id): {
            "status": str(read_payload.get("status") or ""),
            "linked_issue_tags": _string_items(read_payload.get("linked_issue_tags")),
            "selected_in_case_scope": bool(read_payload.get("selected_in_case_scope")),
        }
        for read_id, read_payload in _as_dict(value).items()
        if str(read_id).strip() and isinstance(read_payload, dict)
    }


def _compact_source_linkage(value: Any) -> dict[str, list[str]]:
    linkage = _as_dict(value)
    return {
        "source_ids": _string_items(linkage.get("source_ids")),
        "source_types": _string_items(linkage.get("source_types")),
        "supporting_uids": _string_items(linkage.get("supporting_uids")),
        "supporting_citation_ids": _string_items(linkage.get("supporting_citation_ids")),
    }


def _compact_chronology_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "chronology_id": str(entry.get("chronology_id") or ""),
        "date": str(entry.get("date") or ""),
        "date_precision": str(entry.get("date_precision") or ""),
        "entry_type": str(entry.get("entry_type") or ""),
        "title": str(entry.get("title") or ""),
        "event_support_matrix": _compact_event_support_matrix(entry.get("event_support_matrix")),
        "source_linkage": _compact_source_linkage(entry.get("source_linkage")),
    }


def _compact_chronology_views(value: Any) -> dict[Any, dict[str, Any]]:
    return {
        view_id: {
            "view_id": str(_as_dict(view_payload).get("view_id") or view_id),
            "entry_count": int(_as_dict(view_payload).get("entry_count") or 0),
            "summary": dict(_as_dict(view_payload).get("summary") or {}),
        }
        for view_id, view_payload in _as_dict(value).items()
        if str(view_id).strip()
    }


def _chronology_entries(value: Any) -> list[dict[str, Any]]:
    return [entry for entry in _as_list(value) if isinstance(entry, dict)]


def _int_or(value: Any, fallback: int) -> int:
    return int(value or fallback)


def report_master_chronology_payload(master_chronology: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact chronology payload for the report surface."""
    chronology = _as_dict(master_chronology)
    entries = _chronology_entries(chronology.get("entries"))
    compact_entries = [_compact_chronology_entry(entry) for entry in entries[:4]]
    return {
        "version": str(chronology.get("version") or ""),
        "entry_count": _int_or(chronology.get("entry_count"), len(entries)),
        "primary_entry_count": _int_or(chronology.get("primary_entry_count"), 0),
        "scope_supplied_entry_count": _int_or(chronology.get("scope_supplied_entry_count"), 0),
        "summary": dict(chronology.get("summary") or {}),
        "entries": compact_entries,
        "views": _compact_chronology_views(chronology.get("views")),
        "_truncated": max(0, len(entries) - len(compact_entries)),
    }


def _dict_entries(value: Any, limit: int) -> list[dict[str, Any]]:
    return [dict(entry) for entry in _as_list(value)[:limit] if isinstance(entry, dict)]


def report_retaliation_timeline_payload(retaliation_analysis: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact retaliation timeline assessment for the report surface."""
    timeline_assessment = _as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment"))
    temporal_entries = _as_list(timeline_assessment.get("temporal_correlation_analysis"))
    return {
        "version": str(timeline_assessment.get("version") or ""),
        "protected_activity_candidates": _dict_entries(_as_dict(retaliation_analysis).get("protected_activity_candidates"), 4),
        "adverse_action_candidates": _dict_entries(_as_dict(retaliation_analysis).get("adverse_action_candidates"), 4),
        "retaliation_points": _dict_entries(_as_dict(retaliation_analysis).get("retaliation_points"), 4),
        "protected_activity_timeline": _dict_entries(timeline_assessment.get("protected_activity_timeline"), 3),
        "adverse_action_timeline": _dict_entries(timeline_assessment.get("adverse_action_timeline"), 4),
        "temporal_correlation_analysis": _dict_entries(temporal_entries, 3),
        "strongest_retaliation_indicators": _dict_entries(timeline_assessment.get("strongest_retaliation_indicators"), 3),
        "strongest_non_retaliatory_explanations": _dict_entries(
            timeline_assessment.get("strongest_non_retaliatory_explanations"), 3
        ),
        "confounder_summary": _as_dict(_as_dict(temporal_entries[:1][0]).get("confounder_summary") if temporal_entries else {}),
        "overall_evidentiary_rating": dict(timeline_assessment.get("overall_evidentiary_rating") or {}),
    }


def missing_information_section(
    case_bundle: dict[str, Any],
    power_context: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    """Return a missing-information section."""
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
