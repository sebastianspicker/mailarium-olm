"""Exercises QA metric coercion, baseline deltas, threshold enforcement, and backend-specific profiles.

It requires every labeled boolean metric to participate in threshold decisions.
"""

from mailarium.qa_eval_thresholds import (
    _check_delta_when_baseline_present,
    _metric_value,
    evaluate_report_thresholds,
    infer_threshold_profile,
)


def test_metric_value_supports_boolean_ratio_and_average() -> None:
    summary = {
        "support_uid_hit": {"scorable": 10, "passed": 9},
        "support_uid_recall": {"scorable": 10, "average": 0.8},
        "unscored": {"scorable": 0, "passed": 0},
    }

    assert _metric_value(summary, "support_uid_hit", "passed_ratio") == 0.9
    assert _metric_value(summary, "support_uid_recall", "average_when_scorable") == 0.8
    assert _metric_value(summary, "unscored", "passed_ratio") is None


def test_check_delta_when_baseline_present_flags_insufficient_improvement() -> None:
    failure = _check_delta_when_baseline_present(
        {"support_uid_recall": {"scorable": 8, "average": 0.62}},
        {"support_uid_recall": {"scorable": 8, "average": 0.58}},
        metric="support_uid_recall",
        field="average_when_scorable",
        min_delta=0.1,
    )

    assert failure is not None
    assert failure["metric"] == "support_uid_recall"


def test_evaluate_report_thresholds_requires_all_labeled_boolean_metrics() -> None:
    report = {
        "summary": {
            "support_uid_hit": {"scorable": 2, "passed": 2},
            "support_source_id_hit": {"scorable": 1, "passed": 0},
            "ambiguity_match": {"scorable": 0, "passed": 0},
        }
    }

    verdict = evaluate_report_thresholds(report)

    assert verdict["profile"] == "generic"
    assert verdict["status"] == "fail"
    assert verdict["failures"][0]["metric"] == "support_source_id_hit"


def test_infer_threshold_profile_distinguishes_live_and_embedding() -> None:
    assert infer_threshold_profile({"questions_path": "qa_eval_questions.live_expanded.json"}) == "live_expanded"
    assert infer_threshold_profile({"live_backend": "embedding"}) == "embedding"
