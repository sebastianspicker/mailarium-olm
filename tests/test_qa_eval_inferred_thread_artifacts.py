import json
from pathlib import Path


def test_inferred_thread_question_set_is_labeled():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.inferred_thread.json")
    cases = load_question_cases(path)

    assert len(cases) >= 2
    assert all(case.status == "labeled" for case in cases)
    assert all(case.expected_thread_group_id for case in cases)
    assert all(case.expected_thread_group_source == "inferred" for case in cases)


def test_saved_inferred_thread_report_matches_runner_output():
    from src.qa_eval import run_evaluation_sync

    questions_path = Path("docs/agent/qa_eval_questions.inferred_thread.json")
    results_path = Path("docs/agent/qa_eval_results.inferred_thread.captured.json")
    report_path = Path("docs/agent/qa_eval_report.inferred_thread.captured.json")

    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    rerun_report = run_evaluation_sync(questions_path=questions_path, results_path=results_path)

    assert saved_report["summary"] == rerun_report["summary"]
    assert saved_report["failure_taxonomy"] == rerun_report["failure_taxonomy"]
    assert [item["id"] for item in saved_report["results"]] == [item["id"] for item in rerun_report["results"]]

    summary = saved_report["summary"]
    assert summary["thread_group_id_match"]["passed"] == 2
    assert summary["thread_group_source_match"]["passed"] == 2


def test_saved_live_inferred_thread_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.inferred_thread.live.json")
    report_path = Path("docs/agent/qa_eval_report.inferred_thread.live.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.inferred_thread.live.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_counts"] == {"live": len(cases)}
    assert report["live_backend"] == "sqlite_fallback"
    assert report["summary"]["thread_group_id_match"]["passed"] == len(cases)
    assert report["summary"]["thread_group_source_match"]["passed"] == len(cases)


def test_saved_natural_inferred_thread_prevalence_artifact_has_expected_contract():
    artifact_path = Path("docs/agent/qa_eval_inferred_thread_prevalence.live.json")

    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["artifact_type"] == "natural_inferred_thread_prevalence"
    assert artifact["source_corpus"].endswith("synthetic-eval-corpus.olm")
    assert artifact["sample_email_count"] >= 1000
    assert artifact["emails_with_inferred_thread_id"] >= 0
    assert artifact["emails_with_inferred_parent_uid"] >= 0
    assert artifact["inferred_only_email_count"] >= 0
    assert artifact["distinct_inferred_thread_ids"] >= 0
    assert artifact["decision"] in {"deprioritize", "validate_and_continue"}
