"""Public investigation-report entrypoint with stable helper imports."""

from __future__ import annotations

from typing import Any

from .actor_witness_map import build_actor_witness_map
from .behavioral_interpretation_policy import interpretation_policy_payload
from .bilingual_workflows import attach_bilingual_rendering, build_bilingual_workflow
from .case_dashboard import build_case_dashboard
from .controlled_factual_drafting import build_controlled_factual_drafting
from .cross_output_consistency import build_cross_output_consistency
from .deadline_warnings import build_deadline_warnings
from .document_request_checklist import build_document_request_checklist
from .investigation_report_impl import (
    INVESTIGATION_REPORT_VERSION,
    SECTION_ORDER,
    _actor_and_witness_map_section,
    _as_dict,
    _as_list,
    _case_dashboard_section,
    _controlled_factual_drafting_section,
    _cross_output_consistency_section,
    _document_request_checklist_section,
    _employment_issue_frameworks_section,
    _evidence_table_section,
    _evidence_triage_section,
    _factual_summary_entry,
    _finding_entries,
    _language_section,
    _lawyer_briefing_memo_section,
    _lawyer_issue_matrix_section,
    _matter_evidence_index_section,
    _missing_information_section,
    _overall_assessment_section,
    _power_section,
    _promise_and_contradiction_analysis_section,
    _report_highlights,
    _report_master_chronology_payload,
    _report_retaliation_timeline_payload,
    _section_with_entries,
    _skeptical_employer_review_section,
    _timeline_section,
    _title,
    _witness_question_packs_section,
)
from .investigation_report_impl import (
    compact_investigation_report as _compact_investigation_report_impl,
)
from .lawyer_briefing_memo import build_lawyer_briefing_memo
from .lawyer_issue_matrix import build_lawyer_issue_matrix
from .master_chronology import build_master_chronology
from .matter_evidence_index import build_matter_evidence_index
from .matter_workspace import build_matter_workspace
from .promise_contradiction_analysis import build_promise_contradiction_analysis
from .skeptical_employer_review import build_skeptical_employer_review
from .witness_question_packs import build_witness_question_packs


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
    actor_identity_graph: dict[str, Any] | None = None,
    multi_source_case_bundle: dict[str, Any] | None = None,
    output_language: str = "en",
    translation_mode: str = "translation_aware",
) -> dict[str, Any] | None:
    """Render a structured investigation report from the current case-scoped payload."""
    if not isinstance(case_bundle, dict):
        return None
    findings = [finding for finding in _as_list(_as_dict(finding_evidence_index).get("findings")) if isinstance(finding, dict)]
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
    executive_entries = _finding_entries(executive_findings, max_items=3)
    if findings:
        executive_entries = [
            _factual_summary_entry(
                candidates=candidates,
                timeline=_as_dict(timeline),
                findings=findings,
            ),
            *executive_entries,
        ]
    missing_information_section = _missing_information_section(
        case_bundle,
        _as_dict(power_context),
        _as_dict(comparative_treatment),
    )
    master_chronology = build_master_chronology(
        case_bundle=case_bundle,
        timeline=_as_dict(timeline),
        multi_source_case_bundle=_as_dict(multi_source_case_bundle),
        finding_evidence_index=_as_dict(finding_evidence_index),
    )
    matter_evidence_index = build_matter_evidence_index(
        case_bundle=case_bundle,
        multi_source_case_bundle=_as_dict(multi_source_case_bundle),
        finding_evidence_index=_as_dict(finding_evidence_index),
        master_chronology=master_chronology,
    )
    bilingual_workflow = build_bilingual_workflow(
        case_bundle=case_bundle,
        multi_source_case_bundle=_as_dict(multi_source_case_bundle),
        output_language=output_language,
        translation_mode=translation_mode,
    )
    matter_workspace = build_matter_workspace(
        case_bundle=case_bundle,
        multi_source_case_bundle=_as_dict(multi_source_case_bundle),
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
    )
    actor_witness_map = build_actor_witness_map(
        case_bundle=case_bundle,
        actor_identity_graph=_as_dict(actor_identity_graph),
        communication_graph=_as_dict(communication_graph),
        master_chronology=master_chronology,
        matter_workspace=matter_workspace,
        multi_source_case_bundle=_as_dict(multi_source_case_bundle),
    )
    promise_contradiction_analysis = build_promise_contradiction_analysis(
        case_bundle=case_bundle,
        multi_source_case_bundle=_as_dict(multi_source_case_bundle),
        master_chronology=master_chronology,
    )
    chronology_section = _timeline_section(
        case_bundle,
        _as_dict(timeline),
        _as_dict(case_patterns),
    )
    if isinstance(master_chronology, dict):
        chronology_section["master_chronology"] = _report_master_chronology_payload(master_chronology)
    if isinstance(retaliation_analysis, dict):
        chronology_section["retaliation_timeline_assessment"] = _report_retaliation_timeline_payload(retaliation_analysis)
        retaliation_rating = _as_dict(
            _as_dict(retaliation_analysis.get("retaliation_timeline_assessment")).get("overall_evidentiary_rating")
        )
        if retaliation_rating:
            chronology_section["entries"] = [
                *chronology_section.get("entries", []),
                {
                    "entry_id": "timeline:retaliation_assessment",
                    "statement": (
                        "Retaliation timeline review is currently rated as "
                        f"{_title(str(retaliation_rating.get('rating') or 'insufficient_timing_record')).lower()}."
                    ),
                    "supporting_finding_ids": [],
                    "supporting_citation_ids": [],
                    "supporting_uids": [],
                },
            ][:8]
    overall_assessment_section = _overall_assessment_section(
        findings,
        case_bundle=case_bundle,
        comparative_treatment=_as_dict(comparative_treatment),
    )
    employment_issue_frameworks_section = _employment_issue_frameworks_section(
        case_bundle=case_bundle,
        findings=findings,
        comparative_treatment=_as_dict(comparative_treatment),
        overall_assessment=overall_assessment_section,
        missing_information_section=missing_information_section,
        matter_evidence_index=matter_evidence_index,
    )
    lawyer_issue_matrix = build_lawyer_issue_matrix(
        case_bundle=case_bundle,
        findings=findings,
        matter_evidence_index=matter_evidence_index,
        comparative_treatment=_as_dict(comparative_treatment),
        retaliation_timeline_assessment=_as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment")),
        employment_issue_frameworks=employment_issue_frameworks_section,
        master_chronology=master_chronology,
    )
    lawyer_issue_matrix = attach_bilingual_rendering(
        lawyer_issue_matrix,
        bilingual_workflow=bilingual_workflow,
        product_id="lawyer_issue_matrix",
        translated_summary_fields=["relevant_facts", "likely_opposing_argument", "missing_proof"],
        original_quote_fields=["rows[].strongest_documents[].quoted_evidence.original_text"],
    )
    skeptical_employer_review = build_skeptical_employer_review(
        findings=findings,
        master_chronology=master_chronology,
        matter_evidence_index=matter_evidence_index,
        comparative_treatment=_as_dict(comparative_treatment),
        lawyer_issue_matrix=lawyer_issue_matrix,
        overall_assessment=overall_assessment_section,
        retaliation_timeline_assessment=_as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment")),
    )
    document_request_checklist = build_document_request_checklist(
        matter_evidence_index=matter_evidence_index,
        skeptical_employer_review=skeptical_employer_review,
        missing_information_entries=[
            entry for entry in _as_list(missing_information_section.get("entries")) if isinstance(entry, dict)
        ],
    )
    deadline_warnings = build_deadline_warnings(
        case_bundle=case_bundle,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        document_request_checklist=document_request_checklist,
    )
    if isinstance(deadline_warnings, dict):
        warnings = [item for item in _as_list(deadline_warnings.get("warnings")) if isinstance(item, dict)]
        warnings_by_issue: dict[str, list[str]] = {}
        warnings_by_group: dict[str, list[str]] = {}
        for warning in warnings:
            warning_id = str(warning.get("warning_id") or "")
            if not warning_id:
                continue
            for issue_id in [str(item) for item in _as_list(warning.get("linked_issue_ids")) if item]:
                warnings_by_issue.setdefault(issue_id, []).append(warning_id)
            for group_id in [str(item) for item in _as_list(warning.get("linked_group_ids")) if item]:
                warnings_by_group.setdefault(group_id, []).append(warning_id)
        for row in [item for item in _as_list(_as_dict(lawyer_issue_matrix).get("rows")) if isinstance(item, dict)]:
            issue_id = str(row.get("issue_id") or "")
            row["timing_warning_ids"] = warnings_by_issue.get(issue_id, [])
        document_request_checklist["deadline_warnings"] = deadline_warnings
        for group in [item for item in _as_list(document_request_checklist.get("groups")) if isinstance(item, dict)]:
            group_id = str(group.get("group_id") or "")
            group["timing_warning_ids"] = warnings_by_group.get(group_id, [])
    witness_question_packs = build_witness_question_packs(
        actor_witness_map=actor_witness_map,
        master_chronology=master_chronology,
        matter_evidence_index=matter_evidence_index,
        document_request_checklist=document_request_checklist,
    )
    lawyer_briefing_memo = build_lawyer_briefing_memo(
        case_bundle=case_bundle,
        matter_workspace=matter_workspace,
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        retaliation_timeline_assessment=_as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment")),
        skeptical_employer_review=skeptical_employer_review,
        document_request_checklist=document_request_checklist,
        promise_contradiction_analysis=promise_contradiction_analysis,
    )
    lawyer_briefing_memo = attach_bilingual_rendering(
        lawyer_briefing_memo,
        bilingual_workflow=bilingual_workflow,
        product_id="lawyer_briefing_memo",
        translated_summary_fields=["sections.executive_summary[].text", "sections.key_facts[].text"],
        original_quote_fields=["sections.strongest_evidence[].quoted_evidence.original_text"],
    )
    controlled_factual_drafting = build_controlled_factual_drafting(
        case_bundle=case_bundle,
        findings=findings,
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        comparative_treatment=comparative_treatment,
        retaliation_timeline_assessment=_as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment")),
        skeptical_employer_review=skeptical_employer_review,
        document_request_checklist=document_request_checklist,
        promise_contradiction_analysis=promise_contradiction_analysis,
    )
    controlled_factual_drafting = attach_bilingual_rendering(
        controlled_factual_drafting,
        bilingual_workflow=bilingual_workflow,
        product_id="controlled_factual_drafting",
        translated_summary_fields=["framing_preflight.strongest_framing[].text", "controlled_draft.rendered_text"],
        original_quote_fields=["supporting evidence remains in matter_evidence_index rows"],
    )
    case_dashboard = build_case_dashboard(
        case_bundle=case_bundle,
        matter_workspace=matter_workspace,
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        actor_map=_as_dict(_as_dict(actor_witness_map).get("actor_map")),
        comparative_treatment=_as_dict(comparative_treatment),
        case_patterns=_as_dict(case_patterns),
        skeptical_employer_review=skeptical_employer_review,
        document_request_checklist=document_request_checklist,
        promise_contradiction_analysis=promise_contradiction_analysis,
        deadline_warnings=deadline_warnings,
    )
    case_dashboard = attach_bilingual_rendering(
        case_dashboard,
        bilingual_workflow=bilingual_workflow,
        product_id="case_dashboard",
        translated_summary_fields=["cards.main_claims_or_issues[].evidence_hint", "cards.strongest_exhibits[].summary"],
        original_quote_fields=["cards.strongest_exhibits[].quoted_evidence.original_text"],
    )
    cross_output_consistency = build_cross_output_consistency(
        master_chronology=master_chronology,
        matter_evidence_index=matter_evidence_index,
        lawyer_issue_matrix=lawyer_issue_matrix,
        lawyer_briefing_memo=lawyer_briefing_memo,
        case_dashboard=case_dashboard,
        skeptical_employer_review=skeptical_employer_review,
        controlled_factual_drafting=controlled_factual_drafting,
        retaliation_timeline_assessment=_as_dict(_as_dict(retaliation_analysis).get("retaliation_timeline_assessment")),
        actor_map=actor_witness_map.get("actor_map") if isinstance(actor_witness_map, dict) else None,
    )
    sections = {
        "executive_summary": _section_with_entries(
            section_id="executive_summary",
            title="Executive Summary",
            entries=executive_entries[:4],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough supported findings for an executive summary."
            ),
        ),
        "evidence_triage": _evidence_triage_section(
            findings,
            missing_information_section=missing_information_section,
        ),
        "chronological_pattern_analysis": chronology_section,
        "language_analysis": _language_section(candidates, _as_dict(case_patterns)),
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
        "matter_evidence_index": _matter_evidence_index_section(
            case_bundle=case_bundle,
            multi_source_case_bundle=_as_dict(multi_source_case_bundle),
            finding_evidence_index=_as_dict(finding_evidence_index),
            master_chronology=master_chronology,
        ),
        "employment_issue_frameworks": employment_issue_frameworks_section,
        "lawyer_issue_matrix": _lawyer_issue_matrix_section(
            lawyer_issue_matrix=lawyer_issue_matrix,
        ),
        "actor_and_witness_map": _actor_and_witness_map_section(
            actor_witness_map=actor_witness_map,
        ),
        "witness_question_packs": _witness_question_packs_section(
            witness_question_packs=witness_question_packs,
        ),
        "promise_and_contradiction_analysis": _promise_and_contradiction_analysis_section(
            promise_contradiction_analysis=promise_contradiction_analysis,
        ),
        "lawyer_briefing_memo": _lawyer_briefing_memo_section(
            lawyer_briefing_memo=lawyer_briefing_memo,
        ),
        "controlled_factual_drafting": _controlled_factual_drafting_section(
            controlled_factual_drafting=controlled_factual_drafting,
        ),
        "case_dashboard": _case_dashboard_section(
            case_dashboard=case_dashboard,
        ),
        "cross_output_consistency": _cross_output_consistency_section(
            cross_output_consistency=cross_output_consistency,
        ),
        "skeptical_employer_review": _skeptical_employer_review_section(skeptical_employer_review=skeptical_employer_review),
        "document_request_checklist": _document_request_checklist_section(document_request_checklist=document_request_checklist),
        "overall_assessment": overall_assessment_section,
        "missing_information": missing_information_section,
    }
    supported_section_count = sum(1 for section in sections.values() if section.get("status") == "supported")
    return {
        "version": INVESTIGATION_REPORT_VERSION,
        "report_format": "investigation_briefing",
        "interpretation_policy": interpretation_policy_payload(),
        "bilingual_workflow": bilingual_workflow,
        "section_order": SECTION_ORDER,
        "summary": {
            "section_count": len(SECTION_ORDER),
            "supported_section_count": supported_section_count,
            "insufficient_section_count": len(SECTION_ORDER) - supported_section_count,
        },
        "report_highlights": _report_highlights(findings),
        "deadline_warnings": deadline_warnings,
        "sections": sections,
    }


def compact_investigation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller BA16 report representation for tight response budgets."""
    return _compact_investigation_report_impl(report)
