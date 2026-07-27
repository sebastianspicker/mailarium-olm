"""QA evaluation scoring for quote attribution, thread continuity, and report summaries."""

import pytest


def test_evaluate_payload_scores_quote_attribution_precision_and_coverage():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="quote-001",
        bucket="quote_attribution",
        question="Who was quoted?",
        expected_quoted_speaker_emails=["bob@example.com"],
    )
    payload = {
        "candidates": [
            {
                "uid": "uid-1",
                "speaker_attribution": {
                    "quoted_blocks": [
                        {"speaker_email": "bob@example.com"},
                        {"speaker_email": "carol@example.com"},
                    ]
                },
            }
        ],
        "attachment_candidates": [],
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["observed_quoted_speaker_emails"] == ["bob@example.com", "carol@example.com"]
    assert result["quote_attribution_precision"] == pytest.approx(0.5)
    assert result["quote_attribution_coverage"] == pytest.approx(1.0)


def test_evaluate_payload_scores_thread_group_and_long_thread_survival():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="thread-001",
        bucket="thread_process",
        question="Which thread contains the handoff?",
        expected_thread_group_id="thread-1",
        expected_thread_group_source="inferred",
        triage_tags=["long_thread"],
    )
    payload = {
        "conversation_groups": [{"thread_group_id": "thread-1"}],
        "timeline": {"events": [{"uid": "uid-1"}]},
        "final_answer": {"text": "The handoff is in thread 1."},
        "answer_quality": {
            "top_thread_group_id": "thread-1",
            "top_thread_group_source": "inferred",
        },
    }

    result = evaluate_payload(case, payload, source="live")

    assert result["thread_group_id_match"] is True
    assert result["thread_group_source_match"] is True
    assert result["long_thread_answer_present"] is True
    assert result["long_thread_structure_preserved"] is True


def test_summarize_evaluation_reports_only_active_metrics():
    from mailarium.qa_eval import summarize_evaluation

    summary = summarize_evaluation(
        [
            {
                "id": "fact-1",
                "bucket": "fact_lookup",
                "support_uid_hit": True,
                "support_uid_recall": 1.0,
                "evidence_precision": 1.0,
                "forbidden_support_ids_excluded": True,
            },
            {
                "id": "fact-2",
                "bucket": "fact_lookup",
                "support_uid_hit": False,
                "support_uid_recall": 0.0,
                "evidence_precision": 0.5,
                "forbidden_support_ids_excluded": False,
            },
        ]
    )

    assert summary["total_cases"] == 2
    assert summary["support_uid_hit"] == {"scorable": 2, "passed": 1, "failed": 1}
    assert summary["support_uid_recall"]["average"] == pytest.approx(0.5)
    assert summary["evidence_precision"]["average"] == pytest.approx(0.75)
    assert summary["forbidden_support_ids_excluded"]["failed"] == 1
