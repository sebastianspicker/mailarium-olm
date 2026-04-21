"""Core payload transformation for case-analysis outputs."""

from __future__ import annotations

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


def transform_case_analysis_payload(answer_payload: dict[str, Any], params: EmailCaseAnalysisInput) -> dict[str, Any]:
    """Normalize an answer-context payload into the dedicated case-analysis contract."""
    scope_quality = case_scope_quality(params)
    message_appendix = build_message_appendix(answer_payload, include_message_appendix=params.include_message_appendix)
    finding_evidence_index = answer_payload.get("finding_evidence_index")
    evidence_table = answer_payload.get("evidence_table")
    if params.compact_case_evidence:
        finding_evidence_index = {
            "summary": {
                "finding_count": len((finding_evidence_index or {}).get("findings", []))
                if isinstance(finding_evidence_index, dict)
                else 0,
                "finding_ids": [
                    str(finding.get("finding_id") or "")
                    for finding in (
                        ((finding_evidence_index or {}).get("findings", [])) if isinstance(finding_evidence_index, dict) else []
                    )[:3]
                    if isinstance(finding, dict)
                ],
            }
        }
        evidence_table = {
            "summary": {
                "row_count": int((evidence_table or {}).get("row_count") or 0) if isinstance(evidence_table, dict) else 0,
            }
        }
        if message_appendix.get("included"):
            rows = [row for row in message_appendix.get("rows", []) if isinstance(row, dict)]
            shown_rows = rows[:5]
            message_appendix = {
                "included": True,
                "row_count": len(rows),
                "shown_row_count": len(shown_rows),
                "rows": shown_rows,
                "_truncated": len(rows) - len(shown_rows),
            }
    master_chronology = build_master_chronology(
        case_bundle=answer_payload.get("case_bundle"),
        timeline=answer_payload.get("timeline"),
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        finding_evidence_index=answer_payload.get("finding_evidence_index"),
    )
    matter_evidence_index = build_matter_evidence_index(
        case_bundle=answer_payload.get("case_bundle"),
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        finding_evidence_index=answer_payload.get("finding_evidence_index"),
        master_chronology=master_chronology,
    )
    bilingual_workflow = build_bilingual_workflow(
        case_bundle=answer_payload.get("case_bundle"),
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        output_language=params.output_language,
        translation_mode=params.translation_mode,
    )
    source_bundle = as_dict(answer_payload.get("multi_source_case_bundle"))
    generated_investigation_report = (
        build_investigation_report(
            case_bundle=answer_payload.get("case_bundle"),
            candidates=[item for item in answer_payload.get("candidates", []) if isinstance(item, dict)]
            if isinstance(answer_payload.get("candidates"), list)
            else [],
            timeline=answer_payload.get("timeline"),
            power_context=answer_payload.get("power_context"),
            case_patterns=answer_payload.get("case_patterns"),
            retaliation_analysis=answer_payload.get("retaliation_analysis"),
            comparative_treatment=answer_payload.get("comparative_treatment"),
            communication_graph=answer_payload.get("communication_graph"),
            actor_identity_graph=answer_payload.get("actor_identity_graph"),
            finding_evidence_index=answer_payload.get("finding_evidence_index"),
            evidence_table=answer_payload.get("evidence_table"),
            multi_source_case_bundle=source_bundle,
            output_language=params.output_language,
            translation_mode=params.translation_mode,
        )
        if isinstance(answer_payload.get("multi_source_case_bundle"), dict) and bool(source_bundle.get("sources"))
        else None
    )
    investigation_report = inject_scope_warnings_into_report(
        generated_investigation_report or answer_payload.get("investigation_report"),
        scope_quality,
    )
    preliminary_analysis_limits = analysis_limits(
        params,
        answer_payload,
        scope_quality,
        final_payload={
            "case_patterns": answer_payload.get("case_patterns"),
            "finding_evidence_index": finding_evidence_index,
            "investigation_report": investigation_report,
            "message_appendix": message_appendix,
        },
    )
    retaliation_analysis_payload = as_dict(answer_payload.get("retaliation_analysis"))
    retaliation_timeline_assessment = (
        dict(retaliation_analysis_payload.get("retaliation_timeline_assessment") or {}) if retaliation_analysis_payload else None
    )
    if isinstance(retaliation_timeline_assessment, dict) and retaliation_analysis_payload:
        retaliation_timeline_assessment["anchor_requirement_status"] = str(
            retaliation_analysis_payload.get("anchor_requirement_status") or ""
        )
        retaliation_timeline_assessment["protected_activity_candidate_count"] = int(
            retaliation_analysis_payload.get("protected_activity_candidate_count") or 0
        )
        retaliation_timeline_assessment["adverse_action_candidate_count"] = int(
            retaliation_analysis_payload.get("adverse_action_candidate_count") or 0
        )
        retaliation_timeline_assessment["source_backed_candidate_counts"] = dict(
            retaliation_analysis_payload.get("source_backed_candidate_counts") or {}
        )
        if not retaliation_timeline_assessment.get("insufficiency_reason"):
            if str(retaliation_timeline_assessment.get("anchor_requirement_status") or "") == (
                "explicit_trigger_confirmation_required"
            ):
                retaliation_timeline_assessment["insufficiency_reason"] = (
                    "No explicit confirmed trigger event is available yet for a stronger before/after retaliation analysis."
                )
            elif not list(retaliation_timeline_assessment.get("protected_activity_timeline") or []) and not list(
                retaliation_timeline_assessment.get("adverse_action_timeline") or []
            ):
                retaliation_timeline_assessment["insufficiency_reason"] = (
                    "The current record does not yet contain enough protected-activity and adverse-action timeline detail "
                    "for a fuller retaliation assessment."
                )
    finding_rows = (
        [
            finding
            for finding in ((answer_payload.get("finding_evidence_index") or {}).get("findings", []))
            if isinstance(finding, dict)
        ]
        if isinstance(answer_payload.get("finding_evidence_index"), dict)
        else []
    )
    lawyer_issue_matrix = build_lawyer_issue_matrix(
        case_bundle=answer_payload.get("case_bundle"),
        findings=finding_rows,
        matter_evidence_index=matter_evidence_index,
        comparative_treatment=answer_payload.get("comparative_treatment"),
        retaliation_timeline_assessment=retaliation_timeline_assessment,
        employment_issue_frameworks=((investigation_report.get("sections") or {}).get("employment_issue_frameworks"))
        if isinstance(investigation_report, dict)
        else None,
        master_chronology=master_chronology,
        case_scope_quality=scope_quality,
        analysis_limits=preliminary_analysis_limits,
        include_full_issue_set=params.review_mode == "exhaustive_matter_review",
    )
    lawyer_issue_matrix = attach_bilingual_rendering(
        lawyer_issue_matrix,
        bilingual_workflow=bilingual_workflow,
        product_id="lawyer_issue_matrix",
        translated_summary_fields=["relevant_facts", "likely_opposing_argument", "missing_proof"],
        original_quote_fields=["rows[].strongest_documents[].quoted_evidence.original_text"],
    )
    skeptical_employer_review = build_skeptical_employer_review(
        findings=finding_rows,
        master_chronology=master_chronology,
        matter_evidence_index=matter_evidence_index,
        comparative_treatment=answer_payload.get("comparative_treatment"),
        lawyer_issue_matrix=lawyer_issue_matrix,
        overall_assessment=((investigation_report.get("sections") or {}).get("overall_assessment"))
        if isinstance(investigation_report, dict)
        else None,
        retaliation_timeline_assessment=retaliation_timeline_assessment,
        case_scope_quality=scope_quality,
        analysis_limits=preliminary_analysis_limits,
    )
    missing_information_entries = [
        entry
        for entry in (
            (((investigation_report.get("sections") or {}).get("missing_information") or {}).get("entries") or [])
            if isinstance(investigation_report, dict)
            else []
        )
        if isinstance(entry, dict)
    ]
    document_request_checklist = build_document_request_checklist(
        matter_evidence_index=matter_evidence_index,
        skeptical_employer_review=skeptical_employer_review,
        missing_information_entries=missing_information_entries,
        lawyer_issue_matrix=lawyer_issue_matrix,
        case_scope_quality=scope_quality,
        analysis_limits=preliminary_analysis_limits,
    )
    deadline_warnings = build_deadline_warnings(
        case_bundle=answer_payload.get("case_bundle"),
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        document_request_checklist=document_request_checklist,
    )
    if isinstance(deadline_warnings, dict):
        warnings = [item for item in (deadline_warnings.get("warnings") or []) if isinstance(item, dict)]
        warnings_by_issue: dict[str, list[str]] = {}
        warnings_by_group: dict[str, list[str]] = {}
        for warning_row in warnings:
            warning_id = str(warning_row.get("warning_id") or "")
            if not warning_id:
                continue
            for issue_id in [str(item) for item in warning_row.get("linked_issue_ids", []) if item]:
                warnings_by_issue.setdefault(issue_id, []).append(warning_id)
            for group_id in [str(item) for item in warning_row.get("linked_group_ids", []) if item]:
                warnings_by_group.setdefault(group_id, []).append(warning_id)
        if isinstance(lawyer_issue_matrix, dict):
            for row in [item for item in lawyer_issue_matrix.get("rows", []) if isinstance(item, dict)]:
                issue_id = str(row.get("issue_id") or "")
                row["timing_warning_ids"] = warnings_by_issue.get(issue_id, [])
        if isinstance(document_request_checklist, dict):
            document_request_checklist["deadline_warnings"] = deadline_warnings
            for group in [item for item in document_request_checklist.get("groups", []) if isinstance(item, dict)]:
                group_id = str(group.get("group_id") or "")
                group["timing_warning_ids"] = warnings_by_group.get(group_id, [])
    matter_workspace = build_matter_workspace(
        case_bundle=answer_payload.get("case_bundle"),
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
    )
    actor_witness_map = build_actor_witness_map(
        case_bundle=answer_payload.get("case_bundle"),
        actor_identity_graph=answer_payload.get("actor_identity_graph"),
        communication_graph=answer_payload.get("communication_graph"),
        master_chronology=master_chronology,
        matter_workspace=matter_workspace,
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
    )
    promise_contradiction_analysis = build_promise_contradiction_analysis(
        case_bundle=answer_payload.get("case_bundle"),
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        master_chronology=master_chronology,
    )
    lawyer_briefing_memo = build_lawyer_briefing_memo(
        case_bundle=answer_payload.get("case_bundle"),
        matter_workspace=matter_workspace,
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        retaliation_timeline_assessment=retaliation_timeline_assessment,
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
        case_bundle=answer_payload.get("case_bundle"),
        findings=finding_rows,
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        comparative_treatment=answer_payload.get("comparative_treatment"),
        retaliation_timeline_assessment=retaliation_timeline_assessment,
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
    actor_map = actor_witness_map.get("actor_map") if isinstance(actor_witness_map, dict) else None
    witness_map = actor_witness_map.get("witness_map") if isinstance(actor_witness_map, dict) else None
    witness_question_packs = build_witness_question_packs(
        actor_witness_map=actor_witness_map,
        master_chronology=master_chronology,
        matter_evidence_index=matter_evidence_index,
        document_request_checklist=document_request_checklist,
    )
    case_dashboard = build_case_dashboard(
        case_bundle=answer_payload.get("case_bundle"),
        matter_workspace=matter_workspace,
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        actor_map=actor_map,
        comparative_treatment=answer_payload.get("comparative_treatment"),
        case_patterns=answer_payload.get("case_patterns"),
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
    coverage_ledger = matter_coverage_ledger(
        params=params,
        multi_source_case_bundle=answer_payload.get("multi_source_case_bundle"),
        matter_evidence_index=matter_evidence_index,
        master_chronology=master_chronology,
        lawyer_issue_matrix=lawyer_issue_matrix,
        message_appendix=message_appendix,
    )
    cross_output_consistency = build_cross_output_consistency(
        master_chronology=master_chronology,
        matter_evidence_index=matter_evidence_index,
        lawyer_issue_matrix=lawyer_issue_matrix,
        lawyer_briefing_memo=lawyer_briefing_memo,
        case_dashboard=case_dashboard,
        skeptical_employer_review=skeptical_employer_review,
        controlled_factual_drafting=controlled_factual_drafting,
        retaliation_timeline_assessment=retaliation_timeline_assessment,
        actor_map=actor_map,
    )
    if isinstance(investigation_report, dict):
        investigation_report["bilingual_workflow"] = bilingual_workflow
        sections = as_dict(investigation_report.get("sections"))
        section_updates = {
            "matter_evidence_index": ("matter_evidence_index", matter_evidence_index),
            "lawyer_issue_matrix": ("lawyer_issue_matrix", lawyer_issue_matrix),
            "lawyer_briefing_memo": ("lawyer_briefing_memo", lawyer_briefing_memo),
            "controlled_factual_drafting": ("controlled_factual_drafting", controlled_factual_drafting),
            "case_dashboard": ("case_dashboard", case_dashboard),
        }
        for section_id, (payload_key, payload_value) in section_updates.items():
            section = as_dict(sections.get(section_id))
            if section:
                section[payload_key] = payload_value
                sections[section_id] = section
        investigation_report["sections"] = sections

    transformed: dict[str, Any] = {
        "case_analysis_version": CASE_ANALYSIS_VERSION,
        "workflow": "case_analysis",
        "review_mode": params.review_mode,
        "analysis_query": derive_case_analysis_query(params),
        "search": answer_payload.get("search"),
        "bilingual_workflow": bilingual_workflow,
        "case_scope_quality": scope_quality,
        "case_bundle": answer_payload.get("case_bundle"),
        "multi_source_case_bundle": answer_payload.get("multi_source_case_bundle"),
        "chat_export_ingestion_report": answer_payload.get("chat_export_ingestion_report"),
        "matter_ingestion_report": answer_payload.get("matter_ingestion_report"),
        "power_context": answer_payload.get("power_context"),
        "case_patterns": answer_payload.get("case_patterns"),
        "retaliation_analysis": answer_payload.get("retaliation_analysis"),
        "retaliation_timeline_assessment": retaliation_timeline_assessment,
        "comparative_treatment": answer_payload.get("comparative_treatment"),
        "actor_identity_graph": answer_payload.get("actor_identity_graph"),
        "master_chronology": master_chronology,
        "matter_evidence_index": matter_evidence_index,
        "lawyer_issue_matrix": lawyer_issue_matrix,
        "skeptical_employer_review": skeptical_employer_review,
        "document_request_checklist": document_request_checklist,
        "deadline_warnings": deadline_warnings,
        "matter_workspace": matter_workspace,
        "actor_map": actor_map,
        "witness_map": witness_map,
        "witness_question_packs": witness_question_packs,
        "promise_contradiction_analysis": promise_contradiction_analysis,
        "lawyer_briefing_memo": lawyer_briefing_memo,
        "controlled_factual_drafting": controlled_factual_drafting,
        "case_dashboard": case_dashboard,
        "matter_coverage_ledger": coverage_ledger,
        "cross_output_consistency": cross_output_consistency,
        "archive_harvest": dict(answer_payload.get("archive_harvest") or {}),
        "retrieval_plan": dict(answer_payload.get("retrieval_plan") or {}),
        "finding_evidence_index": finding_evidence_index,
        "evidence_table": evidence_table,
        "behavioral_strength_rubric": answer_payload.get("behavioral_strength_rubric"),
        "investigation_report": investigation_report,
        "message_appendix": message_appendix,
        "_packed": dict(answer_payload.get("_packed") or {}),
        "_case_surface_compaction": dict(answer_payload.get("_case_surface_compaction") or {}),
    }
    if params.wave_id:
        wave_local_payload = dict(transformed)
        wave_local_payload["finding_evidence_index"] = answer_payload.get("finding_evidence_index")
        transformed["wave_local_views"] = build_wave_local_views(wave_local_payload, wave_id=params.wave_id)
    transformed["analysis_limits"] = analysis_limits(
        params,
        answer_payload,
        scope_quality,
        final_payload=transformed,
    )
    transformed["review_classification"] = review_classification(
        params,
        answer_payload,
        final_payload=transformed,
        analysis_limits_payload=as_dict(transformed.get("analysis_limits")),
    )
    final_payload = transformed
    if params.output_mode == "report_only":
        final_payload = {
            "case_analysis_version": CASE_ANALYSIS_VERSION,
            "workflow": "case_analysis",
            "review_mode": params.review_mode,
            "review_classification": transformed["review_classification"],
            "analysis_query": derive_case_analysis_query(params),
            "bilingual_workflow": bilingual_workflow,
            "case_scope_quality": scope_quality,
            "investigation_report": investigation_report,
            "chat_export_ingestion_report": answer_payload.get("chat_export_ingestion_report"),
            "matter_ingestion_report": answer_payload.get("matter_ingestion_report"),
            "retaliation_timeline_assessment": retaliation_timeline_assessment,
            "actor_map": actor_map,
            "witness_map": witness_map,
            "witness_question_packs": witness_question_packs,
            "promise_contradiction_analysis": promise_contradiction_analysis,
            "lawyer_briefing_memo": lawyer_briefing_memo,
            "controlled_factual_drafting": controlled_factual_drafting,
            "case_dashboard": case_dashboard,
            "matter_coverage_ledger": coverage_ledger,
            "cross_output_consistency": cross_output_consistency,
            "skeptical_employer_review": skeptical_employer_review,
            "document_request_checklist": document_request_checklist,
            "deadline_warnings": deadline_warnings,
            "retrieval_plan": dict(answer_payload.get("retrieval_plan") or {}),
            "message_appendix": message_appendix,
            "analysis_limits": transformed["analysis_limits"],
            "wave_local_views": transformed.get("wave_local_views"),
            "_packed": transformed["_packed"],
            "_case_surface_compaction": transformed["_case_surface_compaction"],
        }
    redacted_payload, privacy_guardrails = apply_privacy_guardrails(
        final_payload,
        privacy_mode=params.privacy_mode,
    )
    if isinstance(redacted_payload, dict):
        redacted_payload["privacy_guardrails"] = privacy_guardrails
        redacted_payload["bilingual_workflow"] = bilingual_workflow
        report = redacted_payload.get("investigation_report")
        if isinstance(report, dict):
            report["privacy_guardrails"] = privacy_guardrails
            report["bilingual_workflow"] = bilingual_workflow
    return redacted_payload
