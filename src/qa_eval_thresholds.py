"""Threshold profiles for QA eval report gating."""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def infer_threshold_profile(report: dict[str, Any]) -> str:
    questions_path = str(report.get("questions_path") or "")
    live_backend = str(report.get("live_backend") or "")
    if questions_path.endswith("qa_eval_questions.behavioral_analysis.captured.json"):
        return "behavioral_analysis"
    if questions_path.endswith("qa_eval_questions.behavioral_analysis_german.captured.json"):
        return "behavioral_analysis_german"
    if questions_path.endswith("qa_eval_questions.legal_support.captured.json"):
        return "legal_support"
    if questions_path.endswith("qa_eval_questions.live_expanded.json") and live_backend == "embedding":
        return "live_expanded_embedding"
    if questions_path.endswith("qa_eval_questions.live_expanded.json"):
        return "live_expanded"
    return "default"


def _check_minimum(summary: dict[str, Any], metric: str, field: str, minimum: float) -> dict[str, Any] | None:
    value = _metric_value(summary, metric, field)
    if value is None:
        return None
    if value >= minimum:
        return None
    return {
        "metric": metric,
        "field": field,
        "expected": {"min": minimum},
        "actual": value,
    }


def _check_maximum(summary: dict[str, Any], metric: str, field: str, maximum: float) -> dict[str, Any] | None:
    value = _metric_value(summary, metric, field)
    if value is None:
        return None
    if value <= maximum:
        return None
    return {
        "metric": metric,
        "field": field,
        "expected": {"max": maximum},
        "actual": value,
    }


def _check_pass_all_when_scorable(summary: dict[str, Any], metric: str) -> dict[str, Any] | None:
    metric_summary = _as_dict(summary.get(metric))
    scorable = int(metric_summary.get("scorable") or 0)
    if scorable <= 0:
        return None
    passed = int(metric_summary.get("passed") or 0)
    if passed == scorable:
        return None
    return {
        "metric": metric,
        "field": "passed",
        "expected": {"equals_scorable": scorable},
        "actual": passed,
    }


def _check_average_when_scorable(summary: dict[str, Any], metric: str, minimum: float) -> dict[str, Any] | None:
    metric_summary = _as_dict(summary.get(metric))
    scorable = int(metric_summary.get("scorable") or 0)
    if scorable <= 0:
        return None
    average = float(metric_summary.get("average") or 0.0)
    if average >= minimum:
        return None
    return {
        "metric": metric,
        "field": "average",
        "expected": {"min": minimum},
        "actual": average,
    }


def _metric_value(summary: dict[str, Any], metric: str, field: str) -> float | None:
    metric_summary = _as_dict(summary.get(metric))
    if not metric_summary:
        return None
    if field == "passed_ratio":
        scorable = int(metric_summary.get("scorable") or 0)
        if scorable <= 0:
            return None
        passed = int(metric_summary.get("passed") or 0)
        return passed / scorable
    if field == "average_when_scorable":
        scorable = int(metric_summary.get("scorable") or 0)
        if scorable <= 0:
            return None
        return float(metric_summary.get("average") or 0.0)
    if field not in metric_summary:
        return None
    return float(metric_summary.get(field) or 0.0)


def _check_delta_when_baseline_present(
    summary: dict[str, Any],
    baseline_summary: dict[str, Any],
    *,
    metric: str,
    field: str,
    min_delta: float,
) -> dict[str, Any] | None:
    current_value = _metric_value(summary, metric, field)
    baseline_value = _metric_value(baseline_summary, metric, field)
    if current_value is None or baseline_value is None:
        return None
    observed_delta = current_value - baseline_value
    if observed_delta >= min_delta:
        return None
    return {
        "metric": metric,
        "field": field,
        "expected": {
            "baseline": baseline_value,
            "min_delta": min_delta,
            "min_current": baseline_value + min_delta,
        },
        "actual": current_value,
        "delta": observed_delta,
    }


