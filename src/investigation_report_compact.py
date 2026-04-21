"""Compact investigation-report rendering for tight response budgets."""

from __future__ import annotations

from typing import Any

from .investigation_report_constants import INVESTIGATION_REPORT_VERSION, SECTION_ORDER
from .investigation_report_sections import _as_dict, _as_list


def compact_investigation_report(report: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller BA16 report representation for tight response budgets."""
    compact_sections: dict[str, Any] = {}
    sections = _as_dict(report.get("sections"))
    for section_id in SECTION_ORDER:
        section = _as_dict(sections.get(section_id))
        entries = [entry for entry in _as_list(section.get("entries")) if isinstance(entry, dict)]
        compact_section = {
            "title": str(section.get("title") or ""),
            "status": str(section.get("status") or "insufficient_evidence"),
            "entry_count": len(entries),
            "entries": entries[:1],
            "insufficiency_reason": str(section.get("insufficiency_reason") or ""),
        }
        if section_id == "evidence_triage":
            compact_section["summary"] = dict(section.get("summary") or {})
            for field in ("direct_evidence", "reasonable_inference", "unresolved_points", "missing_proof"):
                compact_section[field] = [entry for entry in _as_list(section.get(field)) if isinstance(entry, dict)][:1]
        if section_id == "employment_issue_frameworks":
            compact_section["issue_tracks"] = [
                entry for entry in _as_list(section.get("issue_tracks")) if isinstance(entry, dict)
            ][:2]
            compact_section["issue_tag_summary"] = _as_dict(section.get("issue_tag_summary"))
        if section_id == "lawyer_issue_matrix":
            lawyer_matrix = _as_dict(section.get("lawyer_issue_matrix"))
            compact_section["lawyer_issue_matrix"] = {
                "version": str(lawyer_matrix.get("version") or ""),
                "row_count": int(lawyer_matrix.get("row_count") or 0),
                "bilingual_rendering": dict(lawyer_matrix.get("bilingual_rendering") or {}),
                "rows": [
                    {
                        "issue_id": str(row.get("issue_id") or ""),
                        "title": str(row.get("title") or ""),
                        "legal_relevance_status": str(row.get("legal_relevance_status") or ""),
                        "urgency_or_deadline_relevance": str(row.get("urgency_or_deadline_relevance") or ""),
                        "timing_warning_ids": [str(item) for item in _as_list(row.get("timing_warning_ids")) if item][:2],
                        "strongest_documents": [
                            item for item in _as_list(row.get("strongest_documents")) if isinstance(item, dict)
                        ][:1],
                        "not_legal_advice": bool(row.get("not_legal_advice")),
                    }
                    for row in sorted(
                        [row for row in _as_list(lawyer_matrix.get("rows")) if isinstance(row, dict)],
                        key=lambda item: (
                            0 if str(item.get("legal_relevance_status") or "") == "supported_for_further_review" else 1,
                            -len(_as_list(item.get("strongest_documents"))),
                            -len(_as_list(item.get("supporting_source_ids"))),
                            str(item.get("issue_id") or ""),
                        ),
                    )[:2]
                    if isinstance(row, dict)
                ],
            }
        if section_id == "actor_and_witness_map":
            actor_map = _as_dict(section.get("actor_map"))
            witness_map = _as_dict(section.get("witness_map"))
            compact_section["actor_map"] = {
                "actor_count": int(actor_map.get("actor_count") or 0),
                "summary": dict(actor_map.get("summary") or {}),
                "actors": [
                    {
                        "actor_id": str(actor.get("actor_id") or ""),
                        "name": str(actor.get("name") or ""),
                        "status": dict(actor.get("status") or {}),
                        "helps_hurts_mixed": str(actor.get("helps_hurts_mixed") or ""),
                    }
                    for actor in _as_list(actor_map.get("actors"))[:2]
                    if isinstance(actor, dict)
                ],
            }
            compact_section["witness_map"] = {
                "primary_decision_makers": [
                    dict(item) for item in _as_list(witness_map.get("primary_decision_makers"))[:2] if isinstance(item, dict)
                ],
                "potentially_independent_witnesses": [
                    dict(item)
                    for item in _as_list(witness_map.get("potentially_independent_witnesses"))[:2]
                    if isinstance(item, dict)
                ],
                "coordination_points": [
                    dict(item) for item in _as_list(witness_map.get("coordination_points"))[:2] if isinstance(item, dict)
                ],
            }
        if section_id == "witness_question_packs":
            packs = _as_dict(section.get("witness_question_packs"))
            compact_section["witness_question_packs"] = {
                "version": str(packs.get("version") or ""),
                "pack_count": int(packs.get("pack_count") or 0),
                "summary": dict(packs.get("summary") or {}),
                "packs": [
                    {
                        "pack_id": str(item.get("pack_id") or ""),
                        "actor_id": str(item.get("actor_id") or ""),
                        "actor_name": str(item.get("actor_name") or ""),
                        "pack_type": str(item.get("pack_type") or ""),
                        "likely_knowledge_areas": [str(value) for value in _as_list(item.get("likely_knowledge_areas")) if value][
                            :2
                        ],
                        "suggested_questions": [str(value) for value in _as_list(item.get("suggested_questions")) if value][:2],
                    }
                    for item in _as_list(packs.get("packs"))[:2]
                    if isinstance(item, dict)
                ],
            }
        if section_id == "promise_and_contradiction_analysis":
            analysis = _as_dict(section.get("promise_contradiction_analysis"))
            compact_section["promise_contradiction_analysis"] = {
                "version": str(analysis.get("version") or ""),
                "summary": dict(analysis.get("summary") or {}),
                "promises_vs_actions": [
                    dict(item) for item in _as_list(analysis.get("promises_vs_actions"))[:2] if isinstance(item, dict)
                ],
                "omission_rows": [dict(item) for item in _as_list(analysis.get("omission_rows"))[:2] if isinstance(item, dict)],
                "contradiction_table": [
                    dict(item) for item in _as_list(analysis.get("contradiction_table"))[:2] if isinstance(item, dict)
                ],
            }
        if section_id == "lawyer_briefing_memo":
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
        if section_id == "controlled_factual_drafting":
            drafting = _as_dict(section.get("controlled_factual_drafting"))
            preflight = _as_dict(drafting.get("framing_preflight"))
            draft = _as_dict(drafting.get("controlled_draft"))
            draft_sections = _as_dict(draft.get("sections"))
            compact_section["controlled_factual_drafting"] = {
                "version": str(drafting.get("version") or ""),
                "drafting_format": str(drafting.get("drafting_format") or ""),
                "summary": dict(drafting.get("summary") or {}),
                "bilingual_rendering": dict(drafting.get("bilingual_rendering") or {}),
                "framing_preflight": {
                    "objective_of_draft": str(preflight.get("objective_of_draft") or ""),
                    "legal_and_factual_risks": [
                        dict(item) for item in _as_list(preflight.get("legal_and_factual_risks"))[:2] if isinstance(item, dict)
                    ],
                    "strongest_framing": [
                        dict(item) for item in _as_list(preflight.get("strongest_framing"))[:2] if isinstance(item, dict)
                    ],
                    "safest_framing": [
                        dict(item) for item in _as_list(preflight.get("safest_framing"))[:2] if isinstance(item, dict)
                    ],
                    "allegation_ceiling": dict(preflight.get("allegation_ceiling") or {}),
                },
                "controlled_draft": {
                    "audience": str(draft.get("audience") or ""),
                    "tone": str(draft.get("tone") or ""),
                    "allegation_ceiling_applied": str(draft.get("allegation_ceiling_applied") or ""),
                    "sections": {
                        section_name: [
                            dict(item) for item in _as_list(draft_sections.get(section_name))[:2] if isinstance(item, dict)
                        ]
                        for section_name in (
                            "established_facts",
                            "concerns",
                            "requests_for_clarification",
                            "formal_demands",
                        )
                    },
                },
            }
        if section_id == "case_dashboard":
            dashboard = _as_dict(section.get("case_dashboard"))
            cards = _as_dict(dashboard.get("cards"))
            compact_section["case_dashboard"] = {
                "version": str(dashboard.get("version") or ""),
                "dashboard_format": str(dashboard.get("dashboard_format") or ""),
                "summary": dict(dashboard.get("summary") or {}),
                "bilingual_rendering": dict(dashboard.get("bilingual_rendering") or {}),
                "cards": {
                    card_id: [dict(item) for item in _as_list(cards.get(card_id))[:2] if isinstance(item, dict)]
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
        if section_id == "cross_output_consistency":
            consistency = _as_dict(section.get("cross_output_consistency"))
            compact_section["cross_output_consistency"] = {
                "version": str(consistency.get("version") or ""),
                "overall_status": str(consistency.get("overall_status") or ""),
                "summary": dict(consistency.get("summary") or {}),
                "checks": [
                    {
                        "check_id": str(item.get("check_id") or ""),
                        "status": str(item.get("status") or ""),
                        "summary": str(item.get("summary") or ""),
                        "affected_outputs": [str(output) for output in _as_list(item.get("affected_outputs")) if output][:3],
                    }
                    for item in _as_list(consistency.get("checks"))[:3]
                    if isinstance(item, dict)
                ],
            }
        if section_id == "skeptical_employer_review":
            skeptical_review = _as_dict(section.get("skeptical_employer_review"))
            compact_section["skeptical_employer_review"] = {
                "version": str(skeptical_review.get("version") or ""),
                "summary": dict(skeptical_review.get("summary") or {}),
                "weaknesses": [
                    {
                        "weakness_id": str(item.get("weakness_id") or ""),
                        "category": str(item.get("category") or ""),
                        "critique": str(item.get("critique") or ""),
                        "repair_guidance": {
                            "how_to_fix": str(_as_dict(item.get("repair_guidance")).get("how_to_fix") or ""),
                            "cautious_rewrite": str(_as_dict(item.get("repair_guidance")).get("cautious_rewrite") or ""),
                        },
                    }
                    for item in _as_list(skeptical_review.get("weaknesses"))[:2]
                    if isinstance(item, dict)
                ],
            }
        if section_id == "document_request_checklist":
            checklist = _as_dict(section.get("document_request_checklist"))
            compact_section["document_request_checklist"] = {
                "version": str(checklist.get("version") or ""),
                "group_count": int(checklist.get("group_count") or 0),
                "deadline_warnings": _as_dict(checklist.get("deadline_warnings")),
                "groups": [
                    {
                        "group_id": str(group.get("group_id") or ""),
                        "title": str(group.get("title") or ""),
                        "timing_warning_ids": [str(item) for item in _as_list(group.get("timing_warning_ids")) if item][:2],
                        "item_count": int(group.get("item_count") or len(_as_list(group.get("items")))),
                        "items": [
                            {
                                "item_id": str(item.get("item_id") or ""),
                                "request": str(item.get("request") or ""),
                                "likely_custodian": str(item.get("likely_custodian") or ""),
                                "urgency": str(item.get("urgency") or ""),
                                "risk_of_loss": str(item.get("risk_of_loss") or ""),
                            }
                            for item in _as_list(group.get("items"))[:1]
                            if isinstance(item, dict)
                        ],
                    }
                    for group in _as_list(checklist.get("groups"))[:2]
                    if isinstance(group, dict)
                ],
            }
        if section_id == "chronological_pattern_analysis":
            chronology = _as_dict(section.get("master_chronology"))
            chronology_summary = _as_dict(chronology.get("summary"))
            source_conflict_registry = _as_dict(chronology_summary.get("source_conflict_registry"))
            compact_section["master_chronology"] = {
                "version": str(chronology.get("version") or ""),
                "entry_count": int(chronology.get("entry_count") or 0),
                "summary": {
                    "date_precision_counts": dict(chronology_summary.get("date_precision_counts") or {}),
                    "source_linked_entry_count": int(chronology_summary.get("source_linked_entry_count") or 0),
                    "date_range": dict(chronology_summary.get("date_range") or {}),
                    "date_gap_count": int(chronology_summary.get("date_gap_count") or 0),
                    "largest_gap_days": int(chronology_summary.get("largest_gap_days") or 0),
                    "source_conflict_registry": {
                        "conflict_count": int(source_conflict_registry.get("conflict_count") or 0),
                        "conflict_ids": [
                            str(item.get("conflict_id") or "")
                            for item in _as_list(source_conflict_registry.get("conflicts"))[:3]
                            if isinstance(item, dict) and str(item.get("conflict_id") or "")
                        ],
                    },
                },
                "date_gaps_and_unexplained_sequences": [
                    {
                        "gap_id": str(item.get("gap_id") or ""),
                        "priority": str(item.get("priority") or ""),
                        "gap_days": int(item.get("gap_days") or 0),
                        "missing_bridge_record_suggestions": [
                            str(value) for value in _as_list(item.get("missing_bridge_record_suggestions")) if value
                        ][:2],
                    }
                    for item in _as_list(chronology_summary.get("date_gaps_and_unexplained_sequences"))[:2]
                    if isinstance(item, dict)
                ],
                "entries": [
                    {
                        "chronology_id": str(item.get("chronology_id") or ""),
                        "date": str(item.get("date") or ""),
                        "title": str(item.get("title") or ""),
                        "source_ids": [
                            str(value) for value in _as_list(_as_dict(item.get("source_linkage")).get("source_ids")) if value
                        ][:3],
                        "supporting_uids": [
                            str(value) for value in _as_list(_as_dict(item.get("source_linkage")).get("supporting_uids")) if value
                        ][:3],
                        "linked_source_ids": [
                            str(value)
                            for value in _as_list(_as_dict(item.get("source_linkage")).get("linked_source_ids"))
                            if value
                        ][:3],
                        "supporting_citation_ids": [
                            str(value)
                            for value in _as_list(_as_dict(item.get("source_linkage")).get("supporting_citation_ids"))
                            if value
                        ][:3],
                        "evidence_handles": [
                            str(value)
                            for value in _as_list(_as_dict(item.get("source_linkage")).get("evidence_handles"))
                            if value
                        ][:3],
                    }
                    for item in _as_list(chronology.get("entries"))[:2]
                    if isinstance(item, dict)
                ],
                "_truncated": int(chronology.get("_truncated") or 0),
            }
            retaliation_timeline = _as_dict(section.get("retaliation_timeline_assessment"))
            compact_section["retaliation_timeline_assessment"] = {
                "version": str(retaliation_timeline.get("version") or ""),
                "protected_activity_timeline": [
                    dict(entry)
                    for entry in _as_list(retaliation_timeline.get("protected_activity_timeline"))[:1]
                    if isinstance(entry, dict)
                ],
                "temporal_correlation_analysis": [
                    dict(entry)
                    for entry in _as_list(retaliation_timeline.get("temporal_correlation_analysis"))[:1]
                    if isinstance(entry, dict)
                ],
                "overall_evidentiary_rating": dict(retaliation_timeline.get("overall_evidentiary_rating") or {}),
            }
        if section_id == "matter_evidence_index":
            matter_index = _as_dict(section.get("matter_evidence_index"))
            matter_summary = _as_dict(matter_index.get("summary"))
            compact_section["matter_evidence_index"] = {
                "version": str(matter_index.get("version") or ""),
                "row_count": int(matter_index.get("row_count") or 0),
                "summary": {
                    "exhibit_strength_counts": dict(matter_summary.get("exhibit_strength_counts") or {}),
                    "readiness_counts": dict(
                        matter_summary.get("exhibit_readiness_counts") or matter_summary.get("readiness_counts") or {}
                    ),
                    "source_conflict_status_counts": dict(matter_summary.get("source_conflict_status_counts") or {}),
                    "missing_exhibit_count": int(matter_summary.get("missing_exhibit_count") or 0),
                },
                "top_15_exhibits": [
                    {
                        "exhibit_id": str(row.get("exhibit_id") or ""),
                        "source_id": str(row.get("source_id") or ""),
                        "priority_score": int(row.get("priority_score") or 0),
                        "strength": str(row.get("strength") or ""),
                        "readiness": str(row.get("readiness") or ""),
                        "source_conflict_status": str(row.get("source_conflict_status") or ""),
                        "supporting_source_ids": [str(item) for item in _as_list(row.get("supporting_source_ids")) if item][:3],
                        "supporting_uids": [str(item) for item in _as_list(row.get("supporting_uids")) if item][:3],
                        "supporting_citation_ids": [str(item) for item in _as_list(row.get("supporting_citation_ids")) if item][
                            :3
                        ],
                    }
                    for row in _as_list(matter_index.get("top_15_exhibits"))[:3]
                    if isinstance(row, dict)
                ],
                "rows": [
                    {
                        "exhibit_id": str(row.get("exhibit_id") or ""),
                        "source_id": str(row.get("source_id") or ""),
                        "source_conflict_status": str(row.get("source_conflict_status") or ""),
                        "supporting_source_ids": [str(item) for item in _as_list(row.get("supporting_source_ids")) if item][:3],
                        "supporting_uids": [str(item) for item in _as_list(row.get("supporting_uids")) if item][:3],
                        "linked_source_ids": [str(item) for item in _as_list(row.get("linked_source_ids")) if item][:3],
                        "source_conflict_ids": [str(item) for item in _as_list(row.get("source_conflict_ids")) if item][:3],
                        "promotability_status": str(row.get("promotability_status") or ""),
                        "exhibit_reliability": {
                            "strength": str(_as_dict(row.get("exhibit_reliability")).get("strength") or ""),
                            "next_step_logic": {
                                "readiness": str(
                                    _as_dict(_as_dict(row.get("exhibit_reliability")).get("next_step_logic")).get("readiness")
                                    or ""
                                ),
                            },
                        },
                        "supporting_citation_ids": [str(item) for item in _as_list(row.get("supporting_citation_ids")) if item],
                    }
                    for row in sorted(
                        [row for row in _as_list(matter_index.get("rows")) if isinstance(row, dict)],
                        key=lambda item: (
                            0 if str(item.get("source_conflict_status") or "") == "disputed" else 1,
                            -len(_as_list(item.get("supporting_source_ids"))),
                            -len(_as_list(item.get("supporting_citation_ids"))),
                            str(item.get("source_id") or ""),
                        ),
                    )[:1]
                    if isinstance(row, dict)
                ],
            }
        if section_id == "overall_assessment":
            compact_section["primary_assessment"] = str(section.get("primary_assessment") or "insufficient_evidence")
            compact_section["secondary_plausible_interpretations"] = [
                str(item) for item in _as_list(section.get("secondary_plausible_interpretations")) if item
            ]
            compact_section["assessment_strength"] = str(section.get("assessment_strength") or "insufficient_evidence")
            compact_section["downgrade_reasons"] = [str(item) for item in _as_list(section.get("downgrade_reasons")) if item]
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
