"""Exercises QA question-set loading and bootstrap generation with machine-readable labels and provenance.

It rejects obsolete schema fields instead of accepting ambiguous evaluation data.
"""

import json
from pathlib import Path

import pytest


def test_load_question_cases_reads_generic_labels(tmp_path: Path):
    from mailarium.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "question": "Who asked for the updated budget?",
                        "expected_answer_terms": ["budget"],
                        "expected_support_uids": ["uid-1"],
                        "expected_support_source_ids": ["email:uid-1"],
                        "expected_quoted_speaker_emails": ["BOB@EXAMPLE.COM"],
                        "forbidden_support_uids": ["uid-forbidden"],
                        "triage_tags": ["retrieval_recall"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    case = load_question_cases(path)[0]

    assert case.expected_support_uids == ["uid-1"]
    assert case.expected_support_source_ids == ["email:uid-1"]
    assert case.expected_quoted_speaker_emails == ["bob@example.com"]
    assert case.forbidden_support_uids == ["uid-forbidden"]
    assert case.triage_tags == ["retrieval_recall"]


def test_load_question_cases_rejects_removed_fields(tmp_path: Path):
    from mailarium.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "old-001",
                        "bucket": "old",
                        "question": "Old schema",
                        "case_scope": {"target": "removed"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="case_scope"):
        load_question_cases(path)


def test_bootstrap_question_set_produces_reviewable_sampled_artifact(tmp_path: Path):
    from mailarium.qa_eval import bootstrap_question_set, load_question_cases

    questions_path = tmp_path / "questions.template.json"
    questions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "description": "Template question set.",
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "status": "todo",
                        "question": "Who asked for the updated budget?",
                        "expected_answer": "TODO(human): confirm",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "fact-001": {
                    "candidates": [{"uid": "uid-1", "score": 0.91, "subject": "Budget update"}],
                    "attachment_candidates": [],
                    "answer_quality": {"top_candidate_uid": "uid-1", "confidence_label": "high"},
                }
            }
        ),
        encoding="utf-8",
    )

    bootstrapped = bootstrap_question_set(questions_path=questions_path, results_path=results_path)
    output_path = tmp_path / "questions.sampled.json"
    output_path.write_text(json.dumps(bootstrapped), encoding="utf-8")
    case = load_question_cases(output_path)[0]

    assert case.status == "sampled"
    assert case.expected_answer == ""
    assert bootstrapped["bootstrap_metadata"]["status"] == "review_required"
    assert bootstrapped["cases"][0]["bootstrap_candidates"][0]["uid"] == "uid-1"


def test_template_question_set_is_machine_readable() -> None:
    payload = json.loads(Path("tests/fixtures/qa_eval/qa_eval_questions.template.json").read_text(encoding="utf-8"))

    assert "bootstrap" in payload["description"].casefold()
    assert "TODO(human)" not in json.dumps(payload)