def _derived_metric_average(results: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    values = [float(result[metric]) for result in results if isinstance(result, dict) and result.get(metric) is not None]
    if not values:
        return {"scorable": 0, "average": 0.0}
    return {"scorable": len(values), "average": round(sum(values) / len(values), 12)}


def _derive_behavioral_analysis_german_metrics(report: dict[str, Any]) -> dict[str, Any]:
    results = [item for item in (report.get("results") or []) if isinstance(item, dict)]
    return {
        "slice_a_exact_verified_quote_rate": _derived_metric_average(results, "slice_a_exact_verified_quote_rate"),
        "slice_a_near_exact_quote_rate": _derived_metric_average(results, "slice_a_near_exact_quote_rate"),
        "slice_a_false_exact_rate": _derived_metric_average(results, "slice_a_false_exact_flag"),
        "slice_a_locator_completeness": _derived_metric_average(results, "slice_a_locator_completeness"),
        "slice_a_ocr_heavy_attachment_recall": _derived_metric_average(results, "slice_a_ocr_heavy_attachment_recall"),
        "slice_a_authored_german_primary_match": _derived_metric_average(results, "slice_a_authored_german_primary_match"),
        "slice_a_contradiction_pair_precision": _derived_metric_average(results, "slice_a_contradiction_pair_precision"),
        "slice_a_mixed_source_completeness": _derived_metric_average(results, "slice_a_mixed_source_completeness"),
        "slice_a_calendar_exclusion_visible": _derived_metric_average(results, "slice_a_calendar_exclusion_visible"),
        "slice_a_silence_omission_anchor_match": _derived_metric_average(results, "slice_a_silence_omission_anchor_match"),
    }


def evaluate_report_thresholds(report: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    summary = _as_dict(report.get("summary"))
    baseline_summary = _as_dict(report.get("baseline_summary"))
    failure_taxonomy = _as_dict(report.get("failure_taxonomy"))
    resolved_profile = profile or infer_threshold_profile(report)
    source_mode = str(report.get("source_mode") or "")
    source_counts = _as_dict(report.get("source_counts"))
    metric_summary = dict(summary)
    if resolved_profile == "behavioral_analysis_german":
        metric_summary.update(_derive_behavioral_analysis_german_metrics(report))

    if source_mode == "mixed":
        return {
            "profile": resolved_profile,
            "status": "informational",
            "failure_count": 0,
            "failures": [],
            "reason": "source_mode_mixed_comparison_only",
        }

    failures: list[dict[str, Any]] = []

    behavioral_analysis_checks = [
        {"type": "minimum", "metric": "support_uid_hit", "field": "passed", "value": 5},
        {"type": "minimum", "metric": "support_source_id_hit", "field": "scorable", "value": 6},
        {"type": "minimum", "metric": "support_source_id_hit", "field": "passed", "value": 5},
        {"type": "minimum", "metric": "support_source_id_recall", "field": "average", "value": 0.8},
        {"type": "average_when_scorable", "metric": "benchmark_issue_family_recovery", "value": 1.0},
        {"type": "average_when_scorable", "metric": "benchmark_report_recovery", "value": 1.0},
        {"type": "minimum", "metric": "chronology_uid_hit", "field": "scorable", "value": 4},
        {"type": "average_when_scorable", "metric": "behavior_tag_coverage", "value": 1.0},
        {"type": "average_when_scorable", "metric": "counter_indicator_quality", "value": 1.0},
        {"type": "minimum", "metric": "overclaim_guard_match", "field": "passed", "value": 6},
        {"type": "minimum", "metric": "report_completeness", "field": "scorable", "value": 6},
    ]

    checks_by_profile: dict[str, list[dict[str, Any]]] = {
        "behavioral_analysis": list(behavioral_analysis_checks),
        "behavioral_analysis_german": [
            {"type": "minimum", "metric": "top_1_correctness", "field": "passed_ratio", "value": 0.9},
            {"type": "minimum", "metric": "behavior_tag_coverage", "field": "average_when_scorable", "value": 0.9},
            {"type": "minimum", "metric": "counter_indicator_quality", "field": "average_when_scorable", "value": 0.9},
            {"type": "minimum", "metric": "report_completeness", "field": "passed_ratio", "value": 0.9},
            {"type": "minimum", "metric": "slice_a_exact_verified_quote_rate", "field": "average", "value": 0.8},
            {"type": "minimum", "metric": "slice_a_near_exact_quote_rate", "field": "average", "value": 0.8},
            {"type": "maximum", "metric": "slice_a_false_exact_rate", "field": "average", "value": 0.3},
            {"type": "minimum", "metric": "slice_a_locator_completeness", "field": "average", "value": 0.9},
            {"type": "minimum", "metric": "slice_a_ocr_heavy_attachment_recall", "field": "average", "value": 0.9},
            {"type": "minimum", "metric": "slice_a_authored_german_primary_match", "field": "average", "value": 1.0},
            {"type": "minimum", "metric": "slice_a_contradiction_pair_precision", "field": "average", "value": 0.9},
            {"type": "minimum", "metric": "comparator_matrix_coverage", "field": "average_when_scorable", "value": 0.9},
            {"type": "minimum", "metric": "slice_a_mixed_source_completeness", "field": "average", "value": 0.9},
            {"type": "minimum", "metric": "slice_a_calendar_exclusion_visible", "field": "average", "value": 1.0},
            {"type": "minimum", "metric": "slice_a_silence_omission_anchor_match", "field": "average", "value": 1.0},
        ],
        "legal_support": [
            {"type": "pass_all_when_scorable", "metric": "legal_support_product_completeness"},
            {"type": "average_when_scorable", "metric": "comparator_matrix_coverage", "value": 1.0},
            {"type": "average_when_scorable", "metric": "dashboard_card_coverage", "value": 1.0},
            {"type": "average_when_scorable", "metric": "actor_map_coverage", "value": 1.0},
            {"type": "average_when_scorable", "metric": "checklist_group_coverage", "value": 1.0},
            {"type": "pass_all_when_scorable", "metric": "drafting_ceiling_match"},
            {"type": "minimum", "metric": "draft_section_completeness", "field": "passed", "value": 1},
            {"type": "pass_all_when_scorable", "metric": "answer_content_match"},
            {"type": "pass_all_when_scorable", "metric": "legal_support_grounding_hit"},
            {"type": "average_when_scorable", "metric": "legal_support_grounding_recall", "value": 1.0},
        ],
        "live_expanded": [
            {"type": "pass_all_when_scorable", "metric": "support_uid_hit"},
            {"type": "minimum", "metric": "support_uid_recall", "field": "average", "value": 0.95},
            {"type": "pass_all_when_scorable", "metric": "support_source_id_hit"},
            {"type": "average_when_scorable", "metric": "support_source_id_recall", "value": 1.0},
            {"type": "average_when_scorable", "metric": "evidence_precision", "value": 0.45},
            {"type": "minimum", "metric": "confidence_calibration_match", "field": "passed", "value": 9},
            {"type": "average_when_scorable", "metric": "quote_attribution_precision", "value": 1.0},
            {"type": "average_when_scorable", "metric": "quote_attribution_coverage", "value": 1.0},
        ],
        "live_expanded_embedding": [
            {"type": "minimum", "metric": "support_uid_hit", "field": "scorable", "value": 1},
            {"type": "minimum", "metric": "support_uid_recall", "field": "scorable", "value": 1},
        ],
        "default": [],
    }

    for check in checks_by_profile.get(resolved_profile, []):
        failure = None
        if check["type"] == "minimum":
            failure = _check_minimum(metric_summary, str(check["metric"]), str(check["field"]), float(check["value"]))
        elif check["type"] == "maximum":
            failure = _check_maximum(metric_summary, str(check["metric"]), str(check["field"]), float(check["value"]))
        elif check["type"] == "pass_all_when_scorable":
            failure = _check_pass_all_when_scorable(metric_summary, str(check["metric"]))
        elif check["type"] == "average_when_scorable":
            failure = _check_average_when_scorable(metric_summary, str(check["metric"]), float(check["value"]))
        elif check["type"] == "delta_when_baseline_present":
            failure = _check_delta_when_baseline_present(
                metric_summary,
                baseline_summary,
                metric=str(check["metric"]),
                field=str(check["field"]),
                min_delta=float(check["value"]),
            )
        if failure is not None:
            failures.append(failure)

    if source_mode == "captured_only":
        observed_live = int(source_counts.get("live") or 0)
        if observed_live > 0:
            failures.append(
                {
                    "metric": "source_counts",
                    "field": "live",
                    "expected": {"equals": 0},
                    "actual": observed_live,
                }
            )
    elif source_mode == "live_only":
        observed_captured = int(source_counts.get("captured") or 0)
        if observed_captured > 0:
            failures.append(
                {
                    "metric": "source_counts",
                    "field": "captured",
                    "expected": {"equals": 0},
                    "actual": observed_captured,
                }
            )

    if resolved_profile == "legal_support" and int(failure_taxonomy.get("total_flagged_cases") or 0) > 0:
        failures.append(
            {
                "metric": "failure_taxonomy",
                "field": "total_flagged_cases",
                "expected": {"max": 0},
                "actual": int(failure_taxonomy.get("total_flagged_cases") or 0),
            }
        )

    return {
        "profile": resolved_profile,
        "status": "pass" if not failures else "fail",
        "failure_count": len(failures),
        "failures": failures,
    }
