import json
from pathlib import Path


def test_german_behavioral_analysis_question_set_covers_target_case_types():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.behavioral_analysis_german.captured.json")
    cases = load_question_cases(path)

    required_buckets = {
        "ordinary_workplace_conflict",
        "poor_communication_or_process_noise",
        "repeated_exclusion",
        "selective_non_response",
        "retaliation_after_trigger",
        "unequal_treatment",
        "explicit_hostility",
        "mixed_evidence",
        "insufficient_evidence",
        "attachment_same_name_hard_negative",
        "wrong_attachment_quote_match",
        "authored_german_quoted_english",
        "weak_ocr_near_exact",
        "calendar_only_exclusion",
        "silence_omission_chain",
        "promise_then_denial",
        "committee_comparator_witness_coverage",
    }

    assert len(cases) == 17
    assert all(case.status == "labeled" for case in cases)
    assert all(case.case_scope is not None for case in cases)
    assert required_buckets == {case.bucket for case in cases}
    assert all(case.question.startswith(("Beurteile", "Pruefe", "Bewerte", "Ordne")) for case in cases)
    triage_tags = {tag for case in cases for tag in case.triage_tags}
    assert {
        "slice_a_same_name_attachment",
        "slice_a_wrong_attachment_quote",
        "slice_a_authored_language",
        "slice_a_weak_ocr",
        "slice_a_calendar_only",
        "slice_a_silence_omission",
        "slice_a_promise_denial",
        "slice_a_comparator_coverage",
    }.issubset(triage_tags)


def test_saved_german_behavioral_analysis_report_matches_runner_output():
    from src.qa_eval import run_evaluation_sync

    questions_path = Path("docs/agent/qa_eval_questions.behavioral_analysis_german.captured.json")
    results_path = Path("docs/agent/qa_eval_results.behavioral_analysis_german.captured.json")
    report_path = Path("docs/agent/qa_eval_report.behavioral_analysis_german.captured.json")

    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    rerun_report = run_evaluation_sync(questions_path=questions_path, results_path=results_path)

    assert saved_report["summary"] == rerun_report["summary"]
    assert saved_report["failure_taxonomy"] == rerun_report["failure_taxonomy"]
    assert saved_report["source_counts"] == {"captured": 17}
    assert saved_report["summary"]["top_1_correctness"] == {"scorable": 17, "passed": 17, "failed": 0}
    assert saved_report["summary"]["behavior_tag_coverage"] == {"scorable": 9, "average": 1.0}
    assert saved_report["summary"]["counter_indicator_quality"] == {"scorable": 8, "average": 1.0}
    assert saved_report["summary"]["overclaim_guard_match"] == {"scorable": 17, "passed": 17, "failed": 0}
    assert saved_report["summary"]["report_completeness"] == {"scorable": 17, "passed": 17, "failed": 0}
    assert saved_report["threshold_verdict"]["profile"] == "behavioral_analysis_german"
    assert saved_report["threshold_verdict"]["status"] in {"pass", "fail", "informational"}
    assert saved_report["threshold_verdict"]["status"] == "pass"
    assert saved_report["threshold_verdict"]["status"] == rerun_report["threshold_verdict"]["status"]
