from __future__ import annotations

from src.qa_eval_thresholds import _check_delta_when_baseline_present, _metric_value, evaluate_report_thresholds


def test_metric_value_supports_passed_ratio_and_skips_unscorable() -> None:
    summary = {
        "archive_harvest_coverage_pass": {"scorable": 10, "passed": 9},
        "archive_harvest_quality_pass": {"scorable": 0, "passed": 0},
    }

    assert _metric_value(summary, "archive_harvest_coverage_pass", "passed_ratio") == 0.9
    assert _metric_value(summary, "archive_harvest_quality_pass", "passed_ratio") is None


def test_check_delta_when_baseline_present_flags_insufficient_improvement() -> None:
    summary = {
        "support_source_id_recall": {"scorable": 8, "average": 0.62},
    }
    baseline_summary = {
        "support_source_id_recall": {"scorable": 8, "average": 0.58},
    }

    failure = _check_delta_when_baseline_present(
        summary,
        baseline_summary,
        metric="support_source_id_recall",
        field="average_when_scorable",
        min_delta=0.1,
    )

    assert failure is not None
    assert failure["metric"] == "support_source_id_recall"
    assert float(failure["delta"]) < 0.1


def test_check_delta_when_baseline_present_skips_missing_baseline() -> None:
    summary = {
        "support_source_id_recall": {"scorable": 8, "average": 0.62},
    }

    failure = _check_delta_when_baseline_present(
        summary,
        {},
        metric="support_source_id_recall",
        field="average_when_scorable",
        min_delta=0.1,
    )

    assert failure is None


def test_behavioral_analysis_german_thresholds_accept_slice_a_hardening_metrics() -> None:
    report = {
        "questions_path": "docs/agent/qa_eval_questions.behavioral_analysis_german.captured.json",
        "source_mode": "captured_only",
        "source_counts": {"captured": 2},
        "summary": {
            "top_1_correctness": {"scorable": 2, "passed": 2, "failed": 0},
            "behavior_tag_coverage": {"scorable": 1, "average": 1.0},
            "counter_indicator_quality": {"scorable": 1, "average": 1.0},
            "report_completeness": {"scorable": 2, "passed": 2, "failed": 0},
            "comparator_matrix_coverage": {"scorable": 1, "average": 1.0},
        },
        "results": [
            {
                "slice_a_exact_verified_quote_rate": 1.0,
                "slice_a_near_exact_quote_rate": 1.0,
                "slice_a_false_exact_flag": 0.0,
                "slice_a_locator_completeness": 1.0,
                "slice_a_ocr_heavy_attachment_recall": True,
                "slice_a_authored_german_primary_match": True,
                "slice_a_contradiction_pair_precision": 1.0,
                "slice_a_mixed_source_completeness": 1.0,
                "slice_a_calendar_exclusion_visible": True,
                "slice_a_silence_omission_anchor_match": True,
            }
        ],
    }

    verdict = evaluate_report_thresholds(report)

    assert verdict["profile"] == "behavioral_analysis_german"
    assert verdict["status"] == "pass"


def test_behavioral_analysis_german_thresholds_fail_on_false_exact_rate_regression() -> None:
    report = {
        "questions_path": "docs/agent/qa_eval_questions.behavioral_analysis_german.captured.json",
        "source_mode": "captured_only",
        "source_counts": {"captured": 2},
        "summary": {
            "top_1_correctness": {"scorable": 2, "passed": 2, "failed": 0},
            "behavior_tag_coverage": {"scorable": 1, "average": 1.0},
            "counter_indicator_quality": {"scorable": 1, "average": 1.0},
            "report_completeness": {"scorable": 2, "passed": 2, "failed": 0},
            "comparator_matrix_coverage": {"scorable": 1, "average": 1.0},
        },
        "results": [
            {
                "slice_a_exact_verified_quote_rate": 1.0,
                "slice_a_near_exact_quote_rate": 1.0,
                "slice_a_false_exact_flag": 1.0,
                "slice_a_locator_completeness": 1.0,
                "slice_a_ocr_heavy_attachment_recall": True,
                "slice_a_authored_german_primary_match": True,
                "slice_a_contradiction_pair_precision": 1.0,
                "slice_a_mixed_source_completeness": 1.0,
                "slice_a_calendar_exclusion_visible": True,
                "slice_a_silence_omission_anchor_match": True,
            }
        ],
    }

    verdict = evaluate_report_thresholds(report)

    assert verdict["status"] == "fail"
    assert any(failure["metric"] == "slice_a_false_exact_rate" for failure in verdict["failures"])
