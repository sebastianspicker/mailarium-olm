import json
from pathlib import Path


def test_saved_attachment_ocr_report_matches_runner_output():
    from src.qa_eval import run_evaluation_sync

    questions_path = Path("docs/agent/qa_eval_questions.attachment_ocr.json")
    results_path = Path("docs/agent/qa_eval_results.attachment_ocr.captured.json")
    report_path = Path("docs/agent/qa_eval_report.attachment_ocr.captured.json")

    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    rerun_report = run_evaluation_sync(questions_path=questions_path, results_path=results_path)

    assert saved_report["summary"] == rerun_report["summary"]
    assert saved_report["failure_taxonomy"] == rerun_report["failure_taxonomy"]
    assert [item["id"] for item in saved_report["results"]] == [item["id"] for item in rerun_report["results"]]
