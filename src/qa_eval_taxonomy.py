"""Taxonomy and remediation helpers for QA eval reports."""

from __future__ import annotations

from typing import Any

from .qa_eval_cases import QuestionCase
from .qa_eval_scoring import summarize_evaluation
from .tools.utils import ToolDepsProto


def _append_taxonomy_issue(
    flagged: dict[str, dict[str, Any]],
    *,
    category: str,
    severity: str,
    case_id: str,
    driver: str,
) -> None:
    entry = flagged.setdefault(
        category,
        {
            "category": category,
            "flagged_cases": 0,
            "failed_cases": 0,
            "weak_cases": 0,
            "case_ids": [],
            "drivers": [],
        },
    )
    if case_id not in entry["case_ids"]:
        entry["case_ids"].append(case_id)
        entry["flagged_cases"] += 1
        if severity == "failed":
            entry["failed_cases"] += 1
        else:
            entry["weak_cases"] += 1
    if driver not in entry["drivers"]:
        entry["drivers"].append(driver)


def _issue_category_for_case(case: QuestionCase, default: str) -> str:
    for category in (
        "investigation_bundle_completeness",
        "chronology_analysis",
        "behavioral_tagging",
        "comparator_analysis",
        "actor_witness_mapping",
        "document_request_quality",
        "dashboard_refresh_stability",
        "drafting_guard",
        "legal_support_product_completeness",
        "counter_indicator_handling",
        "overclaiming_guard",
        "report_completeness",
        "quote_attribution",
        "inferred_threading",
        "attachment_extraction",
        "weak_message_handling",
        "long_thread_summarization",
        "final_rendering",
        "retrieval_recall",
    ):
        if category in case.triage_tags:
            return category
    return default


