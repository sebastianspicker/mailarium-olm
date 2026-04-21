import json
from pathlib import Path


def test_investigation_question_set_is_labeled_and_case_scoped():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.investigation.live.json")
    cases = load_question_cases(path)

    assert len(cases) >= 2
    assert all(case.status == "labeled" for case in cases)
    assert all(case.case_scope is not None for case in cases)
    assert all(case.expected_case_bundle_uids for case in cases)
    assert all(case.expected_source_types for case in cases)


def test_saved_investigation_live_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.investigation.live.json")
    report_path = Path("docs/agent/qa_eval_report.investigation.live.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.investigation.live.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_counts"] == {"live": len(cases)}
    assert isinstance(report["live_backend"], str) and report["live_backend"]
    assert report["summary"]["case_bundle_present"]["scorable"] == len(cases)
    assert report["summary"]["investigation_blocks_present"]["scorable"] == len(cases)
    assert report["summary"]["case_bundle_support_uid_hit"]["scorable"] == len(cases)
    assert report["summary"]["multi_source_source_types_match"]["scorable"] == len(cases)
    readiness = report["investigation_corpus_readiness"]
    assert readiness["case_scope_case_count"] == len(cases)
    assert readiness["corpus_populated"] is True
    assert readiness["supports_case_analysis"] is True
