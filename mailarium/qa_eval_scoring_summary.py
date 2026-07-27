"""Summary helpers for generic QA evaluation metrics."""

from collections import Counter
from typing import Any

from .qa_eval_scoring_core import _average_metric


def _boolean_metric_summary(results: list[dict[str, Any]], metric: str) -> dict[str, int]:
    scorable = [result for result in results if result.get(metric) is not None]
    passed = sum(result.get(metric) is True for result in scorable)
    return {"scorable": len(scorable), "passed": passed, "failed": len(scorable) - passed}


def summarize_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize retrieval, answer, quote, thread, and attachment outcomes."""
    buckets = Counter(str(result["bucket"]) for result in results)
    boolean_metrics = (
        "top_1_correctness",
        "support_uid_hit",
        "support_uid_hit_top_3",
        "support_source_id_hit",
        "top_uid_match",
        "ambiguity_match",
        "confidence_calibration_match",
        "attachment_support_uid_hit",
        "attachment_answer_success",
        "attachment_text_evidence_success",
        "attachment_ocr_text_evidence_success",
        "weak_evidence_explained",
        "thread_group_id_match",
        "thread_group_source_match",
        "long_thread_answer_present",
        "long_thread_structure_preserved",
        "answer_content_match",
        "forbidden_support_ids_excluded",
    )
    average_metrics = (
        "support_uid_recall",
        "support_source_id_recall",
        "evidence_precision",
        "quote_attribution_precision",
        "quote_attribution_coverage",
    )
    return {
        "total_cases": len(results),
        "bucket_counts": dict(sorted(buckets.items())),
        **{metric: _boolean_metric_summary(results, metric) for metric in boolean_metrics},
        **{metric: _average_metric(results, metric) for metric in average_metrics},
    }
