"""Compact investigation-report rendering for tight response budgets."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

from typing import Any

from .investigation_report_constants import INVESTIGATION_REPORT_VERSION, SECTION_ORDER
from .investigation_report_sections import _as_dict, _as_list


def _dict_items(value: Any, limit: int) -> list[dict[str, Any]]:
    return [dict(item) for item in _as_list(value)[:limit] if isinstance(item, dict)]


def _dict_values(value: Any, limit: int) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)][:limit]


def _string_items(value: Any, limit: int | None = None) -> list[str]:
    items = [str(item) for item in _as_list(value) if item]
    return items[:limit]


def _sorted_dict_values(value: Any, *, key: Any, limit: int) -> list[dict[str, Any]]:
    return sorted(_dict_values(value, len(_as_list(value))), key=key)[:limit]


def _compact_section_evidence_triage(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    compact_section["summary"] = dict(section.get("summary") or {})
    for field in ("direct_evidence", "reasonable_inference", "unresolved_points", "missing_proof"):
        compact_section[field] = [entry for entry in _as_list(section.get(field)) if isinstance(entry, dict)][:1]


def _compact_section_employment_issue_frameworks(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    compact_section["issue_tracks"] = _dict_values(section.get("issue_tracks"), 2)
    compact_section["issue_tag_summary"] = _as_dict(section.get("issue_tag_summary"))


def _lawyer_row_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    relevance_rank = 0 if str(item.get("legal_relevance_status") or "") == "supported_for_further_review" else 1
    return (
        relevance_rank,
        -len(_as_list(item.get("strongest_documents"))),
        -len(_as_list(item.get("supporting_source_ids"))),
        str(item.get("issue_id") or ""),
    )


def _compact_lawyer_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_id": str(row.get("issue_id") or ""),
        "title": str(row.get("title") or ""),
        "legal_relevance_status": str(row.get("legal_relevance_status") or ""),
        "urgency_or_deadline_relevance": str(row.get("urgency_or_deadline_relevance") or ""),
        "timing_warning_ids": _string_items(row.get("timing_warning_ids"), 2),
        "strongest_documents": _dict_values(row.get("strongest_documents"), 1),
        "not_legal_advice": bool(row.get("not_legal_advice")),
    }


def _compact_section_lawyer_issue_matrix(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    lawyer_matrix = _as_dict(section.get("lawyer_issue_matrix"))
    rows = _sorted_dict_values(lawyer_matrix.get("rows"), key=_lawyer_row_sort_key, limit=2)
    compact_section["lawyer_issue_matrix"] = {
        "version": str(lawyer_matrix.get("version") or ""),
        "row_count": int(lawyer_matrix.get("row_count") or 0),
        "bilingual_rendering": dict(lawyer_matrix.get("bilingual_rendering") or {}),
        "rows": [_compact_lawyer_row(row) for row in rows],
    }


def _compact_actor(actor: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor_id": str(actor.get("actor_id") or ""),
        "name": str(actor.get("name") or ""),
        "status": dict(actor.get("status") or {}),
        "helps_hurts_mixed": str(actor.get("helps_hurts_mixed") or ""),
    }


def _compact_section_actor_and_witness_map(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    actor_map = _as_dict(section.get("actor_map"))
    witness_map = _as_dict(section.get("witness_map"))
    compact_section["actor_map"] = {
        "actor_count": int(actor_map.get("actor_count") or 0),
        "summary": dict(actor_map.get("summary") or {}),
        "actors": [_compact_actor(actor) for actor in _dict_values(actor_map.get("actors"), 2)],
    }
    compact_section["witness_map"] = {
        "primary_decision_makers": _dict_items(witness_map.get("primary_decision_makers"), 2),
        "potentially_independent_witnesses": _dict_items(witness_map.get("potentially_independent_witnesses"), 2),
        "coordination_points": _dict_items(witness_map.get("coordination_points"), 2),
    }


def _compact_question_pack(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "pack_id": str(item.get("pack_id") or ""),
        "actor_id": str(item.get("actor_id") or ""),
        "actor_name": str(item.get("actor_name") or ""),
        "pack_type": str(item.get("pack_type") or ""),
        "likely_knowledge_areas": _string_items(item.get("likely_knowledge_areas"), 2),
        "suggested_questions": _string_items(item.get("suggested_questions"), 2),
    }


def _compact_section_witness_question_packs(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    packs = _as_dict(section.get("witness_question_packs"))
    compact_section["witness_question_packs"] = {
        "version": str(packs.get("version") or ""),
        "pack_count": int(packs.get("pack_count") or 0),
        "summary": dict(packs.get("summary") or {}),
        "packs": [_compact_question_pack(item) for item in _dict_values(packs.get("packs"), 2)],
    }


def _compact_section_promise_and_contradiction_analysis(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    analysis = _as_dict(section.get("promise_contradiction_analysis"))
    compact_section["promise_contradiction_analysis"] = {
        "version": str(analysis.get("version") or ""),
        "summary": dict(analysis.get("summary") or {}),
        "promises_vs_actions": _dict_items(analysis.get("promises_vs_actions"), 2),
        "omission_rows": _dict_items(analysis.get("omission_rows"), 2),
        "contradiction_table": _dict_items(analysis.get("contradiction_table"), 2),
    }


def _compact_section_lawyer_briefing_memo(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    memo = _as_dict(section.get("lawyer_briefing_memo"))
    memo_sections = _as_dict(memo.get("sections"))
    compact_section["lawyer_briefing_memo"] = {
        "version": str(memo.get("version") or ""),
        "memo_format": str(memo.get("memo_format") or ""),
        "summary": dict(memo.get("summary") or {}),
        "bilingual_rendering": dict(memo.get("bilingual_rendering") or {}),
        "sections": {
            section_name: [dict(item) for item in _as_list(memo_sections.get(section_name))[:1] if isinstance(item, dict)]
            for section_name in (
                "executive_summary",
                "key_facts",
                "timeline",
                "core_theories",
                "strongest_evidence",
                "weaknesses_or_risks",
                "urgent_next_steps",
                "open_questions_for_counsel",
            )
        },
    }


def _compact_preflight(preflight: dict[str, Any]) -> dict[str, Any]:
    return {
        "objective_of_draft": str(preflight.get("objective_of_draft") or ""),
        "legal_and_factual_risks": _dict_items(preflight.get("legal_and_factual_risks"), 2),
        "strongest_framing": _dict_items(preflight.get("strongest_framing"), 2),
        "safest_framing": _dict_items(preflight.get("safest_framing"), 2),
        "allegation_ceiling": dict(preflight.get("allegation_ceiling") or {}),
    }


def _compact_controlled_draft(draft: dict[str, Any]) -> dict[str, Any]:
    draft_sections = _as_dict(draft.get("sections"))
    return {
        "audience": str(draft.get("audience") or ""),
        "tone": str(draft.get("tone") or ""),
        "allegation_ceiling_applied": str(draft.get("allegation_ceiling_applied") or ""),
        "sections": {
            section_name: _dict_items(draft_sections.get(section_name), 2)
            for section_name in ("established_facts", "concerns", "requests_for_clarification", "formal_demands")
        },
    }


def _compact_section_controlled_factual_drafting(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    drafting = _as_dict(section.get("controlled_factual_drafting"))
    compact_section["controlled_factual_drafting"] = {
        "version": str(drafting.get("version") or ""),
        "drafting_format": str(drafting.get("drafting_format") or ""),
        "summary": dict(drafting.get("summary") or {}),
        "bilingual_rendering": dict(drafting.get("bilingual_rendering") or {}),
        "framing_preflight": _compact_preflight(_as_dict(drafting.get("framing_preflight"))),
        "controlled_draft": _compact_controlled_draft(_as_dict(drafting.get("controlled_draft"))),
    }


def _compact_section_case_dashboard(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    dashboard = _as_dict(section.get("case_dashboard"))
    cards = _as_dict(dashboard.get("cards"))
    compact_section["case_dashboard"] = {
        "version": str(dashboard.get("version") or ""),
        "dashboard_format": str(dashboard.get("dashboard_format") or ""),
        "summary": dict(dashboard.get("summary") or {}),
        "bilingual_rendering": dict(dashboard.get("bilingual_rendering") or {}),
        "cards": {
            card_id: _dict_items(cards.get(card_id), 2)
            for card_id in (
                "main_claims_or_issues",
                "key_dates",
                "strongest_exhibits",
                "open_evidence_gaps",
                "main_actors",
                "comparator_points",
                "process_irregularities",
                "drafting_priorities",
                "timing_warnings",
                "risks_or_weak_spots",
                "recommended_next_actions",
            )
        },
    }


def _compact_consistency_check(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": str(item.get("check_id") or ""),
        "status": str(item.get("status") or ""),
        "summary": str(item.get("summary") or ""),
        "affected_outputs": _string_items(item.get("affected_outputs"), 3),
    }


def _compact_section_cross_output_consistency(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    consistency = _as_dict(section.get("cross_output_consistency"))
    compact_section["cross_output_consistency"] = {
        "version": str(consistency.get("version") or ""),
        "overall_status": str(consistency.get("overall_status") or ""),
        "summary": dict(consistency.get("summary") or {}),
        "checks": [_compact_consistency_check(item) for item in _dict_values(consistency.get("checks"), 3)],
    }


def _compact_weakness(item: dict[str, Any]) -> dict[str, Any]:
    repair_guidance = _as_dict(item.get("repair_guidance"))
    return {
        "weakness_id": str(item.get("weakness_id") or ""),
        "category": str(item.get("category") or ""),
        "critique": str(item.get("critique") or ""),
        "repair_guidance": {
            "how_to_fix": str(repair_guidance.get("how_to_fix") or ""),
            "cautious_rewrite": str(repair_guidance.get("cautious_rewrite") or ""),
        },
    }


def _compact_section_skeptical_employer_review(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    skeptical_review = _as_dict(section.get("skeptical_employer_review"))
    compact_section["skeptical_employer_review"] = {
        "version": str(skeptical_review.get("version") or ""),
        "summary": dict(skeptical_review.get("summary") or {}),
        "weaknesses": [_compact_weakness(item) for item in _dict_values(skeptical_review.get("weaknesses"), 2)],
    }


def _compact_request_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": str(item.get("item_id") or ""),
        "request": str(item.get("request") or ""),
        "likely_custodian": str(item.get("likely_custodian") or ""),
        "urgency": str(item.get("urgency") or ""),
        "risk_of_loss": str(item.get("risk_of_loss") or ""),
    }


def _compact_request_group(group: dict[str, Any]) -> dict[str, Any]:
    items = _as_list(group.get("items"))
    return {
        "group_id": str(group.get("group_id") or ""),
        "title": str(group.get("title") or ""),
        "timing_warning_ids": _string_items(group.get("timing_warning_ids"), 2),
        "item_count": int(group.get("item_count") or len(items)),
        "items": [_compact_request_item(item) for item in _dict_values(items, 1)],
    }


def _compact_section_document_request_checklist(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    checklist = _as_dict(section.get("document_request_checklist"))
    compact_section["document_request_checklist"] = {
        "version": str(checklist.get("version") or ""),
        "group_count": int(checklist.get("group_count") or 0),
        "deadline_warnings": _as_dict(checklist.get("deadline_warnings")),
        "groups": [_compact_request_group(group) for group in _dict_values(checklist.get("groups"), 2)],
    }


def _nonempty_fields(value: Any, field: str, limit: int) -> list[str]:
    return [str(item.get(field) or "") for item in _dict_values(value, limit) if str(item.get(field) or "")]


def _compact_chronology_summary(summary: dict[str, Any]) -> dict[str, Any]:
    conflicts = _as_dict(summary.get("source_conflict_registry"))
    return {
        "date_precision_counts": dict(summary.get("date_precision_counts") or {}),
        "source_linked_entry_count": int(summary.get("source_linked_entry_count") or 0),
        "date_range": dict(summary.get("date_range") or {}),
        "date_gap_count": int(summary.get("date_gap_count") or 0),
        "largest_gap_days": int(summary.get("largest_gap_days") or 0),
        "source_conflict_registry": {
            "conflict_count": int(conflicts.get("conflict_count") or 0),
            "conflict_ids": _nonempty_fields(conflicts.get("conflicts"), "conflict_id", 3),
        },
    }


def _compact_chronology_gap(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "gap_id": str(item.get("gap_id") or ""),
        "priority": str(item.get("priority") or ""),
        "gap_days": int(item.get("gap_days") or 0),
        "missing_bridge_record_suggestions": _string_items(item.get("missing_bridge_record_suggestions"), 2),
    }


def _compact_chronology_entry(item: dict[str, Any]) -> dict[str, Any]:
    linkage = _as_dict(item.get("source_linkage"))
    return {
        "chronology_id": str(item.get("chronology_id") or ""),
        "date": str(item.get("date") or ""),
        "title": str(item.get("title") or ""),
        "source_ids": _string_items(linkage.get("source_ids"), 3),
        "supporting_uids": _string_items(linkage.get("supporting_uids"), 3),
        "linked_source_ids": _string_items(linkage.get("linked_source_ids"), 3),
        "supporting_citation_ids": _string_items(linkage.get("supporting_citation_ids"), 3),
        "evidence_handles": _string_items(linkage.get("evidence_handles"), 3),
    }


def _compact_section_chronological_pattern_analysis(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    chronology = _as_dict(section.get("master_chronology"))
    summary = _as_dict(chronology.get("summary"))
    compact_section["master_chronology"] = {
        "version": str(chronology.get("version") or ""),
        "entry_count": int(chronology.get("entry_count") or 0),
        "summary": _compact_chronology_summary(summary),
        "date_gaps_and_unexplained_sequences": [
            _compact_chronology_gap(item) for item in _dict_values(summary.get("date_gaps_and_unexplained_sequences"), 2)
        ],
        "entries": [_compact_chronology_entry(item) for item in _dict_values(chronology.get("entries"), 2)],
        "_truncated": int(chronology.get("_truncated") or 0),
    }
    retaliation_timeline = _as_dict(section.get("retaliation_timeline_assessment"))
    compact_section["retaliation_timeline_assessment"] = {
        "version": str(retaliation_timeline.get("version") or ""),
        "protected_activity_timeline": _dict_items(retaliation_timeline.get("protected_activity_timeline"), 1),
        "temporal_correlation_analysis": _dict_items(retaliation_timeline.get("temporal_correlation_analysis"), 1),
        "overall_evidentiary_rating": dict(retaliation_timeline.get("overall_evidentiary_rating") or {}),
    }


def _compact_top_exhibit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "exhibit_id": str(row.get("exhibit_id") or ""),
        "source_id": str(row.get("source_id") or ""),
        "priority_score": int(row.get("priority_score") or 0),
        "strength": str(row.get("strength") or ""),
        "readiness": str(row.get("readiness") or ""),
        "source_conflict_status": str(row.get("source_conflict_status") or ""),
        "supporting_source_ids": _string_items(row.get("supporting_source_ids"), 3),
        "supporting_uids": _string_items(row.get("supporting_uids"), 3),
        "supporting_citation_ids": _string_items(row.get("supporting_citation_ids"), 3),
    }


def _matter_row_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    dispute_rank = 0 if str(item.get("source_conflict_status") or "") == "disputed" else 1
    return (
        dispute_rank,
        -len(_as_list(item.get("supporting_source_ids"))),
        -len(_as_list(item.get("supporting_citation_ids"))),
        str(item.get("source_id") or ""),
    )


def _compact_matter_row(row: dict[str, Any]) -> dict[str, Any]:
    reliability = _as_dict(row.get("exhibit_reliability"))
    next_step = _as_dict(reliability.get("next_step_logic"))
    return {
        "exhibit_id": str(row.get("exhibit_id") or ""),
        "source_id": str(row.get("source_id") or ""),
        "source_conflict_status": str(row.get("source_conflict_status") or ""),
        "supporting_source_ids": _string_items(row.get("supporting_source_ids"), 3),
        "supporting_uids": _string_items(row.get("supporting_uids"), 3),
        "linked_source_ids": _string_items(row.get("linked_source_ids"), 3),
        "source_conflict_ids": _string_items(row.get("source_conflict_ids"), 3),
        "promotability_status": str(row.get("promotability_status") or ""),
        "exhibit_reliability": {
            "strength": str(reliability.get("strength") or ""),
            "next_step_logic": {"readiness": str(next_step.get("readiness") or "")},
        },
        "supporting_citation_ids": _string_items(row.get("supporting_citation_ids")),
    }


def _compact_matter_summary(summary: dict[str, Any]) -> dict[str, Any]:
    readiness_counts = summary.get("exhibit_readiness_counts") or summary.get("readiness_counts") or {}
    return {
        "exhibit_strength_counts": dict(summary.get("exhibit_strength_counts") or {}),
        "readiness_counts": dict(readiness_counts),
        "source_conflict_status_counts": dict(summary.get("source_conflict_status_counts") or {}),
        "missing_exhibit_count": int(summary.get("missing_exhibit_count") or 0),
    }


def _compact_section_matter_evidence_index(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    matter_index = _as_dict(section.get("matter_evidence_index"))
    rows = _sorted_dict_values(matter_index.get("rows"), key=_matter_row_sort_key, limit=1)
    top_exhibits = _dict_values(matter_index.get("top_15_exhibits"), 3)
    compact_section["matter_evidence_index"] = {
        "version": str(matter_index.get("version") or ""),
        "row_count": int(matter_index.get("row_count") or 0),
        "summary": _compact_matter_summary(_as_dict(matter_index.get("summary"))),
        "top_15_exhibits": [_compact_top_exhibit(row) for row in top_exhibits],
        "rows": [_compact_matter_row(row) for row in rows],
    }


def _compact_section_overall_assessment(section: dict[str, Any], compact_section: dict[str, Any]) -> None:
    compact_section["primary_assessment"] = str(section.get("primary_assessment") or "insufficient_evidence")
    compact_section["secondary_plausible_interpretations"] = [
        str(item) for item in _as_list(section.get("secondary_plausible_interpretations")) if item
    ]
    compact_section["assessment_strength"] = str(section.get("assessment_strength") or "insufficient_evidence")
    compact_section["downgrade_reasons"] = [str(item) for item in _as_list(section.get("downgrade_reasons")) if item]


_SECTION_COMPACTORS = {
    "evidence_triage": _compact_section_evidence_triage,
    "employment_issue_frameworks": _compact_section_employment_issue_frameworks,
    "lawyer_issue_matrix": _compact_section_lawyer_issue_matrix,
    "actor_and_witness_map": _compact_section_actor_and_witness_map,
    "witness_question_packs": _compact_section_witness_question_packs,
    "promise_and_contradiction_analysis": _compact_section_promise_and_contradiction_analysis,
    "lawyer_briefing_memo": _compact_section_lawyer_briefing_memo,
    "controlled_factual_drafting": _compact_section_controlled_factual_drafting,
    "case_dashboard": _compact_section_case_dashboard,
    "cross_output_consistency": _compact_section_cross_output_consistency,
    "skeptical_employer_review": _compact_section_skeptical_employer_review,
    "document_request_checklist": _compact_section_document_request_checklist,
    "chronological_pattern_analysis": _compact_section_chronological_pattern_analysis,
    "matter_evidence_index": _compact_section_matter_evidence_index,
    "overall_assessment": _compact_section_overall_assessment,
}


def _base_compact_section(section: dict[str, Any]) -> dict[str, Any]:
    entries = [entry for entry in _as_list(section.get("entries")) if isinstance(entry, dict)]
    return {
        "title": str(section.get("title") or ""),
        "status": str(section.get("status") or "insufficient_evidence"),
        "entry_count": len(entries),
        "entries": entries[:1],
        "insufficiency_reason": str(section.get("insufficiency_reason") or ""),
    }


def compact_investigation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller BA16 report representation for tight response budgets."""
    compact_sections: dict[str, Any] = {}
    sections = _as_dict(report.get("sections"))
    for section_id in SECTION_ORDER:
        section = _as_dict(sections.get(section_id))
        compact_section = _base_compact_section(section)
        compactor = _SECTION_COMPACTORS.get(section_id)
        if compactor is not None:
            compactor(section, compact_section)
        compact_sections[section_id] = compact_section
    return {
        "version": str(report.get("version") or INVESTIGATION_REPORT_VERSION),
        "report_format": str(report.get("report_format") or "investigation_briefing"),
        "interpretation_policy": _as_dict(report.get("interpretation_policy")),
        "bilingual_workflow": _as_dict(report.get("bilingual_workflow")),
        "section_order": list(report.get("section_order") or SECTION_ORDER),
        "summary": dict(report.get("summary") or {}),
        "report_highlights": _as_dict(report.get("report_highlights")),
        "deadline_warnings": _as_dict(report.get("deadline_warnings")),
        "sections": compact_sections,
    }