def build_failure_taxonomy(cases: list[QuestionCase], results: list[dict[str, Any]]) -> dict[str, Any]:
    by_case_id = {case.id: case for case in cases}
    flagged: dict[str, dict[str, Any]] = {}

    for result in results:
        case = by_case_id.get(str(result["id"]))
        if case is None:
            continue

        case_id = case.id
        count = int(result.get("count") or 0)
        support_uid_hit = result.get("support_uid_hit")
        top_uid_match = result.get("top_uid_match")
        ambiguity_match = result.get("ambiguity_match")
        confidence_match = result.get("confidence_calibration_match")
        evidence_precision = result.get("evidence_precision")
        attachment_success = result.get("attachment_answer_success")
        attachment_text_success = result.get("attachment_text_evidence_success")
        attachment_ocr_text_success = result.get("attachment_ocr_text_evidence_success")
        weak_explained = result.get("weak_evidence_explained")
        ambiguity_reason = str(result.get("observed_ambiguity_reason") or "")

        retrieval_labeled = bool(case.expected_support_uids or case.expected_support_source_ids or case.expected_top_uid)
        support_source_id_hit = result.get("support_source_id_hit")
        if retrieval_labeled and (support_uid_hit is False or top_uid_match is False or count == 0):
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "retrieval_recall"),
                severity="failed",
                case_id=case_id,
                driver="no_supported_hit" if count == 0 or support_uid_hit is False else "top_uid_mismatch",
            )
        if retrieval_labeled and support_source_id_hit is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "retrieval_recall"),
                severity="failed",
                case_id=case_id,
                driver="support_source_grounding_missing",
            )
        if evidence_precision is not None and float(evidence_precision) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "retrieval_recall"),
                severity="weak",
                case_id=case_id,
                driver="evidence_precision_below_one",
            )
        support_source_id_recall = result.get("support_source_id_recall")
        if retrieval_labeled and support_source_id_recall is not None and float(support_source_id_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "retrieval_recall"),
                severity="weak",
                case_id=case_id,
                driver="support_source_grounding_recall_below_one",
            )
        if ambiguity_match is False or confidence_match is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "final_rendering"),
                severity="failed",
                case_id=case_id,
                driver="ambiguity_or_confidence_mismatch",
            )

        quote_precision = result.get("quote_attribution_precision")
        quote_coverage = result.get("quote_attribution_coverage")
        if quote_precision is not None and float(quote_precision) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "quote_attribution"),
                severity="weak",
                case_id=case_id,
                driver="quote_precision_below_one",
            )
        if quote_coverage is not None and float(quote_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "quote_attribution"),
                severity="failed" if float(quote_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="quote_coverage_below_one",
            )

        if result.get("thread_group_id_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "inferred_threading"),
                severity="failed",
                case_id=case_id,
                driver="thread_group_id_mismatch",
            )
        if result.get("thread_group_source_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "inferred_threading"),
                severity="failed",
                case_id=case_id,
                driver="thread_group_source_mismatch",
            )
        if attachment_success is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "attachment_extraction"),
                severity="failed",
                case_id=case_id,
                driver="attachment_answer_failed",
            )
        if attachment_text_success is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "attachment_extraction"),
                severity="weak",
                case_id=case_id,
                driver="weak_attachment_text_evidence",
            )
        if attachment_ocr_text_success is False and "attachment_ocr" in case.triage_tags:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "attachment_extraction"),
                severity="weak",
                case_id=case_id,
                driver="weak_attachment_ocr_evidence",
            )

        if case.expected_ambiguity == "insufficient" and weak_explained is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "weak_message_handling"),
                severity="failed",
                case_id=case_id,
                driver="weak_evidence_not_explained",
            )
        elif (
            ambiguity_reason
            in {"weak_scan_body", "source_shell_only", "image_only", "metadata_only_reply", "true_blank", "attachment_only"}
            and weak_explained is not True
        ):
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "weak_message_handling"),
                severity="weak",
                case_id=case_id,
                driver="weak_message_reason_without_explicit_explanation",
            )

        if result.get("long_thread_answer_present") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "long_thread_summarization"),
                severity="failed",
                case_id=case_id,
                driver="missing_long_thread_answer",
            )
        if result.get("long_thread_structure_preserved") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "long_thread_summarization"),
                severity="failed",
                case_id=case_id,
                driver="missing_long_thread_structure",
            )
        if result.get("case_bundle_present") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_case_bundle",
            )
        if result.get("investigation_blocks_present") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_investigation_blocks",
            )
        if result.get("case_bundle_support_uid_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_case_bundle_evidence",
            )
        if result.get("case_bundle_support_source_id_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_case_bundle_source_grounding",
            )
        bundle_recall = result.get("case_bundle_support_uid_recall")
        if bundle_recall is not None and float(bundle_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="weak",
                case_id=case_id,
                driver="case_bundle_recall_below_one",
            )
        bundle_source_recall = result.get("case_bundle_support_source_id_recall")
        if bundle_source_recall is not None and float(bundle_source_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="weak",
                case_id=case_id,
                driver="case_bundle_source_recall_below_one",
            )
        if result.get("multi_source_source_types_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "investigation_bundle_completeness"),
                severity="weak",
                case_id=case_id,
                driver="missing_expected_source_types",
            )
        if result.get("chronology_uid_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "chronology_analysis"),
                severity="failed",
                case_id=case_id,
                driver="missing_timeline_anchor",
            )
        chronology_recall = result.get("chronology_uid_recall")
        if chronology_recall is not None and float(chronology_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "chronology_analysis"),
                severity="weak",
                case_id=case_id,
                driver="timeline_recall_below_one",
            )
        if result.get("chronology_source_id_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "chronology_analysis"),
                severity="failed",
                case_id=case_id,
                driver="missing_timeline_source_grounding",
            )
        chronology_source_recall = result.get("chronology_source_id_recall")
        if chronology_source_recall is not None and float(chronology_source_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "chronology_analysis"),
                severity="weak",
                case_id=case_id,
                driver="timeline_source_recall_below_one",
            )
        behavior_coverage = result.get("behavior_tag_coverage")
        if behavior_coverage is not None and float(behavior_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "behavioral_tagging"),
                severity="failed" if float(behavior_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="behavior_tag_coverage_below_one",
            )
        behavior_precision = result.get("behavior_tag_precision")
        if behavior_precision is not None and float(behavior_precision) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "behavioral_tagging"),
                severity="weak",
                case_id=case_id,
                driver="behavior_tag_precision_below_one",
            )
        counter_quality = result.get("counter_indicator_quality")
        if counter_quality is not None and float(counter_quality) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "counter_indicator_handling"),
                severity="failed" if float(counter_quality) == 0.0 else "weak",
                case_id=case_id,
                driver="counter_indicator_quality_below_one",
            )
        if result.get("overclaim_guard_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "overclaiming_guard"),
                severity="failed",
                case_id=case_id,
                driver="claim_level_exceeds_label_ceiling",
            )
        if result.get("report_completeness") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "report_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_supported_report_sections",
            )
        if result.get("legal_support_product_completeness") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "legal_support_product_completeness"),
                severity="failed",
                case_id=case_id,
                driver="missing_legal_support_product",
            )
        if result.get("legal_support_grounding_hit") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "legal_support_product_completeness"),
                severity="failed",
                case_id=case_id,
                driver="ungrounded_legal_support_product",
            )
        legal_support_grounding_recall = result.get("legal_support_grounding_recall")
        if legal_support_grounding_recall is not None and float(legal_support_grounding_recall) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "legal_support_product_completeness"),
                severity="weak",
                case_id=case_id,
                driver="legal_support_grounding_recall_below_one",
            )
        comparator_coverage = result.get("comparator_matrix_coverage")
        if comparator_coverage is not None and float(comparator_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "comparator_analysis"),
                severity="failed" if float(comparator_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="comparator_matrix_coverage_below_one",
            )
        dashboard_coverage = result.get("dashboard_card_coverage")
        if dashboard_coverage is not None and float(dashboard_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "dashboard_refresh_stability"),
                severity="failed" if float(dashboard_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="dashboard_card_coverage_below_one",
            )
        actor_coverage = result.get("actor_map_coverage")
        if actor_coverage is not None and float(actor_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "actor_witness_mapping"),
                severity="failed" if float(actor_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="actor_map_coverage_below_one",
            )
        checklist_coverage = result.get("checklist_group_coverage")
        if checklist_coverage is not None and float(checklist_coverage) < 1.0:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "document_request_quality"),
                severity="failed" if float(checklist_coverage) == 0.0 else "weak",
                case_id=case_id,
                driver="checklist_group_coverage_below_one",
            )
        if result.get("drafting_ceiling_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "drafting_guard"),
                severity="failed",
                case_id=case_id,
                driver="drafting_ceiling_mismatch",
            )
        if result.get("draft_section_completeness") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "drafting_guard"),
                severity="failed",
                case_id=case_id,
                driver="missing_controlled_draft_sections",
            )
        for metric, category, failed_driver, weak_driver in (
            (
                "benchmark_actor_recovery",
                _issue_category_for_case(case, "retrieval_recall"),
                "benchmark_actor_recovery_zero",
                "benchmark_actor_recovery_partial",
            ),
            (
                "benchmark_issue_family_recovery",
                _issue_category_for_case(case, "retrieval_recall"),
                "benchmark_issue_family_recovery_zero",
                "benchmark_issue_family_recovery_partial",
            ),
            (
                "benchmark_chronology_anchor_recovery",
                _issue_category_for_case(case, "chronology_analysis"),
                "benchmark_chronology_anchor_recovery_zero",
                "benchmark_chronology_anchor_recovery_partial",
            ),
            (
                "benchmark_manifest_link_recovery",
                _issue_category_for_case(case, "investigation_bundle_completeness"),
                "benchmark_manifest_link_recovery_zero",
                "benchmark_manifest_link_recovery_partial",
            ),
            (
                "benchmark_report_recovery",
                _issue_category_for_case(case, "report_completeness"),
                "benchmark_report_recovery_zero",
                "benchmark_report_recovery_partial",
            ),
        ):
            benchmark_coverage = result.get(metric)
            benchmark_total = result.get(f"{metric}_total")
            if benchmark_coverage is None:
                continue
            if benchmark_total is not None and int(benchmark_total) <= 0:
                continue
            if float(benchmark_coverage) == 0.0:
                _append_taxonomy_issue(
                    flagged,
                    category=category,
                    severity="failed",
                    case_id=case_id,
                    driver=failed_driver,
                )
            elif float(benchmark_coverage) < 1.0:
                _append_taxonomy_issue(
                    flagged,
                    category=category,
                    severity="weak",
                    case_id=case_id,
                    driver=weak_driver,
                )
        if result.get("answer_content_match") is False:
            _append_taxonomy_issue(
                flagged,
                category=_issue_category_for_case(case, "final_rendering"),
                severity="failed",
                case_id=case_id,
                driver="answer_content_mismatch",
            )
        for metric, category, driver in (
            ("forbidden_support_ids_excluded", _issue_category_for_case(case, "retrieval_recall"), "forbidden_support_present"),
            ("forbidden_issue_ids_excluded", _issue_category_for_case(case, "overclaiming_guard"), "forbidden_issue_present"),
            ("forbidden_actor_ids_excluded", _issue_category_for_case(case, "actor_witness_mapping"), "forbidden_actor_present"),
            (
                "forbidden_dashboard_cards_excluded",
                _issue_category_for_case(case, "dashboard_refresh_stability"),
                "forbidden_dashboard_card_present",
            ),
            (
                "forbidden_checklist_groups_excluded",
                _issue_category_for_case(case, "document_request_quality"),
                "forbidden_checklist_group_present",
            ),
        ):
            if result.get(metric) is False:
                _append_taxonomy_issue(
                    flagged,
                    category=category,
                    severity="failed",
                    case_id=case_id,
                    driver=driver,
                )

    ranked_categories = sorted(
        flagged.values(),
        key=lambda item: (-int(item["failed_cases"]), -int(item["weak_cases"]), str(item["category"])),
    )
    return {
        "total_flagged_cases": len({case_id for item in flagged.values() for case_id in item["case_ids"]}),
        "categories": {item["category"]: item for item in ranked_categories},
        "ranked_categories": ranked_categories,
    }


