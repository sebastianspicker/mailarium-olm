"""Ensures the core QA question set is labeled with expected support and its captured report is reproducible."""

from pathlib import Path

from tests.helpers.qa_eval_fixtures import assert_captured_report_matches


def test_core_question_set_is_labeled():
    from mailarium.qa_eval import load_question_cases

    path = Path("tests/fixtures/qa_eval/qa_eval_questions.core.json")
    cases = load_question_cases(path)

    assert len(cases) >= 8
    assert all(case.status == "labeled" for case in cases)
    assert all(case.expected_support_uids for case in cases)
    assert all(case.expected_top_uid for case in cases)
    assert all("TODO(human)" not in case.expected_answer for case in cases)


def test_saved_core_report_matches_runner_output():
    assert_captured_report_matches("core")
