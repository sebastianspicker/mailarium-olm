"""Ensures quoted-speaker QA prompts carry labeled expectations and their captured evaluation report is reproducible."""

from pathlib import Path

from tests.helpers.qa_eval_fixtures import assert_captured_report_matches


def test_quote_question_set_is_labeled():
    from mailarium.qa_eval import load_question_cases

    path = Path("tests/fixtures/qa_eval/qa_eval_questions.quote.json")
    cases = load_question_cases(path)

    assert len(cases) >= 2
    assert all(case.status == "labeled" for case in cases)
    assert all(case.expected_quoted_speaker_emails for case in cases)
    assert all("quote_attribution" in case.triage_tags for case in cases)


def test_saved_quote_report_matches_runner_output():
    assert_captured_report_matches("quote")
