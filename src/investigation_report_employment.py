"""Employment-issue and chronology helpers for investigation reports."""

from __future__ import annotations

from typing import Any

from .employment_issue_frameworks import ISSUE_TRACK_DEFINITIONS
from .investigation_report_assessment import NON_WEAK_STRENGTHS, scope_has_protected_context
from .investigation_report_findings import supporting_citation_ids, supporting_uids
from .investigation_report_sections import _as_dict, _as_list, _section_with_entries


def text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """Return whether any keyword occurs in normalized text."""
    normalized = " ".join(str(text or "").lower().split())
    return any(keyword in normalized for keyword in keywords)


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
    issue_tag_summary: dict[str, list[dict[str, str]]] = {
        "operator_supplied": [],
        "direct_document_content": [],
        "bounded_inference": [],
    }
    if isinstance(matter_evidence_index, dict):
        seen_by_basis: dict[str, set[str]] = {basis: set() for basis in issue_tag_summary}
        for row in _as_list(matter_evidence_index.get("rows")):
            if not isinstance(row, dict):
                continue
            for tag in _as_list(row.get("issue_tags")):
                if not isinstance(tag, dict):
                    continue
                basis = str(tag.get("assignment_basis") or "")
                tag_id = str(tag.get("tag_id") or "")
                if basis not in issue_tag_summary or not tag_id or tag_id in seen_by_basis[basis]:
                    continue
                seen_by_basis[basis].add(tag_id)
                issue_tag_summary[basis].append(
                    {
                        "tag_id": tag_id,
                        "label": str(tag.get("label") or ""),
                        "evidence_status": str(tag.get("evidence_status") or ""),
                    }
                )
    if not issue_tracks:
        section = _section_with_entries(
            section_id="employment_issue_frameworks",
            title="Employment Issue Frameworks",
            entries=[],
            insufficiency_reason="No employment issue tracks were selected for this case.",
        )
        section["issue_tag_summary"] = issue_tag_summary
        return section

    context_notes = str(scope.get("context_notes") or "")
    overall_primary = str(overall_assessment.get("primary_assessment") or "")
    overall_secondary = {str(item) for item in _as_list(overall_assessment.get("secondary_plausible_interpretations")) if item}
    finding_scopes = {str(finding.get("finding_scope") or "") for finding in findings}
    strong_or_moderate = any(
        str(_as_dict(finding.get("evidence_strength")).get("label") or "") in NON_WEAK_STRENGTHS for finding in findings
    )
    missing_statements = [
        str(entry.get("statement") or "")
        for entry in _as_list(missing_information_section.get("entries"))
        if isinstance(entry, dict)
    ]
    comparator_summaries = [
        summary for summary in _as_list(comparative_treatment.get("comparator_summaries")) if isinstance(summary, dict)
    ]

    issue_payloads: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    for issue_track in issue_tracks:
        definition = ISSUE_TRACK_DEFINITIONS.get(issue_track)
        if definition is None:
            continue

        status = "alleged_but_not_yet_evidenced"
        support_reason = "The current record does not yet contain enough issue-specific support."
        if issue_track == "disability_disadvantage":
            if scope_has_protected_context(case_bundle) and (
                overall_primary in {"discrimination_concern", "unequal_treatment_concern"}
                or any(bool(summary.get("supports_discrimination_concern")) for summary in comparator_summaries)
            ):
                status = "supported_by_current_record"
                support_reason = (
                    "Protected-context support and current unequal-treatment or discrimination indicators are both present."
                )
        elif issue_track == "retaliation_after_protected_event":
            if _as_list(scope.get("trigger_events")) and (
                "retaliation_analysis" in finding_scopes
                or overall_primary == "retaliation_concern"
                or "retaliation_concern" in overall_secondary
            ):
                status = "supported_by_current_record"
                support_reason = "A trigger event is present and the current record still supports retaliation-style review."
        elif issue_track == "eingruppierung_dispute":
            if text_contains_any(context_notes, ("eingruppierung", "entgeltgruppe", "vergütungsgruppe", "tarif", "td ")):
                if strong_or_moderate and (
                    "comparative_treatment" in finding_scopes
                    or "communication_graph" in finding_scopes
                    or int(_as_dict(comparative_treatment.get("summary")).get("available_comparator_count") or 0) > 0
                ):
                    status = "supported_by_current_record"
                    support_reason = (
                        "The intake names a classification dispute and the current record contains "
                        "non-trivial supporting evidence."
                    )
                else:
                    support_reason = (
                        "The intake names a classification dispute, but stronger role or HR-document support is still missing."
                    )
        elif issue_track == "prevention_duty_gap":
            if scope_has_protected_context(case_bundle) and text_contains_any(
                context_notes, ("bem", "prävention", "praevention", "sgb ix", "167", "workability")
            ):
                if strong_or_moderate:
                    status = "supported_by_current_record"
                    support_reason = "Health-context support and prevention-process cues are both visible in the current record."
                else:
                    support_reason = (
                        "A prevention-oriented concern is visible, but the current record is still too thin for stronger support."
                    )
        elif issue_track == "participation_duty_gap":
            if text_contains_any(
                context_notes,
                ("sbv", "schwerbehindertenvertretung", "personalrat", "betriebsrat", "mitbestimmung", "participation"),
            ):
                if strong_or_moderate or any("participation" in statement.lower() for statement in missing_statements):
                    status = "supported_by_current_record"
                    support_reason = (
                        "The intake names a participation path and the current record contains at least "
                        "some process support for that concern."
                    )
                else:
                    support_reason = (
                        "A participation issue is alleged, but the current record still lacks concrete consultation proof."
                    )

        why_not_yet_supported: list[str] = []
        if status != "supported_by_current_record":
            why_not_yet_supported = [statement for statement in missing_statements if statement not in why_not_yet_supported][:3]
            if not why_not_yet_supported:
                why_not_yet_supported = [support_reason]

        issue_payload = {
            "issue_track": issue_track,
            "title": str(definition.get("title") or issue_track),
            "neutral_question": str(definition.get("neutral_question") or ""),
            "status": status,
            "support_reason": support_reason,
            "required_proof_elements": list(definition.get("required_proof_elements") or []),
            "normal_alternative_explanations": list(definition.get("normal_alternative_explanations") or []),
            "missing_document_checklist": list(definition.get("missing_document_checklist") or []),
            "minimum_source_quality_expectations": list(definition.get("minimum_source_quality_expectations") or []),
            "why_not_yet_supported": why_not_yet_supported,
            "supporting_finding_ids": [str(finding.get("finding_id") or "") for finding in findings[:3]],
            "supporting_citation_ids": [
                citation_id for finding in findings[:2] for citation_id in supporting_citation_ids(finding, max_items=1)
            ][:3],
            "supporting_uids": [uid for finding in findings[:2] for uid in supporting_uids(finding, max_items=1)][:3],
        }
        issue_payloads.append(issue_payload)
        entries.append(
            {
                "entry_id": f"employment_issue:{issue_track}",
                "statement": (f"{issue_payload['title']} is currently marked as {status.replace('_', ' ')}. {support_reason}"),
                "supporting_finding_ids": issue_payload["supporting_finding_ids"],
                "supporting_citation_ids": issue_payload["supporting_citation_ids"],
                "supporting_uids": issue_payload["supporting_uids"],
            }
        )

    section = _section_with_entries(
        section_id="employment_issue_frameworks",
        title="Employment Issue Frameworks",
        entries=entries,
        insufficiency_reason="No employment issue tracks were selected for this case.",
    )
    section["issue_tracks"] = issue_payloads
    section["issue_tag_summary"] = issue_tag_summary
    return section