def _recommended_track_for_category(category: str) -> dict[str, str]:
    mapping = {
        "retrieval_recall": {
            "track": "retrieval_quality",
            "next_step": "define and implement retrieval-quality remediation after AQ20",
        },
        "investigation_bundle_completeness": {
            "track": "BA15",
            "next_step": "improve case-bundle completeness and investigation readiness on synthetic corpus data",
        },
        "chronology_analysis": {
            "track": "BA10",
            "next_step": "improve chronology assembly and timeline-anchor retention for behavioural-analysis cases",
        },
        "behavioral_tagging": {
            "track": "BA6",
            "next_step": "improve message-level behaviour tagging precision and recall on labeled cases",
        },
        "counter_indicator_handling": {
            "track": "BA13",
            "next_step": "improve counter-indicator surfacing and alternative-explanation carry-through",
        },
        "overclaiming_guard": {
            "track": "BA17",
            "next_step": "tighten interpretation-policy claim ceilings and overclaim prevention",
        },
        "report_completeness": {
            "track": "BA16",
            "next_step": "improve investigation report section completeness for labeled review cases",
        },
        "legal_support_product_completeness": {
            "track": "LS1",
            "next_step": "restore missing stable legal-support products in the case-analysis payload",
        },
        "comparator_analysis": {
            "track": "LS2",
            "next_step": "repair comparator-matrix coverage and expected lawyer-usable comparison rows",
        },
        "actor_witness_mapping": {
            "track": "LS3",
            "next_step": "repair actor and witness mapping coverage from the shared matter entities",
        },
        "document_request_quality": {
            "track": "LS4",
            "next_step": "repair checklist grouping and preservation-request quality in the legal-support outputs",
        },
        "dashboard_refresh_stability": {
            "track": "LS5",
            "next_step": "restore expected dashboard cards and refreshable summary behavior",
        },
        "drafting_guard": {
            "track": "LS6",
            "next_step": "repair allegation-ceiling enforcement and controlled-draft section completeness",
        },
        "final_rendering": {
            "track": "answer_rendering_tuning",
            "next_step": "tighten answer rendering after retrieval quality improves",
        },
        "attachment_extraction": {"track": "AQ21", "next_step": "improve OCR and strong-text attachment evidence"},
        "weak_message_handling": {
            "track": "weak_message_followup",
            "next_step": "improve weak-evidence phrasing and recovery on live cases",
        },
        "inferred_threading": {"track": "AQ23", "next_step": "validate and improve inferred-thread impact on live data"},
        "quote_attribution": {"track": "AQ22", "next_step": "improve quote-attribution recall while preserving precision"},
        "long_thread_summarization": {
            "track": "AQ24",
            "next_step": "validate and improve long-thread answer survival under live budget pressure",
        },
    }
    return mapping.get(
        category, {"track": "manual_triage", "next_step": "inspect representative failures and define a bounded follow-up"}
    )


