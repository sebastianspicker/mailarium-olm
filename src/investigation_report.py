"""Public investigation-report entrypoint with stable helper imports."""
# pylint: disable=too-many-arguments,too-many-locals,too-many-statements

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class InvestigationReportRequest:
    case_bundle: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    timeline: dict[str, Any] | None
    power_context: dict[str, Any] | None
    case_patterns: dict[str, Any] | None
    retaliation_analysis: dict[str, Any] | None
    comparative_treatment: dict[str, Any] | None
    communication_graph: dict[str, Any] | None
    finding_evidence_index: dict[str, Any] | None
    evidence_table: dict[str, Any] | None
    actor_identity_graph: dict[str, Any] | None = None
    multi_source_case_bundle: dict[str, Any] | None = None
    output_language: str = "en"
    translation_mode: str = "translation_aware"


@dataclass
class _ReportBuildContext:
    request: InvestigationReportRequest
    findings: Any = None
    executive_findings: Any = None
    behaviour_findings: Any = None
    executive_entries: Any = None
    missing_information_section: Any = None
    master_chronology: Any = None
    matter_evidence_index: Any = None
    bilingual_workflow: Any = None
    matter_workspace: Any = None
    actor_witness_map: Any = None
    promise_contradiction_analysis: Any = None
    chronology_section: Any = None
    overall_assessment_section: Any = None
    employment_issue_frameworks_section: Any = None
    lawyer_issue_matrix: Any = None
    skeptical_employer_review: Any = None
    document_request_checklist: Any = None
    deadline_warnings: Any = None
    witness_question_packs: Any = None
    lawyer_briefing_memo: Any = None
    controlled_factual_drafting: Any = None
    case_dashboard: Any = None
    cross_output_consistency: Any = None
    sections: Any = None


_REQUIRED_REPORT_OPTIONS = {
    "case_bundle",
    "candidates",
    "timeline",
    "power_context",
    "case_patterns",
    "retaliation_analysis",
    "comparative_treatment",
    "communication_graph",
    "finding_evidence_index",
    "evidence_table",
}
_REPORT_OPTIONS = set(InvestigationReportRequest.__dataclass_fields__)


def _coerce_report_request(
    request: InvestigationReportRequest | None,
    legacy_options: dict[str, Any],
) -> InvestigationReportRequest:
    if request is not None:
        if legacy_options:
            duplicate = sorted(legacy_options)[0]
            raise TypeError(f"duplicate investigation report option: {duplicate}")
        if not isinstance(request, InvestigationReportRequest):
            raise TypeError("request must be an InvestigationReportRequest")
        return request
    unknown = sorted(set(legacy_options) - _REPORT_OPTIONS)
    if unknown:
        raise TypeError(f"unknown investigation report option: {unknown[0]}")
    missing = sorted(_REQUIRED_REPORT_OPTIONS - set(legacy_options))
    if missing:
        raise TypeError(f"missing required investigation report option: {missing[0]}")
    return InvestigationReportRequest(**legacy_options)


def _dict_findings(value: Any) -> list[dict[str, Any]]:
    return [finding for finding in _as_list(value) if isinstance(finding, dict)]


def _scope_findings(findings: list[dict[str, Any]], scopes: set[str]) -> list[dict[str, Any]]:
    return [finding for finding in findings if str(finding.get("finding_scope") or "") in scopes]


def _executive_entries(ctx: _ReportBuildContext) -> list[dict[str, Any]]:
    entries = _finding_entries(ctx.executive_findings, max_items=3)
    if not ctx.findings:
        return entries
    factual = _factual_summary_entry(
        candidates=ctx.request.candidates,
        timeline=_as_dict(ctx.request.timeline),
        findings=ctx.findings,
    )
    return [factual, *entries]


