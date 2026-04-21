import json
from pathlib import Path


def test_long_thread_live_question_set_is_labeled():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.long_thread.live.json")
    cases = load_question_cases(path)

    assert len(cases) == 2
    assert all(case.status == "labeled" for case in cases)
    assert all("long_thread" in case.triage_tags for case in cases)
    assert all(case.expected_top_uid for case in cases)


def test_saved_long_thread_live_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.long_thread.live.json")
    report_path = Path("docs/agent/qa_eval_report.long_thread.live.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.long_thread.live.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_counts"] == {"live": len(cases)}
    assert report["live_backend"] == "sqlite_fallback"
    assert report["summary"]["long_thread_answer_present"]["passed"] == len(cases)
    assert report["summary"]["long_thread_structure_preserved"]["passed"] == len(cases)