def report_master_chronology_payload(master_chronology: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact chronology payload for the report surface."""
    chronology = _as_dict(master_chronology)
    entries = [entry for entry in _as_list(chronology.get("entries")) if isinstance(entry, dict)]
    compact_entries = [
        {
            "chronology_id": str(entry.get("chronology_id") or ""),
            "date": str(entry.get("date") or ""),
            "date_precision": str(entry.get("date_precision") or ""),
            "entry_type": str(entry.get("entry_type") or ""),
            "title": str(entry.get("title") or ""),
            "event_support_matrix": {
                str(read_id): {
                    "status": str(_as_dict(read_payload).get("status") or ""),
                    "linked_issue_tags": [
                        str(item) for item in _as_list(_as_dict(read_payload).get("linked_issue_tags")) if item
                    ],
                    "selected_in_case_scope": bool(_as_dict(read_payload).get("selected_in_case_scope")),
                }
                for read_id, read_payload in _as_dict(entry.get("event_support_matrix")).items()
                if str(read_id).strip() and isinstance(read_payload, dict)
            },
            "source_linkage": {
                "source_ids": [str(item) for item in _as_list(_as_dict(entry.get("source_linkage")).get("source_ids")) if item],
                "source_types": [
                    str(item) for item in _as_list(_as_dict(entry.get("source_linkage")).get("source_types")) if item
                ],
                "supporting_uids": [
                    str(item) for item in _as_list(_as_dict(entry.get("source_linkage")).get("supporting_uids")) if item
                ],
                "supporting_citation_ids": [
                    str(item) for item in _as_list(_as_dict(entry.get("source_linkage")).get("supporting_citation_ids")) if item
                ],
            },
        }
        for entry in entries[:4]
    ]
    return {
        "version": str(chronology.get("version") or ""),
        "entry_count": int(chronology.get("entry_count") or len(entries)),
        "primary_entry_count": int(chronology.get("primary_entry_count") or 0),
        "scope_supplied_entry_count": int(chronology.get("scope_supplied_entry_count") or 0),
        "summary": dict(chronology.get("summary") or {}),
        "entries": compact_entries,
        "views": {
            view_id: {
                "view_id": str(_as_dict(view_payload).get("view_id") or view_id),
                "entry_count": int(_as_dict(view_payload).get("entry_count") or 0),
                "summary": dict(_as_dict(view_payload).get("summary") or {}),
            }
            for view_id, view_payload in _as_dict(chronology.get("views")).items()
            if str(view_id).strip()
        },
        "_truncated": max(0, len(entries) - len(compact_entries)),
    }


def report_retaliation_timeline_payload(retaliation_analysis: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact retaliation timeline assessment for the report surface."""
    timeline_assessment = _as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment"))
    temporal_entries = _as_list(timeline_assessment.get("temporal_correlation_analysis"))
    return {
        "version": str(timeline_assessment.get("version") or ""),
        "protected_activity_candidates": [
            dict(entry)
            for entry in _as_list(_as_dict(retaliation_analysis).get("protected_activity_candidates"))[:4]
            if isinstance(entry, dict)
        ],
        "adverse_action_candidates": [
            dict(entry)
            for entry in _as_list(_as_dict(retaliation_analysis).get("adverse_action_candidates"))[:4]
            if isinstance(entry, dict)
        ],
        "retaliation_points": [
            dict(entry)
            for entry in _as_list(_as_dict(retaliation_analysis).get("retaliation_points"))[:4]
            if isinstance(entry, dict)
        ],
        "protected_activity_timeline": [
            dict(entry)
            for entry in _as_list(timeline_assessment.get("protected_activity_timeline"))[:3]
            if isinstance(entry, dict)
        ],
        "adverse_action_timeline": [
            dict(entry) for entry in _as_list(timeline_assessment.get("adverse_action_timeline"))[:4] if isinstance(entry, dict)
        ],
        "temporal_correlation_analysis": [dict(entry) for entry in temporal_entries[:3] if isinstance(entry, dict)],
        "strongest_retaliation_indicators": [
            dict(entry)
            for entry in _as_list(timeline_assessment.get("strongest_retaliation_indicators"))[:3]
            if isinstance(entry, dict)
        ],
        "strongest_non_retaliatory_explanations": [
            dict(entry)
            for entry in _as_list(timeline_assessment.get("strongest_non_retaliatory_explanations"))[:3]
            if isinstance(entry, dict)
        ],
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
