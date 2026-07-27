"""QA evaluation scoring for grounded answers, ambiguity, safeguards, and unlabeled metrics."""

import pytest


def test_evaluate_payload_scores_support_grounding_answer_and_ambiguity():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="fact-001",
        bucket="fact_lookup",
        question="Who approved the budget?",
        expected_answer_terms=["approved", "budget"],
        expected_support_uids=["uid-1", "uid-2"],
        expected_support_source_ids=["email:uid-1", "email:uid-2"],
        expected_top_uid="uid-1",
        expected_ambiguity="clear",
    )
    payload = {
        "count": 2,
        "candidates": [
            {"uid": "uid-1", "source_id": "email:uid-1", "score": 0.91},
            {"uid": "uid-2", "source_id": "email:uid-2", "score": 0.82},
        ],
        "attachment_candidates": [],
        "final_answer": {"text": "The budget was approved in the first message."},
        "answer_quality": {
            "top_candidate_uid": "uid-1",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["top_1_correctness"] is True
    assert result["support_uid_hit"] is True
    assert result["support_uid_hit_top_3"] is True
    assert result["support_uid_recall"] == pytest.approx(1.0)
    assert result["support_source_id_hit"] is True
    assert result["support_source_id_recall"] == pytest.approx(1.0)
    assert result["evidence_precision"] == pytest.approx(1.0)
    assert result["answer_content_match"] is True
    assert result["ambiguity_match"] is True


def test_evaluate_payload_scores_forbidden_support_negative_controls():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="negative-001",
        bucket="fact_lookup",
        question="Which message is supported?",
        forbidden_support_uids=["uid-forbidden"],
        forbidden_support_source_ids=["email:uid-forbidden"],
    )

    clean = evaluate_payload(
        case,
        {
            "candidates": [{"uid": "uid-ok", "source_id": "email:uid-ok"}],
            "attachment_candidates": [],
        },
        source="captured",
    )
    contaminated = evaluate_payload(
        case,
        {
            "candidates": [{"uid": "uid-forbidden", "source_id": "email:uid-forbidden"}],
            "attachment_candidates": [],
        },
        source="captured",
    )

    assert clean["forbidden_support_ids_excluded"] is True
    assert contaminated["forbidden_support_ids_excluded"] is False


def test_evaluate_payload_leaves_unlabeled_metrics_unscored():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    result = evaluate_payload(
        QuestionCase(id="open-001", bucket="exploration", question="What is relevant?"),
        {"count": 1, "candidates": [{"uid": "uid-1"}], "attachment_candidates": []},
        source="live",
    )

    assert result["support_uid_hit"] is None
    assert result["support_source_id_hit"] is None
    assert result["answer_content_match"] is None
    assert result["forbidden_support_ids_excluded"] is None
