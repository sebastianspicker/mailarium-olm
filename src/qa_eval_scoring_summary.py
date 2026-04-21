# mypy: disable-error-code=name-defined
"""Split QA evaluation scoring helpers (qa_eval_scoring_summary)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .qa_eval_cases import QuestionCase

_ANSWER_TERM_RE = re.compile(r"[0-9a-zA-ZäöüÄÖÜß._-]+")
_ANSWER_STOPWORDS = {
    "aber",
    "after",
    "and",
    "auch",
    "because",
    "beim",
    "beziehungsweise",
    "dann",
    "dass",
    "dem",
    "denn",
    "der",
    "des",
    "die",
    "dies",
    "does",
    "eine",
    "einer",
    "eines",
    "evidence",
    "from",
    "have",
    "into",
    "kein",
    "keine",
    "likely",
    "message",
    "nach",
    "oder",
    "over",
    "says",
    "sein",
    "some",
    "that",
    "their",
    "there",
    "these",
    "this",
    "under",
    "used",
    "with",
    "without",
}

# ruff: noqa: F401,F821


def summarize_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize evaluation outcomes across all scored cases."""
    buckets = Counter(result["bucket"] for result in results)

    def _metric_summary(metric: str) -> dict[str, int]:
        scorable = [result for result in results if result.get(metric) is not None]
        passed = [result for result in scorable if result.get(metric) is True]
        return {
            "scorable": len(scorable),
            "passed": len(passed),
            "failed": len(scorable) - len(passed),
        }

    return {
        "total_cases": len(results),
        "bucket_counts": dict(sorted(buckets.items())),
        "top_1_correctness": _metric_summary("top_1_correctness"),
        "support_uid_hit": _metric_summary("support_uid_hit"),
        "support_uid_hit_top_3": _metric_summary("support_uid_hit_top_3"),
        "support_source_id_hit": _metric_summary("support_source_id_hit"),
        "support_uid_recall": _average_metric(results, "support_uid_recall"),
        "support_source_id_recall": _average_metric(results, "support_source_id_recall"),
        "evidence_precision": _average_metric(results, "evidence_precision"),
        "top_uid_match": _metric_summary("top_uid_match"),
        "ambiguity_match": _metric_summary("ambiguity_match"),
        "confidence_calibration_match": _metric_summary("confidence_calibration_match"),
        "attachment_support_uid_hit": _metric_summary("attachment_support_uid_hit"),
        "attachment_answer_success": _metric_summary("attachment_answer_success"),
        "attachment_text_evidence_success": _metric_summary("attachment_text_evidence_success"),
        "attachment_ocr_text_evidence_success": _metric_summary("attachment_ocr_text_evidence_success"),
        "weak_evidence_explained": _metric_summary("weak_evidence_explained"),
        "quote_attribution_precision": _average_metric(results, "quote_attribution_precision"),
        "quote_attribution_coverage": _average_metric(results, "quote_attribution_coverage"),
        "thread_group_id_match": _metric_summary("thread_group_id_match"),
        "thread_group_source_match": _metric_summary("thread_group_source_match"),
        "long_thread_answer_present": _metric_summary("long_thread_answer_present"),
        "long_thread_structure_preserved": _metric_summary("long_thread_structure_preserved"),
        "case_bundle_present": _metric_summary("case_bundle_present"),
        "investigation_blocks_present": _metric_summary("investigation_blocks_present"),
        "case_bundle_support_uid_hit": _metric_summary("case_bundle_support_uid_hit"),
        "case_bundle_support_uid_recall": _average_metric(results, "case_bundle_support_uid_recall"),
        "case_bundle_support_source_id_hit": _metric_summary("case_bundle_support_source_id_hit"),
        "case_bundle_support_source_id_recall": _average_metric(results, "case_bundle_support_source_id_recall"),
        "multi_source_source_types_match": _metric_summary("multi_source_source_types_match"),
        "chronology_uid_hit": _metric_summary("chronology_uid_hit"),
        "chronology_uid_recall": _average_metric(results, "chronology_uid_recall"),
        "chronology_source_id_hit": _metric_summary("chronology_source_id_hit"),
        "chronology_source_id_recall": _average_metric(results, "chronology_source_id_recall"),
        "behavior_tag_coverage": _average_metric(results, "behavior_tag_coverage"),
        "behavior_tag_precision": _average_metric(results, "behavior_tag_precision"),
        "counter_indicator_quality": _average_metric(results, "counter_indicator_quality"),
        "overclaim_guard_match": _metric_summary("overclaim_guard_match"),
        "report_completeness": _metric_summary("report_completeness"),
        "legal_support_product_completeness": _metric_summary("legal_support_product_completeness"),
        "legal_support_grounding_hit": _metric_summary("legal_support_grounding_hit"),
        "legal_support_grounding_recall": _average_metric(results, "legal_support_grounding_recall"),
        "comparator_matrix_coverage": _average_metric(results, "comparator_matrix_coverage"),
        "dashboard_card_coverage": _average_metric(results, "dashboard_card_coverage"),
        "actor_map_coverage": _average_metric(results, "actor_map_coverage"),
        "checklist_group_coverage": _average_metric(results, "checklist_group_coverage"),
        "drafting_ceiling_match": _metric_summary("drafting_ceiling_match"),
        "draft_section_completeness": _metric_summary("draft_section_completeness"),
        "answer_content_match": _metric_summary("answer_content_match"),
        "archive_harvest_coverage_pass": _metric_summary("archive_harvest_coverage_pass"),
        "archive_harvest_quality_pass": _metric_summary("archive_harvest_quality_pass"),
        "archive_harvest_mixed_source_present": _metric_summary("archive_harvest_mixed_source_present"),
        "archive_harvest_later_round_recovery": _metric_summary("archive_harvest_later_round_recovery"),
        "forbidden_support_ids_excluded": _metric_summary("forbidden_support_ids_excluded"),
        "forbidden_issue_ids_excluded": _metric_summary("forbidden_issue_ids_excluded"),
        "forbidden_actor_ids_excluded": _metric_summary("forbidden_actor_ids_excluded"),
        "forbidden_dashboard_cards_excluded": _metric_summary("forbidden_dashboard_cards_excluded"),
        "forbidden_checklist_groups_excluded": _metric_summary("forbidden_checklist_groups_excluded"),
        "benchmark_actor_recovery": _average_metric(results, "benchmark_actor_recovery"),
        "benchmark_issue_family_recovery": _average_metric(results, "benchmark_issue_family_recovery"),
        "benchmark_chronology_anchor_recovery": _average_metric(results, "benchmark_chronology_anchor_recovery"),
        "benchmark_manifest_link_recovery": _average_metric(results, "benchmark_manifest_link_recovery"),
        "benchmark_report_recovery": _average_metric(results, "benchmark_report_recovery"),
    }


__all__ = [
    "_ANSWER_STOPWORDS",
    "_ANSWER_TERM_RE",
    "summarize_evaluation",
]
