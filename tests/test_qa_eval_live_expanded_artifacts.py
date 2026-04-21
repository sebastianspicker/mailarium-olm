import json
from pathlib import Path


def test_live_expanded_question_set_is_labeled():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.live_expanded.json")
    cases = load_question_cases(path)

    assert len(cases) >= 24
    assert all(case.status == "labeled" for case in cases)
    assert all(case.expected_support_uids for case in cases)
    assert all(case.expected_top_uid for case in cases)
    quote_labeled_cases = [case for case in cases if case.expected_quoted_speaker_emails]
    assert len(quote_labeled_cases) >= 2
    assert {"fact_lookup", "thread_process", "attachment_lookup", "ambiguity_stress"} <= {case.bucket for case in cases}
    tags = {tag for case in cases for tag in case.triage_tags}
    assert {"quote_attribution", "attachment_extraction", "long_thread", "weak_message_handling"} <= tags


def test_saved_live_expanded_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.live_expanded.json")
    report_path = Path("docs/agent/qa_eval_report.live_expanded.live.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.live_expanded.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_mode"] == "live_only"
    assert report["source_counts"] == {"live": len(cases)}
    assert isinstance(report["live_backend"], str) and report["live_backend"]
    assert len(report["results"]) == len(cases)
    assert report["summary"]["support_uid_hit"]["passed"] == len(cases)
    assert report["summary"]["support_uid_recall"]["average"] >= 0.95
    assert report["summary"]["confidence_calibration_match"]["passed"] >= 9
    assert report["summary"]["quote_attribution_precision"]["scorable"] >= 2
    assert report["summary"]["quote_attribution_precision"]["average"] >= 1.0
    assert report["summary"]["quote_attribution_coverage"]["scorable"] >= 2
    assert report["summary"]["quote_attribution_coverage"]["average"] >= 1.0
    assert report["threshold_verdict"]["profile"] == "live_expanded"
    assert report["threshold_verdict"]["status"] == "fail"


def test_saved_embedding_live_expanded_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.live_expanded.json")
    report_path = Path("docs/agent/qa_eval_report.live_expanded.embedding.live.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.live_expanded.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_mode"] == "live_only"
    assert report["source_counts"] == {"live": len(cases)}
    assert report["live_backend"] == "embedding"
    assert len(report["results"]) == len(cases)
    assert report["summary"]["support_uid_hit"]["scorable"] == len(cases)
    assert report["summary"]["support_uid_recall"]["scorable"] == len(cases)
    assert report["threshold_verdict"]["profile"] == "live_expanded_embedding"
    assert report["threshold_verdict"]["status"] == "pass"
