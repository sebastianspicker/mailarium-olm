"""Ensures inferred-thread QA prompts retain labeled thread expectations and a reproducible captured report."""

from pathlib import Path

from tests.helpers.qa_eval_fixtures import assert_captured_report_matches


def test_inferred_thread_question_set_is_labeled():
    from mailarium.qa_eval import load_question_cases

    path = Path("tests/fixtures/qa_eval/qa_eval_questions.inferred_thread.json")
    cases = load_question_cases(path)

    assert len(cases) >= 2
    assert all(case.status == "labeled" for case in cases)
    assert all(case.expected_thread_group_id for case in cases)
    assert all(case.expected_thread_group_source == "inferred" for case in cases)


def test_saved_inferred_thread_report_matches_runner_output():
    saved_report = assert_captured_report_matches("inferred_thread")
    summary = saved_report["summary"]
    assert summary["thread_group_id_match"]["passed"] == 2
    assert summary["thread_group_source_match"]["passed"] == 2
