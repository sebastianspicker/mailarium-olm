import json
from pathlib import Path


def test_legal_support_question_set_is_labeled_and_scored():
    from src.qa_eval import load_question_cases

    path = Path("docs/agent/qa_eval_questions.legal_support.captured.json")
    cases = load_question_cases(path)

    assert len(cases) >= 5
    assert all(case.status == "labeled" for case in cases)
    assert any(case.expected_comparator_issue_ids for case in cases)
    assert any(case.expected_dashboard_cards for case in cases)
    assert any(case.expected_actor_ids for case in cases)
    assert any(case.expected_draft_ceiling_level for case in cases)
    assert any(case.expected_legal_support_source_ids for case in cases)
    assert any(case.expected_answer_terms for case in cases)
    assert any(case.forbidden_issue_ids for case in cases)
    assert any(case.forbidden_actor_ids for case in cases)
    assert any(case.forbidden_dashboard_cards for case in cases)
    assert any(case.forbidden_checklist_group_ids for case in cases)


def test_saved_legal_support_report_has_expected_contract():
    questions_path = Path("docs/agent/qa_eval_questions.legal_support.captured.json")
    report_path = Path("docs/agent/qa_eval_report.legal_support.captured.json")

    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    cases = questions["cases"]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["questions_path"].endswith("docs/agent/qa_eval_questions.legal_support.captured.json")
    assert report["total_cases"] == len(cases)
    assert report["summary"]["total_cases"] == len(cases)
    assert report["source_mode"] == "captured_only"
    assert report["source_counts"] == {"captured": len(cases)}
    assert report["summary"]["legal_support_product_completeness"]["passed"] == len(cases)
    assert report["summary"]["legal_support_product_completeness"]["scorable"] >= 5
    assert report["summary"]["comparator_matrix_coverage"]["scorable"] >= 1
    assert report["summary"]["comparator_matrix_coverage"]["average"] >= 1.0
    assert report["summary"]["dashboard_card_coverage"]["scorable"] >= 1
    assert report["summary"]["dashboard_card_coverage"]["average"] >= 1.0
    assert report["summary"]["actor_map_coverage"]["scorable"] >= 1
    assert report["summary"]["actor_map_coverage"]["average"] >= 1.0
    assert report["summary"]["checklist_group_coverage"]["scorable"] >= 1
    assert report["summary"]["checklist_group_coverage"]["average"] >= 1.0
    assert report["summary"]["drafting_ceiling_match"]["scorable"] >= 1
    assert report["summary"]["draft_section_completeness"]["scorable"] >= 1
    assert report["summary"]["draft_section_completeness"]["passed"] >= 1
    assert report["summary"]["answer_content_match"]["scorable"] >= 1
    assert report["summary"]["legal_support_grounding_hit"]["scorable"] >= 1
    assert report["summary"]["legal_support_grounding_recall"]["scorable"] >= 1
    assert "failure_taxonomy" in report
    assert "ranked_categories" in report["failure_taxonomy"]
    assert report["failure_taxonomy"]["total_flagged_cases"] == 0
    assert report["threshold_verdict"]["profile"] == "legal_support"
    assert report["threshold_verdict"]["status"] == "pass"
