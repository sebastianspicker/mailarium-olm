import json
from pathlib import Path


def test_core_question_set_is_labeled():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.core.json")
    cases = load_question_cases(path)

    assert len(cases) >= 8
    assert all(case.status == "labeled" for case in cases)
    assert all(case.expected_support_uids for case in cases)
    assert all(case.expected_top_uid for case in cases)
    assert all("TODO(human)" not in case.expected_answer for case in cases)


def test_saved_core_report_matches_runner_output():
    from src.qa_eval import run_evaluation_sync

    questions_path = Path("docs/agent/qa_eval_questions.core.json")
    results_path = Path("docs/agent/qa_eval_results.core.captured.json")
    report_path = Path("docs/agent/qa_eval_report.core.captured.json")

    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    rerun_report = run_evaluation_sync(questions_path=questions_path, results_path=results_path)

    assert saved_report["summary"] == rerun_report["summary"]
    assert saved_report["failure_taxonomy"] == rerun_report["failure_taxonomy"]
    assert [item["id"] for item in saved_report["results"]] == [item["id"] for item in rerun_report["results"]]
