"""Build synthetic emails and verify captured QA evaluation fixtures."""

import json
from pathlib import Path

from mailarium.parse_olm import Email


def make_email(*, subject: str, sender_email: str, body_text: str, has_attachments: bool = False) -> Email:
    """Build a synthetic inbox email, adding a stable spreadsheet attachment when requested."""
    return Email(
        message_id=f"<{subject}-{sender_email}>",
        subject=subject,
        sender_name=sender_email.split("@", 1)[0].title(),
        sender_email=sender_email,
        to=["team@example.com"],
        cc=[],
        bcc=[],
        date="2026-04-10T10:00:00Z",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=has_attachments,
        attachment_names=["budget.xlsx"] if has_attachments else [],
        attachments=(
            [{"name": "budget.xlsx", "mime_type": "application/vnd.ms-excel", "size": 1234, "content_id": "", "is_inline": False}]
            if has_attachments
            else []
        ),
    )


def assert_captured_report_matches(fixture_name: str) -> dict:
    """Re-run one captured QA fixture and compare its stable report fields."""
    from mailarium.qa_eval import run_evaluation_sync

    fixture_dir = Path("tests/fixtures/qa_eval")
    questions_path = fixture_dir / f"qa_eval_questions.{fixture_name}.json"
    results_path = fixture_dir / f"qa_eval_results.{fixture_name}.captured.json"
    report_path = fixture_dir / f"qa_eval_report.{fixture_name}.captured.json"
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    rerun_report = run_evaluation_sync(questions_path=questions_path, results_path=results_path)

    assert saved_report["summary"] == rerun_report["summary"]
    assert saved_report["failure_taxonomy"] == rerun_report["failure_taxonomy"]
    assert [item["id"] for item in saved_report["results"]] == [item["id"] for item in rerun_report["results"]]
    return saved_report