def build_remediation_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    taxonomy = report.get("failure_taxonomy")
    if not isinstance(summary, dict) or not isinstance(taxonomy, dict):
        raise ValueError("report must contain summary and failure_taxonomy objects")
    ranked_categories = taxonomy.get("ranked_categories")
    if not isinstance(ranked_categories, list):
        raise ValueError("failure_taxonomy.ranked_categories must be a list")

    ranked_targets: list[dict[str, Any]] = []
    for item in ranked_categories:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "")
        flagged_cases = int(item.get("flagged_cases") or 0)
        failed_cases = int(item.get("failed_cases") or 0)
        weak_cases = int(item.get("weak_cases") or 0)
        recommendation = _recommended_track_for_category(category)
        ranked_targets.append(
            {
                "category": category,
                "priority_score": failed_cases * 3 + weak_cases * 2 + flagged_cases,
                "flagged_cases": flagged_cases,
                "failed_cases": failed_cases,
                "weak_cases": weak_cases,
                "case_ids": [str(case_id) for case_id in item.get("case_ids", [])],
                "drivers": [str(driver) for driver in item.get("drivers", [])],
                "recommended_track": recommendation["track"],
                "recommended_next_step": recommendation["next_step"],
            }
        )
    ranked_targets.sort(
        key=lambda item: (
            int(item.get("priority_score") or 0),
            int(item.get("failed_cases") or 0),
            int(item.get("flagged_cases") or 0),
        ),
        reverse=True,
    )

    return {
        "total_cases": int(summary.get("total_cases") or report.get("total_cases") or 0),
        "bucket_counts": dict(summary.get("bucket_counts") or {}),
        "top_1_correctness": dict(summary.get("top_1_correctness") or {}),
        "support_uid_hit_top_3": dict(summary.get("support_uid_hit_top_3") or {}),
        "confidence_calibration_match": dict(summary.get("confidence_calibration_match") or {}),
        "failure_taxonomy": {
            "total_flagged_cases": int(taxonomy.get("total_flagged_cases") or 0),
            "ranked_categories": ranked_targets,
        },
        "immediate_next_targets": [
            {
                "category": str(item.get("category") or ""),
                "recommended_track": str(item.get("recommended_track") or ""),
                "recommended_next_step": str(item.get("recommended_next_step") or ""),
            }
            for item in ranked_targets[:3]
        ],
    }


