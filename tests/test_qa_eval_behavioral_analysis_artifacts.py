import json
from pathlib import Path


def test_behavioral_analysis_question_set_is_labeled_and_scored():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.behavioral_analysis.captured.json")
    cases = load_question_cases(path)

    assert len(cases) >= 6
    assert all(case.status == "labeled" for case in cases)
    assert any(case.expected_behavior_ids for case in cases)
    assert any(case.expected_counter_indicator_markers for case in cases)
    assert any(case.expected_max_claim_level for case in cases)


def test_saved_behavioral_analysis_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.behavioral_analysis.captured.json")
    report_path = Path("docs/agent/qa_eval_report.behavioral_analysis.captured.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.behavioral_analysis.captured.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_mode"] == "captured_only"
    assert report["source_counts"] == {"captured": len(cases)}
    assert report["summary"]["support_uid_hit"]["passed"] >= 5
    assert report["summary"]["support_source_id_hit"]["scorable"] >= 6
    assert report["summary"]["support_source_id_hit"]["passed"] >= 5
    assert report["summary"]["support_source_id_recall"]["average"] >= 0.8
    assert report["summary"]["benchmark_issue_family_recovery"]["scorable"] >= 1
    assert report["summary"]["benchmark_issue_family_recovery"]["average"] >= 1.0
    assert report["summary"]["benchmark_report_recovery"]["scorable"] >= 1
    assert report["summary"]["benchmark_report_recovery"]["average"] >= 1.0
    assert report["summary"]["chronology_uid_hit"]["scorable"] >= 4
    assert report["summary"]["behavior_tag_coverage"]["scorable"] >= 5
    assert report["summary"]["behavior_tag_coverage"]["average"] >= 1.0
    assert report["summary"]["counter_indicator_quality"]["scorable"] >= 4
    assert report["summary"]["counter_indicator_quality"]["average"] >= 1.0
    assert report["summary"]["overclaim_guard_match"]["scorable"] >= 6
    assert report["summary"]["overclaim_guard_match"]["passed"] >= 6
    assert report["summary"]["report_completeness"]["scorable"] >= 6
    assert "failure_taxonomy" in report
    assert "ranked_categories" in report["failure_taxonomy"]
    assert report["threshold_verdict"]["profile"] == "behavioral_analysis"
    assert report["threshold_verdict"]["status"] == "pass"
