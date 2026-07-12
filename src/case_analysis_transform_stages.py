"""Typed stages for the case-analysis output transformation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .actor_witness_map import build_actor_witness_map
from .bilingual_workflows import attach_bilingual_rendering, build_bilingual_workflow
from .case_analysis_appendix import build_message_appendix
from .case_analysis_common import CASE_ANALYSIS_VERSION, as_dict
from .case_analysis_coverage import matter_coverage_ledger
from .case_analysis_scope import (
    analysis_limits,
    case_scope_quality,
    derive_case_analysis_query,
    inject_scope_warnings_into_report,
    review_classification,
)
from .case_dashboard import build_case_dashboard
from .controlled_factual_drafting import build_controlled_factual_drafting
from .cross_output_consistency import build_cross_output_consistency
from .deadline_warnings import build_deadline_warnings
from .document_request_checklist import build_document_request_checklist
from .investigation_report import build_investigation_report
from .lawyer_briefing_memo import build_lawyer_briefing_memo
from .lawyer_issue_matrix import build_lawyer_issue_matrix
from .master_chronology import build_master_chronology
from .matter_evidence_index import build_matter_evidence_index
from .matter_workspace import build_matter_workspace
from .mcp_models import EmailCaseAnalysisInput
from .promise_contradiction_analysis import build_promise_contradiction_analysis
from .sanitization import apply_privacy_guardrails
from .skeptical_employer_review import build_skeptical_employer_review
from .wave_local_views import build_wave_local_views
from .witness_question_packs import build_witness_question_packs


@dataclass(slots=True)
class TransformContext:
    answer: dict[str, Any]
    params: EmailCaseAnalysisInput
    values: dict[str, Any] = field(default_factory=dict)


def transform_payload(answer: dict[str, Any], params: EmailCaseAnalysisInput) -> dict[str, Any]:
    context = TransformContext(answer, params)
    _build_foundations(context)
    _build_legal_surfaces(context)
    _build_matter_surfaces(context)
    _build_consistency(context)
    transformed = _full_payload(context)
    _add_limits_and_wave_views(context, transformed)
    final_payload = _report_only_payload(context, transformed) if params.output_mode == "report_only" else transformed
    return _apply_privacy(context, final_payload)


def _build_foundations(context: TransformContext) -> None:
    answer, params, values = context.answer, context.params, context.values
    values["scope_quality"] = case_scope_quality(params)
    values["message_appendix"] = build_message_appendix(answer, include_message_appendix=params.include_message_appendix)
    values["finding_evidence_index"], values["evidence_table"], values["message_appendix"] = _compact_evidence(
        answer, params, values["message_appendix"]
    )
    values["master_chronology"] = build_master_chronology(
        case_bundle=answer.get("case_bundle"),
        timeline=answer.get("timeline"),
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
        finding_evidence_index=answer.get("finding_evidence_index"),
    )
    values["matter_evidence_index"] = build_matter_evidence_index(
        case_bundle=answer.get("case_bundle"),
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
        finding_evidence_index=answer.get("finding_evidence_index"),
        master_chronology=values["master_chronology"],
    )
    values["bilingual_workflow"] = build_bilingual_workflow(
        case_bundle=answer.get("case_bundle"),
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
        output_language=params.output_language,
        translation_mode=params.translation_mode,
    )
    generated = _generated_report(context)
    values["investigation_report"] = inject_scope_warnings_into_report(
        generated or answer.get("investigation_report"), values["scope_quality"]
    )
    values["preliminary_limits"] = analysis_limits(
        params,
        answer,
        values["scope_quality"],
        final_payload={
            "case_patterns": answer.get("case_patterns"),
            "finding_evidence_index": values["finding_evidence_index"],
            "investigation_report": values["investigation_report"],
            "message_appendix": values["message_appendix"],
        },
    )
    values["retaliation_timeline_assessment"] = _retaliation_timeline(answer)
    values["finding_rows"] = _finding_rows(answer)


def _compact_evidence(
    answer: dict[str, Any], params: EmailCaseAnalysisInput, appendix: dict[str, Any]
) -> tuple[Any, Any, dict[str, Any]]:
    findings, table = answer.get("finding_evidence_index"), answer.get("evidence_table")
    if not params.compact_case_evidence:
        return findings, table, appendix
    finding_rows = _finding_rows(answer)
    findings = {
        "summary": {
            "finding_count": len(finding_rows),
            "finding_ids": [str(row.get("finding_id") or "") for row in finding_rows[:3]],
        }
    }
    table = {"summary": {"row_count": int(as_dict(table).get("row_count") or 0)}}
    if appendix.get("included"):
        rows = [row for row in appendix.get("rows", []) if isinstance(row, dict)]
        shown = rows[:5]
        appendix = {
            "included": True,
            "row_count": len(rows),
            "shown_row_count": len(shown),
            "rows": shown,
            "_truncated": len(rows) - len(shown),
        }
    return findings, table, appendix


def _generated_report(context: TransformContext) -> dict[str, Any] | None:
    answer, params = context.answer, context.params
    bundle = as_dict(answer.get("multi_source_case_bundle"))
    if not isinstance(answer.get("multi_source_case_bundle"), dict) or not bundle.get("sources"):
        return None
    return build_investigation_report(
        case_bundle=answer.get("case_bundle"),
        candidates=[item for item in answer.get("candidates", []) if isinstance(item, dict)]
        if isinstance(answer.get("candidates"), list)
        else [],
        timeline=answer.get("timeline"),
        power_context=answer.get("power_context"),
        case_patterns=answer.get("case_patterns"),
        retaliation_analysis=answer.get("retaliation_analysis"),
        comparative_treatment=answer.get("comparative_treatment"),
        communication_graph=answer.get("communication_graph"),
        actor_identity_graph=answer.get("actor_identity_graph"),
        finding_evidence_index=answer.get("finding_evidence_index"),
        evidence_table=answer.get("evidence_table"),
        multi_source_case_bundle=bundle,
        output_language=params.output_language,
        translation_mode=params.translation_mode,
    )


def _finding_rows(answer: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in as_dict(answer.get("finding_evidence_index")).get("findings", []) if isinstance(row, dict)]


def _retaliation_timeline(answer: dict[str, Any]) -> dict[str, Any] | None:
    analysis = as_dict(answer.get("retaliation_analysis"))
    timeline = dict(analysis.get("retaliation_timeline_assessment") or {}) if analysis else None
    if not isinstance(timeline, dict) or not analysis:
        return timeline
    timeline.update(
        {
            "anchor_requirement_status": str(analysis.get("anchor_requirement_status") or ""),
            "protected_activity_candidate_count": int(analysis.get("protected_activity_candidate_count") or 0),
            "adverse_action_candidate_count": int(analysis.get("adverse_action_candidate_count") or 0),
            "source_backed_candidate_counts": dict(analysis.get("source_backed_candidate_counts") or {}),
        }
    )
    if not timeline.get("insufficiency_reason"):
        timeline["insufficiency_reason"] = _retaliation_insufficiency(timeline)
    return timeline


def _retaliation_insufficiency(timeline: dict[str, Any]) -> str:
    if str(timeline.get("anchor_requirement_status") or "") == "explicit_trigger_confirmation_required":
        return "No explicit confirmed trigger event is available yet for a stronger before/after retaliation analysis."
    if not list(timeline.get("protected_activity_timeline") or []) and not list(timeline.get("adverse_action_timeline") or []):
        return (
            "The current record does not yet contain enough protected-activity and adverse-action timeline detail "
            "for a fuller retaliation assessment."
        )
    return ""


def _build_legal_surfaces(context: TransformContext) -> None:
    answer, params, values = context.answer, context.params, context.values
    report = values["investigation_report"]
    sections = as_dict(as_dict(report).get("sections"))
    matrix = build_lawyer_issue_matrix(
        case_bundle=answer.get("case_bundle"),
        findings=values["finding_rows"],
        matter_evidence_index=values["matter_evidence_index"],
        comparative_treatment=answer.get("comparative_treatment"),
        retaliation_timeline_assessment=values["retaliation_timeline_assessment"],
        employment_issue_frameworks=sections.get("employment_issue_frameworks"),
        master_chronology=values["master_chronology"],
        case_scope_quality=values["scope_quality"],
        analysis_limits=values["preliminary_limits"],
        include_full_issue_set=params.review_mode == "exhaustive_matter_review",
    )
    values["lawyer_issue_matrix"] = attach_bilingual_rendering(
        matrix,
        bilingual_workflow=values["bilingual_workflow"],
        product_id="lawyer_issue_matrix",
        translated_summary_fields=["relevant_facts", "likely_opposing_argument", "missing_proof"],
        original_quote_fields=["rows[].strongest_documents[].quoted_evidence.original_text"],
    )
    values["skeptical_employer_review"] = build_skeptical_employer_review(
        findings=values["finding_rows"],
        master_chronology=values["master_chronology"],
        matter_evidence_index=values["matter_evidence_index"],
        comparative_treatment=answer.get("comparative_treatment"),
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        overall_assessment=sections.get("overall_assessment"),
        retaliation_timeline_assessment=values["retaliation_timeline_assessment"],
        case_scope_quality=values["scope_quality"],
        analysis_limits=values["preliminary_limits"],
    )
    missing = [entry for entry in as_dict(sections.get("missing_information")).get("entries", []) if isinstance(entry, dict)]
    values["document_request_checklist"] = build_document_request_checklist(
        matter_evidence_index=values["matter_evidence_index"],
        skeptical_employer_review=values["skeptical_employer_review"],
        missing_information_entries=missing,
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        case_scope_quality=values["scope_quality"],
        analysis_limits=values["preliminary_limits"],
    )
    values["deadline_warnings"] = build_deadline_warnings(
        case_bundle=answer.get("case_bundle"),
        master_chronology=values["master_chronology"],
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        document_request_checklist=values["document_request_checklist"],
    )
    _attach_deadline_warnings(values)


def _attach_deadline_warnings(values: dict[str, Any]) -> None:
    deadline = values.get("deadline_warnings")
    if not isinstance(deadline, dict):
        return
    by_issue, by_group = _warning_links(deadline)
    matrix = values.get("lawyer_issue_matrix")
    if isinstance(matrix, dict):
        for row in [item for item in matrix.get("rows", []) if isinstance(item, dict)]:
            row["timing_warning_ids"] = by_issue.get(str(row.get("issue_id") or ""), [])
    checklist = values.get("document_request_checklist")
    if isinstance(checklist, dict):
        checklist["deadline_warnings"] = deadline
        for group in [item for item in checklist.get("groups", []) if isinstance(item, dict)]:
            group["timing_warning_ids"] = by_group.get(str(group.get("group_id") or ""), [])


def _warning_links(deadline: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    by_issue: dict[str, list[str]] = {}
    by_group: dict[str, list[str]] = {}
    for warning in [item for item in deadline.get("warnings", []) if isinstance(item, dict)]:
        warning_id = str(warning.get("warning_id") or "")
        if not warning_id:
            continue
        for issue_id in [str(item) for item in warning.get("linked_issue_ids", []) if item]:
            by_issue.setdefault(issue_id, []).append(warning_id)
        for group_id in [str(item) for item in warning.get("linked_group_ids", []) if item]:
            by_group.setdefault(group_id, []).append(warning_id)
    return by_issue, by_group


def _build_matter_surfaces(context: TransformContext) -> None:
    answer, values = context.answer, context.values
    chronology, evidence = values["master_chronology"], values["matter_evidence_index"]
    values["matter_workspace"] = build_matter_workspace(
        case_bundle=answer.get("case_bundle"),
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
        matter_evidence_index=evidence,
        master_chronology=chronology,
    )
    actor_witness = build_actor_witness_map(
        case_bundle=answer.get("case_bundle"),
        actor_identity_graph=answer.get("actor_identity_graph"),
        communication_graph=answer.get("communication_graph"),
        master_chronology=chronology,
        matter_workspace=values["matter_workspace"],
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
    )
    values["actor_map"] = actor_witness.get("actor_map") if isinstance(actor_witness, dict) else None
    values["witness_map"] = actor_witness.get("witness_map") if isinstance(actor_witness, dict) else None
    values["promise_contradiction_analysis"] = build_promise_contradiction_analysis(
        case_bundle=answer.get("case_bundle"),
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
        master_chronology=chronology,
    )
    values["witness_question_packs"] = build_witness_question_packs(
        actor_witness_map=actor_witness,
        master_chronology=chronology,
        matter_evidence_index=evidence,
        document_request_checklist=values["document_request_checklist"],
    )
    _build_drafting_products(context)
    values["case_dashboard"] = _case_dashboard(context)
    values["coverage_ledger"] = matter_coverage_ledger(
        params=context.params,
        multi_source_case_bundle=answer.get("multi_source_case_bundle"),
        matter_evidence_index=evidence,
        master_chronology=chronology,
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        message_appendix=values["message_appendix"],
    )


def _build_drafting_products(context: TransformContext) -> None:
    answer, values = context.answer, context.values
    common = {
        key: values[key]
        for key in (
            "matter_evidence_index",
            "master_chronology",
            "lawyer_issue_matrix",
            "skeptical_employer_review",
            "document_request_checklist",
            "promise_contradiction_analysis",
        )
    }
    memo = build_lawyer_briefing_memo(
        case_bundle=answer.get("case_bundle"),
        matter_workspace=values["matter_workspace"],
        retaliation_timeline_assessment=values["retaliation_timeline_assessment"],
        **common,
    )
    values["lawyer_briefing_memo"] = attach_bilingual_rendering(
        memo,
        bilingual_workflow=values["bilingual_workflow"],
        product_id="lawyer_briefing_memo",
        translated_summary_fields=["sections.executive_summary[].text", "sections.key_facts[].text"],
        original_quote_fields=["sections.strongest_evidence[].quoted_evidence.original_text"],
    )
    draft = build_controlled_factual_drafting(
        case_bundle=answer.get("case_bundle"),
        findings=values["finding_rows"],
        matter_evidence_index=values["matter_evidence_index"],
        master_chronology=values["master_chronology"],
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        comparative_treatment=answer.get("comparative_treatment"),
        retaliation_timeline_assessment=values["retaliation_timeline_assessment"],
        skeptical_employer_review=values["skeptical_employer_review"],
        document_request_checklist=values["document_request_checklist"],
        promise_contradiction_analysis=values["promise_contradiction_analysis"],
    )
    values["controlled_factual_drafting"] = attach_bilingual_rendering(
        draft,
        bilingual_workflow=values["bilingual_workflow"],
        product_id="controlled_factual_drafting",
        translated_summary_fields=["framing_preflight.strongest_framing[].text", "controlled_draft.rendered_text"],
        original_quote_fields=["supporting evidence remains in matter_evidence_index rows"],
    )


def _case_dashboard(context: TransformContext) -> Any:
    answer, values = context.answer, context.values
    dashboard = build_case_dashboard(
        case_bundle=answer.get("case_bundle"),
        matter_workspace=values["matter_workspace"],
        matter_evidence_index=values["matter_evidence_index"],
        master_chronology=values["master_chronology"],
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        actor_map=values["actor_map"],
        comparative_treatment=answer.get("comparative_treatment"),
        case_patterns=answer.get("case_patterns"),
        skeptical_employer_review=values["skeptical_employer_review"],
        document_request_checklist=values["document_request_checklist"],
        promise_contradiction_analysis=values["promise_contradiction_analysis"],
        deadline_warnings=values["deadline_warnings"],
    )
    return attach_bilingual_rendering(
        dashboard,
        bilingual_workflow=values["bilingual_workflow"],
        product_id="case_dashboard",
        translated_summary_fields=["cards.main_claims_or_issues[].evidence_hint", "cards.strongest_exhibits[].summary"],
        original_quote_fields=["cards.strongest_exhibits[].quoted_evidence.original_text"],
    )


def _build_consistency(context: TransformContext) -> None:
    values = context.values
    values["cross_output_consistency"] = build_cross_output_consistency(
        master_chronology=values["master_chronology"],
        matter_evidence_index=values["matter_evidence_index"],
        lawyer_issue_matrix=values["lawyer_issue_matrix"],
        lawyer_briefing_memo=values["lawyer_briefing_memo"],
        case_dashboard=values["case_dashboard"],
        skeptical_employer_review=values["skeptical_employer_review"],
        controlled_factual_drafting=values["controlled_factual_drafting"],
        retaliation_timeline_assessment=values["retaliation_timeline_assessment"],
        actor_map=values["actor_map"],
    )
    _update_report_sections(values)


def _update_report_sections(values: dict[str, Any]) -> None:
    report = values.get("investigation_report")
    if not isinstance(report, dict):
        return
    report["bilingual_workflow"] = values["bilingual_workflow"]
    sections = as_dict(report.get("sections"))
    updates = {
        "matter_evidence_index": values["matter_evidence_index"],
        "lawyer_issue_matrix": values["lawyer_issue_matrix"],
        "lawyer_briefing_memo": values["lawyer_briefing_memo"],
        "controlled_factual_drafting": values["controlled_factual_drafting"],
        "case_dashboard": values["case_dashboard"],
    }
    for section_id, product in updates.items():
        section = as_dict(sections.get(section_id))
        if section:
            section[section_id] = product
            sections[section_id] = section
    report["sections"] = sections


def _full_payload(context: TransformContext) -> dict[str, Any]:
    answer, params, value = context.answer, context.params, context.values
    return {
        "case_analysis_version": CASE_ANALYSIS_VERSION,
        "workflow": "case_analysis",
        "review_mode": params.review_mode,
        "analysis_query": derive_case_analysis_query(params),
        "search": answer.get("search"),
        "bilingual_workflow": value["bilingual_workflow"],
        "case_scope_quality": value["scope_quality"],
        "case_bundle": answer.get("case_bundle"),
        "multi_source_case_bundle": answer.get("multi_source_case_bundle"),
        "chat_export_ingestion_report": answer.get("chat_export_ingestion_report"),
        "matter_ingestion_report": answer.get("matter_ingestion_report"),
        "power_context": answer.get("power_context"),
        "case_patterns": answer.get("case_patterns"),
        "retaliation_analysis": answer.get("retaliation_analysis"),
        "retaliation_timeline_assessment": value["retaliation_timeline_assessment"],
        "comparative_treatment": answer.get("comparative_treatment"),
        "actor_identity_graph": answer.get("actor_identity_graph"),
        "master_chronology": value["master_chronology"],
        "matter_evidence_index": value["matter_evidence_index"],
        "lawyer_issue_matrix": value["lawyer_issue_matrix"],
        "skeptical_employer_review": value["skeptical_employer_review"],
        "document_request_checklist": value["document_request_checklist"],
        "deadline_warnings": value["deadline_warnings"],
        "matter_workspace": value["matter_workspace"],
        "actor_map": value["actor_map"],
        "witness_map": value["witness_map"],
        "witness_question_packs": value["witness_question_packs"],
        "promise_contradiction_analysis": value["promise_contradiction_analysis"],
        "lawyer_briefing_memo": value["lawyer_briefing_memo"],
        "controlled_factual_drafting": value["controlled_factual_drafting"],
        "case_dashboard": value["case_dashboard"],
        "matter_coverage_ledger": value["coverage_ledger"],
        "cross_output_consistency": value["cross_output_consistency"],
        "archive_harvest": dict(answer.get("archive_harvest") or {}),
        "retrieval_plan": dict(answer.get("retrieval_plan") or {}),
        "finding_evidence_index": value["finding_evidence_index"],
        "evidence_table": value["evidence_table"],
        "behavioral_strength_rubric": answer.get("behavioral_strength_rubric"),
        "investigation_report": value["investigation_report"],
        "message_appendix": value["message_appendix"],
        "_packed": dict(answer.get("_packed") or {}),
        "_case_surface_compaction": dict(answer.get("_case_surface_compaction") or {}),
    }


def _add_limits_and_wave_views(context: TransformContext, transformed: dict[str, Any]) -> None:
    answer, params, values = context.answer, context.params, context.values
    if params.wave_id:
        wave_payload = dict(transformed)
        wave_payload["finding_evidence_index"] = answer.get("finding_evidence_index")
        transformed["wave_local_views"] = build_wave_local_views(wave_payload, wave_id=params.wave_id)
    transformed["analysis_limits"] = analysis_limits(params, answer, values["scope_quality"], final_payload=transformed)
    transformed["review_classification"] = review_classification(
        params, answer, final_payload=transformed, analysis_limits_payload=as_dict(transformed.get("analysis_limits"))
    )


def _report_only_payload(context: TransformContext, transformed: dict[str, Any]) -> dict[str, Any]:
    answer, params, value = context.answer, context.params, context.values
    return {
        "case_analysis_version": CASE_ANALYSIS_VERSION,
        "workflow": "case_analysis",
        "review_mode": params.review_mode,
        "review_classification": transformed["review_classification"],
        "analysis_query": derive_case_analysis_query(params),
        "bilingual_workflow": value["bilingual_workflow"],
        "case_scope_quality": value["scope_quality"],
        "investigation_report": value["investigation_report"],
        "chat_export_ingestion_report": answer.get("chat_export_ingestion_report"),
        "matter_ingestion_report": answer.get("matter_ingestion_report"),
        "retaliation_timeline_assessment": value["retaliation_timeline_assessment"],
        "actor_map": value["actor_map"],
        "witness_map": value["witness_map"],
        "witness_question_packs": value["witness_question_packs"],
        "promise_contradiction_analysis": value["promise_contradiction_analysis"],
        "lawyer_briefing_memo": value["lawyer_briefing_memo"],
        "controlled_factual_drafting": value["controlled_factual_drafting"],
        "case_dashboard": value["case_dashboard"],
        "matter_coverage_ledger": value["coverage_ledger"],
        "cross_output_consistency": value["cross_output_consistency"],
        "skeptical_employer_review": value["skeptical_employer_review"],
        "document_request_checklist": value["document_request_checklist"],
        "deadline_warnings": value["deadline_warnings"],
        "retrieval_plan": dict(answer.get("retrieval_plan") or {}),
        "message_appendix": value["message_appendix"],
        "analysis_limits": transformed["analysis_limits"],
        "wave_local_views": transformed.get("wave_local_views"),
        "_packed": transformed["_packed"],
        "_case_surface_compaction": transformed["_case_surface_compaction"],
    }


def _apply_privacy(context: TransformContext, payload: dict[str, Any]) -> dict[str, Any]:
    redacted, guardrails = apply_privacy_guardrails(payload, privacy_mode=context.params.privacy_mode)
    if isinstance(redacted, dict):
        redacted["privacy_guardrails"] = guardrails
        redacted["bilingual_workflow"] = context.values["bilingual_workflow"]
        report = redacted.get("investigation_report")
        if isinstance(report, dict):
            report["privacy_guardrails"] = guardrails
            report["bilingual_workflow"] = context.values["bilingual_workflow"]
    return redacted