def _build_evidence_foundations(ctx: _ReportBuildContext) -> None:
    ctx.findings = _dict_findings(_as_dict(ctx.request.finding_evidence_index).get("findings"))
    ctx.executive_findings = _scope_findings(
        ctx.findings,
        {"message_behavior", "case_pattern", "retaliation_analysis", "comparative_treatment", "communication_graph"},
    )
    ctx.behaviour_findings = _scope_findings(
        ctx.findings,
        {"message_behavior", "quoted_message_behavior", "case_pattern", "comparative_treatment", "communication_graph"},
    )
    ctx.executive_entries = _executive_entries(ctx)
    ctx.missing_information_section = _missing_information_section(
        _as_dict(ctx.request.case_bundle),
        _as_dict(ctx.request.power_context),
        _as_dict(ctx.request.comparative_treatment),
    )
    ctx.master_chronology = build_master_chronology(
        case_bundle=ctx.request.case_bundle,
        timeline=_as_dict(ctx.request.timeline),
        multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
        finding_evidence_index=_as_dict(ctx.request.finding_evidence_index),
    )
    ctx.matter_evidence_index = build_matter_evidence_index(
        case_bundle=ctx.request.case_bundle,
        multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
        finding_evidence_index=_as_dict(ctx.request.finding_evidence_index),
        master_chronology=ctx.master_chronology,
    )
    ctx.bilingual_workflow = build_bilingual_workflow(
        case_bundle=ctx.request.case_bundle,
        multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
        output_language=ctx.request.output_language,
        translation_mode=ctx.request.translation_mode,
    )


def _build_workspace_foundations(ctx: _ReportBuildContext) -> None:
    ctx.matter_workspace = build_matter_workspace(
        case_bundle=ctx.request.case_bundle,
        multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
        matter_evidence_index=ctx.matter_evidence_index,
        master_chronology=ctx.master_chronology,
    )
    ctx.actor_witness_map = build_actor_witness_map(
        case_bundle=ctx.request.case_bundle,
        actor_identity_graph=_as_dict(ctx.request.actor_identity_graph),
        communication_graph=_as_dict(ctx.request.communication_graph),
        master_chronology=ctx.master_chronology,
        matter_workspace=ctx.matter_workspace,
        multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
    )
    ctx.promise_contradiction_analysis = build_promise_contradiction_analysis(
        case_bundle=ctx.request.case_bundle,
        multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
        master_chronology=ctx.master_chronology,
    )


