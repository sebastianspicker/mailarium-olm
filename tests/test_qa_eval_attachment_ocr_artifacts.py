"""Ensures the captured attachment-OCR evaluation report remains reproducible from its labeled inputs."""

from tests.helpers.qa_eval_fixtures import assert_captured_report_matches


def test_saved_attachment_ocr_report_matches_runner_output():
    assert_captured_report_matches("attachment_ocr")