def _scalar_count(conn: Any, query: str) -> int:
    row = conn.execute(query).fetchone()
    if not row:
        return 0
    if isinstance(row, dict):
        return int(row.get("count") or 0)
    return int(row[0] or 0)


def build_investigation_corpus_readiness(
    *,
    cases: list[QuestionCase],
    results: list[dict[str, Any]],
    live_deps: ToolDepsProto | None,
) -> dict[str, Any]:
    case_scoped_cases = [case for case in cases if case.case_scope is not None]
    total_expected_bundle_uids = sum(len(case.expected_case_bundle_uids) for case in case_scoped_cases)
    readiness: dict[str, Any] = {
        "live_backend": getattr(live_deps, "live_backend", None) if live_deps is not None else None,
        "case_scope_case_count": len(case_scoped_cases),
        "expected_case_bundle_uid_count": total_expected_bundle_uids,
        "corpus_populated": False,
        "supports_case_analysis": False,
        "known_blockers": [],
    }
    if live_deps is None:
        readiness["known_blockers"] = ["no_live_deps"]
        return readiness
    db = live_deps.get_email_db()
    conn = getattr(db, "conn", None)
    if conn is None:
        readiness["known_blockers"] = ["missing_sqlite_connection"]
        return readiness
    total_emails = _scalar_count(conn, "SELECT COUNT(*) FROM emails")
    emails_with_segments_count = _scalar_count(conn, "SELECT COUNT(DISTINCT email_uid) FROM message_segments")
    attachment_email_count = _scalar_count(conn, "SELECT COUNT(*) FROM emails WHERE COALESCE(has_attachments, 0) != 0")
    readiness.update(
        {
            "total_emails": total_emails,
            "emails_with_segments_count": emails_with_segments_count,
            "attachment_email_count": attachment_email_count,
        }
    )
    if total_emails > 0 and emails_with_segments_count > 0:
        readiness["corpus_populated"] = True
    blockers: list[str] = []
    if total_emails <= 0:
        blockers.append("empty_email_corpus")
    if emails_with_segments_count <= 0:
        blockers.append("missing_message_segments")
    if not case_scoped_cases:
        blockers.append("no_case_scoped_eval_cases")
    summary = summarize_evaluation(results)
    case_bundle_metric = dict(summary.get("case_bundle_present") or {})
    investigation_blocks_metric = dict(summary.get("investigation_blocks_present") or {})
    readiness["supports_case_analysis"] = (
        readiness["corpus_populated"]
        and int(case_bundle_metric.get("scorable") or 0) > 0
        and int(case_bundle_metric.get("failed") or 0) == 0
        and int(investigation_blocks_metric.get("failed") or 0) == 0
    )
    if not readiness["supports_case_analysis"] and int(case_bundle_metric.get("scorable") or 0) > 0:
        blockers.append("case_analysis_blocks_incomplete")
    readiness["known_blockers"] = blockers
    return readiness