def _build_chronology(ctx: _ReportBuildContext) -> None:
    ctx.chronology_section = _timeline_section(
        _as_dict(ctx.request.case_bundle),
        _as_dict(ctx.request.timeline),
        _as_dict(ctx.request.case_patterns),
    )
    if isinstance(ctx.master_chronology, dict):
        ctx.chronology_section["master_chronology"] = _report_master_chronology_payload(ctx.master_chronology)
    if isinstance(ctx.request.retaliation_analysis, dict):
        ctx.chronology_section["retaliation_timeline_assessment"] = _report_retaliation_timeline_payload(
            ctx.request.retaliation_analysis
        )
        retaliation_rating = _as_dict(
            _as_dict(ctx.request.retaliation_analysis.get("retaliation_timeline_assessment")).get("overall_evidentiary_rating")
        )
        if retaliation_rating:
            ctx.chronology_section["entries"] = [
                *ctx.chronology_section.get("entries", []),
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


def _build_legal_assessments(ctx: _ReportBuildContext) -> None:
    ctx.overall_assessment_section = _overall_assessment_section(
        ctx.findings,
        case_bundle=_as_dict(ctx.request.case_bundle),
        comparative_treatment=_as_dict(ctx.request.comparative_treatment),
    )
    ctx.employment_issue_frameworks_section = _employment_issue_frameworks_section(
        case_bundle=_as_dict(ctx.request.case_bundle),
        findings=ctx.findings,
        comparative_treatment=_as_dict(ctx.request.comparative_treatment),
        overall_assessment=ctx.overall_assessment_section,
        missing_information_section=ctx.missing_information_section,
        matter_evidence_index=ctx.matter_evidence_index,
    )
    ctx.lawyer_issue_matrix = build_lawyer_issue_matrix(
        case_bundle=ctx.request.case_bundle,
        findings=ctx.findings,
        matter_evidence_index=ctx.matter_evidence_index,
        comparative_treatment=_as_dict(ctx.request.comparative_treatment),
        retaliation_timeline_assessment=_as_dict(
            _as_dict(ctx.request.retaliation_analysis).get("retaliation_timeline_assessment")
        ),
        employment_issue_frameworks=ctx.employment_issue_frameworks_section,
        master_chronology=ctx.master_chronology,
    )
    ctx.lawyer_issue_matrix = attach_bilingual_rendering(
        ctx.lawyer_issue_matrix,
        bilingual_workflow=ctx.bilingual_workflow,
        product_id="lawyer_issue_matrix",
        translated_summary_fields=["relevant_facts", "likely_opposing_argument", "missing_proof"],
        original_quote_fields=["rows[].strongest_documents[].quoted_evidence.original_text"],
    )
    ctx.skeptical_employer_review = build_skeptical_employer_review(
        findings=ctx.findings,
        master_chronology=ctx.master_chronology,
        matter_evidence_index=ctx.matter_evidence_index,
        comparative_treatment=_as_dict(ctx.request.comparative_treatment),
        lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        overall_assessment=ctx.overall_assessment_section,
        retaliation_timeline_assessment=_as_dict(
            _as_dict(ctx.request.retaliation_analysis).get("retaliation_timeline_assessment")
        ),
    )


def _append_warning_links(index: dict[str, list[str]], values: Any, warning_id: str) -> None:
    for value in _as_list(values):
        if value:
            index.setdefault(str(value), []).append(warning_id)


def _warning_links(warnings: Any) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    by_issue: dict[str, list[str]] = {}
    by_group: dict[str, list[str]] = {}
    for warning in _dict_findings(warnings):
        warning_id = str(warning.get("warning_id") or "")
        if not warning_id:
            continue
        _append_warning_links(by_issue, warning.get("linked_issue_ids"), warning_id)
        _append_warning_links(by_group, warning.get("linked_group_ids"), warning_id)
    return by_issue, by_group


def _attach_deadline_warnings(ctx: _ReportBuildContext) -> None:
    if not isinstance(ctx.deadline_warnings, dict):
        return
    warnings_by_issue, warnings_by_group = _warning_links(ctx.deadline_warnings.get("warnings"))
    for row in _dict_findings(_as_dict(ctx.lawyer_issue_matrix).get("rows")):
        row["timing_warning_ids"] = warnings_by_issue.get(str(row.get("issue_id") or ""), [])
    ctx.document_request_checklist["deadline_warnings"] = ctx.deadline_warnings
    for group in _dict_findings(ctx.document_request_checklist.get("groups")):
        group["timing_warning_ids"] = warnings_by_group.get(str(group.get("group_id") or ""), [])


def _build_deadline_outputs(ctx: _ReportBuildContext) -> None:
    ctx.document_request_checklist = build_document_request_checklist(
        matter_evidence_index=ctx.matter_evidence_index,
        skeptical_employer_review=ctx.skeptical_employer_review,
        missing_information_entries=_dict_findings(ctx.missing_information_section.get("entries")),
    )
    ctx.deadline_warnings = build_deadline_warnings(
        case_bundle=ctx.request.case_bundle,
        master_chronology=ctx.master_chronology,
        lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        document_request_checklist=ctx.document_request_checklist,
    )
    _attach_deadline_warnings(ctx)


def _build_witness_and_memo(ctx: _ReportBuildContext) -> None:
    ctx.witness_question_packs = build_witness_question_packs(
        actor_witness_map=ctx.actor_witness_map,
        master_chronology=ctx.master_chronology,
        matter_evidence_index=ctx.matter_evidence_index,
        document_request_checklist=ctx.document_request_checklist,
    )
    ctx.lawyer_briefing_memo = build_lawyer_briefing_memo(
        case_bundle=ctx.request.case_bundle,
        matter_workspace=ctx.matter_workspace,
        matter_evidence_index=ctx.matter_evidence_index,
        master_chronology=ctx.master_chronology,
        lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        retaliation_timeline_assessment=_as_dict(
            _as_dict(ctx.request.retaliation_analysis).get("retaliation_timeline_assessment")
        ),
        skeptical_employer_review=ctx.skeptical_employer_review,
        document_request_checklist=ctx.document_request_checklist,
        promise_contradiction_analysis=ctx.promise_contradiction_analysis,
    )
    ctx.lawyer_briefing_memo = attach_bilingual_rendering(
        ctx.lawyer_briefing_memo,
        bilingual_workflow=ctx.bilingual_workflow,
        product_id="lawyer_briefing_memo",
        translated_summary_fields=["sections.executive_summary[].text", "sections.key_facts[].text"],
        original_quote_fields=["sections.strongest_evidence[].quoted_evidence.original_text"],
    )


def _build_controlled_drafting(ctx: _ReportBuildContext) -> None:
    ctx.controlled_factual_drafting = build_controlled_factual_drafting(
        case_bundle=ctx.request.case_bundle,
        findings=ctx.findings,
        matter_evidence_index=ctx.matter_evidence_index,
        master_chronology=ctx.master_chronology,
        lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        comparative_treatment=ctx.request.comparative_treatment,
        retaliation_timeline_assessment=_as_dict(
            _as_dict(ctx.request.retaliation_analysis).get("retaliation_timeline_assessment")
        ),
        skeptical_employer_review=ctx.skeptical_employer_review,
        document_request_checklist=ctx.document_request_checklist,
        promise_contradiction_analysis=ctx.promise_contradiction_analysis,
    )
    ctx.controlled_factual_drafting = attach_bilingual_rendering(
        ctx.controlled_factual_drafting,
        bilingual_workflow=ctx.bilingual_workflow,
        product_id="controlled_factual_drafting",
        translated_summary_fields=["framing_preflight.strongest_framing[].text", "controlled_draft.rendered_text"],
        original_quote_fields=["supporting evidence remains in matter_evidence_index rows"],
    )


def _build_dashboard_outputs(ctx: _ReportBuildContext) -> None:
    ctx.case_dashboard = build_case_dashboard(
        case_bundle=ctx.request.case_bundle,
        matter_workspace=ctx.matter_workspace,
        matter_evidence_index=ctx.matter_evidence_index,
        master_chronology=ctx.master_chronology,
        lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        actor_map=_as_dict(_as_dict(ctx.actor_witness_map).get("actor_map")),
        comparative_treatment=_as_dict(ctx.request.comparative_treatment),
        case_patterns=_as_dict(ctx.request.case_patterns),
        skeptical_employer_review=ctx.skeptical_employer_review,
        document_request_checklist=ctx.document_request_checklist,
        promise_contradiction_analysis=ctx.promise_contradiction_analysis,
        deadline_warnings=ctx.deadline_warnings,
    )
    ctx.case_dashboard = attach_bilingual_rendering(
        ctx.case_dashboard,
        bilingual_workflow=ctx.bilingual_workflow,
        product_id="case_dashboard",
        translated_summary_fields=["cards.main_claims_or_issues[].evidence_hint", "cards.strongest_exhibits[].summary"],
        original_quote_fields=["cards.strongest_exhibits[].quoted_evidence.original_text"],
    )
    ctx.cross_output_consistency = build_cross_output_consistency(
        master_chronology=ctx.master_chronology,
        matter_evidence_index=ctx.matter_evidence_index,
        lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        lawyer_briefing_memo=ctx.lawyer_briefing_memo,
        case_dashboard=ctx.case_dashboard,
        skeptical_employer_review=ctx.skeptical_employer_review,
        controlled_factual_drafting=ctx.controlled_factual_drafting,
        retaliation_timeline_assessment=_as_dict(
            _as_dict(ctx.request.retaliation_analysis).get("retaliation_timeline_assessment")
        ),
        actor_map=ctx.actor_witness_map.get("actor_map") if isinstance(ctx.actor_witness_map, dict) else None,
    )


def _core_report_sections(ctx: _ReportBuildContext) -> dict[str, Any]:
    return {
        "executive_summary": _section_with_entries(
            section_id="executive_summary",
            title="Executive Summary",
            entries=ctx.executive_entries[:4],
            insufficiency_reason=(
                "The current case bundle does not yet contain enough supported findings for an executive summary."
            ),
        ),
        "evidence_triage": _evidence_triage_section(
            ctx.findings,
            missing_information_section=ctx.missing_information_section,
        ),
        "chronological_pattern_analysis": ctx.chronology_section,
        "language_analysis": _language_section(ctx.request.candidates, _as_dict(ctx.request.case_patterns)),
        "behaviour_analysis": _section_with_entries(
            section_id="behaviour_analysis",
            title="Behaviour Analysis",
            entries=_finding_entries(ctx.behaviour_findings, max_items=4),
            insufficiency_reason="The current case bundle does not yet contain enough supported behaviour findings.",
        ),
        "power_context_analysis": _power_section(
            _as_dict(ctx.request.power_context),
            _as_dict(ctx.request.communication_graph),
            _as_dict(ctx.request.comparative_treatment),
        ),
        "evidence_table": _evidence_table_section(_as_dict(ctx.request.evidence_table)),
        "matter_evidence_index": _matter_evidence_index_section(
            case_bundle=_as_dict(ctx.request.case_bundle),
            multi_source_case_bundle=_as_dict(ctx.request.multi_source_case_bundle),
            finding_evidence_index=_as_dict(ctx.request.finding_evidence_index),
            master_chronology=ctx.master_chronology,
        ),
    }


def _product_report_sections(ctx: _ReportBuildContext) -> dict[str, Any]:
    return {
        "employment_issue_frameworks": ctx.employment_issue_frameworks_section,
        "lawyer_issue_matrix": _lawyer_issue_matrix_section(
            lawyer_issue_matrix=ctx.lawyer_issue_matrix,
        ),
        "actor_and_witness_map": _actor_and_witness_map_section(
            actor_witness_map=ctx.actor_witness_map,
        ),
        "witness_question_packs": _witness_question_packs_section(
            witness_question_packs=ctx.witness_question_packs,
        ),
        "promise_and_contradiction_analysis": _promise_and_contradiction_analysis_section(
            promise_contradiction_analysis=ctx.promise_contradiction_analysis,
        ),
        "lawyer_briefing_memo": _lawyer_briefing_memo_section(
            lawyer_briefing_memo=ctx.lawyer_briefing_memo,
        ),
        "controlled_factual_drafting": _controlled_factual_drafting_section(
            controlled_factual_drafting=ctx.controlled_factual_drafting,
        ),
        "case_dashboard": _case_dashboard_section(
            case_dashboard=ctx.case_dashboard,
        ),
        "cross_output_consistency": _cross_output_consistency_section(
            cross_output_consistency=ctx.cross_output_consistency,
        ),
        "skeptical_employer_review": _skeptical_employer_review_section(skeptical_employer_review=ctx.skeptical_employer_review),
        "document_request_checklist": _document_request_checklist_section(
            document_request_checklist=ctx.document_request_checklist
        ),
        "overall_assessment": ctx.overall_assessment_section,
        "missing_information": ctx.missing_information_section,
    }


def _render_report(ctx: _ReportBuildContext) -> dict[str, Any]:
    ctx.sections = {**_core_report_sections(ctx), **_product_report_sections(ctx)}
    supported_section_count = sum(1 for section in ctx.sections.values() if section.get("status") == "supported")
    return {
        "version": INVESTIGATION_REPORT_VERSION,
        "report_format": "investigation_briefing",
        "interpretation_policy": interpretation_policy_payload(),
        "bilingual_workflow": ctx.bilingual_workflow,
        "section_order": SECTION_ORDER,
        "summary": {
            "section_count": len(SECTION_ORDER),
            "supported_section_count": supported_section_count,
            "insufficient_section_count": len(SECTION_ORDER) - supported_section_count,
        },
        "report_highlights": _report_highlights(ctx.findings),
        "deadline_warnings": ctx.deadline_warnings,
        "sections": ctx.sections,
    }


def build_investigation_report(
    request: InvestigationReportRequest | None = None,
    **legacy_options: Any,
) -> dict[str, Any] | None:
    """Render a structured investigation report from the current case-scoped payload."""
    resolved = _coerce_report_request(request, legacy_options)
    if not isinstance(resolved.case_bundle, dict):
        return None
    context = _ReportBuildContext(request=resolved)
    _build_evidence_foundations(context)
    _build_workspace_foundations(context)
    _build_chronology(context)
    _build_legal_assessments(context)
    _build_deadline_outputs(context)
    _build_witness_and_memo(context)
    _build_controlled_drafting(context)
    _build_dashboard_outputs(context)
    return _render_report(context)


def compact_investigation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller BA16 report representation for tight response budgets."""
    return _compact_investigation_report_impl(report)
