"""Threshold profiles for QA eval report gating."""
# pylint: disable=too-many-branches,too-many-locals,too-many-return-statements

from __future__ import annotations

from typing import Any

from src._utils import _as_dict


def infer_threshold_profile(report: dict[str, Any]) -> str:
    """Infer the threshold profile from a QA evaluation report.

    Determines the appropriate threshold profile based on the questions path
    and live backend specified in the report.

    Args:
        report: QA evaluation report dictionary.

    Returns:
        Profile name string. One of:
            - behavioral_analysis
            - behavioral_analysis_german
            - legal_support
            - live_expanded_embedding
            - live_expanded
            - default
    """
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
    """Check if a metric field meets a minimum threshold.

    Args:
        summary: Summary dictionary containing metric data.
        metric: Metric name to check.
        field: Field name within the metric to check.
        minimum: Minimum acceptable value.

    Returns:
        None if the check passes, otherwise a dictionary with:
            - metric: The metric name
            - field: The field name
            - expected: Dictionary with "min" key
            - actual: The actual value found
    """
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
    """Check if a metric field meets a maximum threshold.

    Args:
        summary: Summary dictionary containing metric data.
        metric: Metric name to check.
        field: Field name within the metric to check.
        maximum: Maximum acceptable value.

    Returns:
        None if the check passes, otherwise a dictionary with:
            - metric: The metric name
            - field: The field name
            - expected: Dictionary with "max" key
            - actual: The actual value found
    """
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
    """Check if all scorable items for a metric passed.

    Args:
        summary: Summary dictionary containing metric data.
        metric: Metric name to check.

    Returns:
        None if all scorable items passed or there are no scorable items,
        otherwise a dictionary with:
            - metric: The metric name
            - field: "passed"
            - expected: Dictionary with "equals_scorable" key
            - actual: The actual passed count
    """
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
    """Check if the average of scorable items meets a minimum threshold.

    Args:
        summary: Summary dictionary containing metric data.
        metric: Metric name to check.
        minimum: Minimum acceptable average value.

    Returns:
        None if the check passes or there are no scorable items,
        otherwise a dictionary with:
            - metric: The metric name
            - field: "average"
            - expected: Dictionary with "min" key
            - actual: The actual average value
    """
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
    """Extract a numeric metric value from a summary dictionary.

    Handles special field types like "passed_ratio" and "average_when_scorable"
    which require computation from multiple fields.

    Args:
        summary: Summary dictionary containing metric data.
        metric: Metric name to extract.
        field: Field name or special type within the metric.

    Returns:
        Float value if found and computable, otherwise None.
    """
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
    """Check if a metric field has improved by at least min_delta from baseline.

    Args:
        summary: Current summary dictionary containing metric data.
        baseline_summary: Baseline summary dictionary for comparison.
        metric: Metric name to check.
        field: Field name within the metric to check.
        min_delta: Minimum required improvement (current - baseline).

    Returns:
        None if the check passes, otherwise a dictionary with:
            - metric: The metric name
            - field: The field name
            - expected: Dictionary with baseline, min_delta, and min_current
            - actual: The actual current value
            - delta: The observed delta (current - baseline)
    """
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
    """Compute the average of a metric across a list of results.

    Args:
        results: List of result dictionaries.
        metric: Metric key to extract from each result.

    Returns:
        Dictionary with:
            - scorable: Number of results with the metric
            - average: Average value of the metric, rounded to 12 decimal places
    """
    values = [float(result[metric]) for result in results if isinstance(result, dict) and result.get(metric) is not None]
    if not values:
        return {"scorable": 0, "average": 0.0}
    return {"scorable": len(values), "average": round(sum(values) / len(values), 12)}


def _derive_behavioral_analysis_german_metrics(report: dict[str, Any]) -> dict[str, Any]:
    """Derive additional metrics specific to behavioral analysis German profile.

    Computes averages for slice_a metrics from the report results.

    Args:
        report: QA evaluation report dictionary with results.

    Returns:
        Dictionary of derived metric averages for behavioral analysis German.
    """
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


def _threshold_checks_by_profile() -> dict[str, list[dict[str, Any]]]:
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

    return checks_by_profile


def evaluate_report_thresholds(report: dict[str, Any], *, profile: str | None = None) -> dict[str, Any]:
    """Evaluate a QA report against threshold profiles.

    Checks report metrics against profile-specific thresholds to determine
    pass/fail status. Supports multiple profiles with different threshold
    requirements.

    Args:
        report: QA evaluation report dictionary.
        profile: Optional profile name override. If None, inferred from report.

    Returns:
        Dictionary containing:
            - profile: The resolved profile name
            - status: "pass" if all checks passed, otherwise "fail"
            - failure_count: Number of failed checks
            - failures: List of failure dictionaries with details
            - reason: Optional reason string (e.g., for informational status)
    """
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

    checks_by_profile = _threshold_checks_by_profile()
    failures = _evaluate_threshold_checks(checks_by_profile.get(resolved_profile, []), metric_summary, baseline_summary)
    failures.extend(_source_count_failures(source_mode, source_counts))
    legal_failure = _legal_taxonomy_failure(resolved_profile, failure_taxonomy)
    if legal_failure:
        failures.append(legal_failure)

    return {
        "profile": resolved_profile,
        "status": "pass" if not failures else "fail",
        "failure_count": len(failures),
        "failures": failures,
    }


def _evaluate_threshold_checks(checks, metric_summary, baseline_summary) -> list[dict[str, Any]]:
    dispatch = {
        "minimum": lambda c: _check_minimum(metric_summary, str(c["metric"]), str(c["field"]), float(c["value"])),
        "maximum": lambda c: _check_maximum(metric_summary, str(c["metric"]), str(c["field"]), float(c["value"])),
        "pass_all_when_scorable": lambda c: _check_pass_all_when_scorable(metric_summary, str(c["metric"])),
        "average_when_scorable": lambda c: _check_average_when_scorable(metric_summary, str(c["metric"]), float(c["value"])),
        "delta_when_baseline_present": lambda c: _check_delta_when_baseline_present(
            metric_summary,
            baseline_summary,
            metric=str(c["metric"]),
            field=str(c["field"]),
            min_delta=float(c["value"]),
        ),
    }
    failures = []
    for check in checks:
        handler = dispatch.get(check["type"])
        failure = handler(check) if handler else None
        if failure is not None:
            failures.append(failure)
    return failures


def _source_count_failures(source_mode: str, source_counts: dict[str, Any]) -> list[dict[str, Any]]:
    if source_mode == "captured_only":
        return _unexpected_source_count(source_counts, "live")
    if source_mode == "live_only":
        return _unexpected_source_count(source_counts, "captured")
    return []


def _unexpected_source_count(source_counts: dict[str, Any], field: str) -> list[dict[str, Any]]:
    observed = int(source_counts.get(field) or 0)
    if observed <= 0:
        return []
    return [{"metric": "source_counts", "field": field, "expected": {"equals": 0}, "actual": observed}]


def _legal_taxonomy_failure(profile: str, taxonomy: dict[str, Any]) -> dict[str, Any] | None:
    flagged = int(taxonomy.get("total_flagged_cases") or 0)
    if profile != "legal_support" or flagged <= 0:
        return None
    return {"metric": "failure_taxonomy", "field": "total_flagged_cases", "expected": {"max": 0}, "actual": flagged}
