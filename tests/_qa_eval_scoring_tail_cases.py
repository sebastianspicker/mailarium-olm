import pytest


def test_evaluate_payload_scores_quote_attribution_precision_and_coverage():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="quote-001",
        bucket="quote_attribution",
        question="Who was being quoted in the vendor thread?",
        expected_support_uids=["uid-quote-1"],
        expected_top_uid="uid-quote-1",
        expected_ambiguity="clear",
        expected_quoted_speaker_emails=["bob@example.com"],
    )
    payload = {
        "count": 1,
        "candidates": [
            {
                "uid": "uid-quote-1",
                "score": 0.87,
                "speaker_attribution": {
                    "authored_speaker": {"email": "employee@example.test"},
                    "quoted_blocks": [
                        {"speaker_email": "bob@example.com", "source": "quoted_from_header", "confidence": 0.65},
                        {"speaker_email": "carol@example.com", "source": "quoted_block_email", "confidence": 0.6},
                    ],
                },
            }
        ],
        "attachment_candidates": [],
        "answer_quality": {
            "top_candidate_uid": "uid-quote-1",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["observed_quoted_speaker_emails"] == ["bob@example.com", "carol@example.com"]
    assert result["quote_attribution_precision"] == pytest.approx(0.5)
    assert result["quote_attribution_coverage"] == pytest.approx(1.0)


def test_evaluate_payload_does_not_score_unlabeled_quote_observations():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="thread-quote-unlabeled-001",
        bucket="thread_process",
        question="What happened in the reboot thread?",
        expected_support_uids=["uid-thread-quote-1"],
        expected_top_uid="uid-thread-quote-1",
        expected_ambiguity="clear",
    )
    payload = {
        "count": 1,
        "candidates": [
            {
                "uid": "uid-thread-quote-1",
                "score": 0.83,
                "speaker_attribution": {
                    "authored_speaker": {"email": "employee@example.test"},
                    "quoted_blocks": [
                        {"speaker_email": "bob@example.com", "source": "quoted_from_header", "confidence": 0.65},
                    ],
                },
            }
        ],
        "attachment_candidates": [],
        "answer_quality": {
            "top_candidate_uid": "uid-thread-quote-1",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="live")

    assert result["observed_quoted_speaker_emails"] == ["bob@example.com"]
    assert result["matched_quoted_speaker_emails"] == []
    assert result["quote_attribution_precision"] is None
    assert result["quote_attribution_coverage"] is None


def test_evaluate_payload_scores_inferred_thread_group_match():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="thread-inferred-001",
        bucket="thread_process",
        question="Which inferred-only thread does this reply belong to?",
        expected_support_uids=["uid-inf-2"],
        expected_top_uid="uid-inf-2",
        expected_ambiguity="clear",
        expected_thread_group_id="thread-inferred-1",
        expected_thread_group_source="inferred",
    )
    payload = {
        "count": 2,
        "candidates": [
            {
                "uid": "uid-inf-2",
                "score": 0.9,
                "conversation_context": {
                    "thread_group_id": "thread-inferred-1",
                    "thread_group_source": "inferred",
                },
            },
            {
                "uid": "uid-inf-1",
                "score": 0.84,
                "conversation_context": {
                    "thread_group_id": "thread-inferred-1",
                    "thread_group_source": "inferred",
                },
            },
        ],
        "attachment_candidates": [],
        "answer_quality": {
            "top_candidate_uid": "uid-inf-2",
            "top_thread_group_id": "thread-inferred-1",
            "top_thread_group_source": "inferred",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["thread_group_id_match"] is True
    assert result["thread_group_source_match"] is True


def test_evaluate_payload_scores_long_thread_budget_survival():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="long-thread-001",
        bucket="thread_process",
        question="Which message anchors the packed long thread?",
        expected_support_uids=["uid-long-1"],
        expected_top_uid="uid-long-1",
        expected_ambiguity="clear",
        triage_tags=["long_thread"],
    )
    payload = {
        "count": 1,
        "candidates": [{"uid": "uid-long-1", "score": 0.91}],
        "attachment_candidates": [],
        "conversation_groups": [{"thread_group_id": "conv-1"}],
        "timeline": {"events": [{"uid": "uid-long-1"}]},
        "final_answer": {"decision": "answer", "text": "Packed answer text [uid:uid-long-1]"},
        "_packed": {"applied": True, "budget_chars": 4000},
        "answer_quality": {
            "top_candidate_uid": "uid-long-1",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="live")

    assert result["long_thread_answer_present"] is True
    assert result["long_thread_structure_preserved"] is True


def test_summarize_evaluation_reports_scorable_counts():
    from src.qa_eval import summarize_evaluation

    summary = summarize_evaluation(
        [
            {
                "id": "fact-001",
                "bucket": "fact_lookup",
                "top_1_correctness": True,
                "support_uid_hit": True,
                "support_uid_hit_top_3": True,
                "support_uid_recall": 1.0,
                "evidence_precision": 1.0,
                "top_uid_match": True,
                "ambiguity_match": None,
                "confidence_calibration_match": True,
                "attachment_answer_success": None,
                "attachment_support_uid_hit": None,
                "attachment_text_evidence_success": None,
                "attachment_ocr_text_evidence_success": None,
                "weak_evidence_explained": None,
                "quote_attribution_precision": None,
                "quote_attribution_coverage": None,
                "thread_group_id_match": None,
                "thread_group_source_match": None,
                "long_thread_answer_present": None,
                "long_thread_structure_preserved": None,
                "chronology_uid_hit": None,
                "chronology_uid_recall": None,
                "behavior_tag_coverage": None,
                "behavior_tag_precision": None,
                "counter_indicator_quality": None,
                "overclaim_guard_match": None,
                "report_completeness": None,
            },
            {
                "id": "thread-001",
                "bucket": "thread_process",
                "top_1_correctness": None,
                "support_uid_hit": False,
                "support_uid_hit_top_3": False,
                "support_uid_recall": 0.0,
                "evidence_precision": 0.0,
                "top_uid_match": None,
                "ambiguity_match": True,
                "confidence_calibration_match": True,
                "attachment_answer_success": None,
                "attachment_support_uid_hit": None,
                "attachment_text_evidence_success": None,
                "attachment_ocr_text_evidence_success": None,
                "weak_evidence_explained": True,
                "quote_attribution_precision": 0.5,
                "quote_attribution_coverage": 1.0,
                "thread_group_id_match": True,
                "thread_group_source_match": False,
                "long_thread_answer_present": True,
                "long_thread_structure_preserved": False,
                "chronology_uid_hit": True,
                "chronology_uid_recall": 0.5,
                "behavior_tag_coverage": 0.5,
                "behavior_tag_precision": 1.0,
                "counter_indicator_quality": 0.5,
                "overclaim_guard_match": False,
                "report_completeness": True,
            },
        ]
    )

    assert summary["total_cases"] == 2
    assert summary["top_1_correctness"]["passed"] == 1
    assert summary["support_uid_hit"]["scorable"] == 2
    assert summary["support_uid_hit"]["passed"] == 1
    assert summary["support_uid_hit_top_3"]["failed"] == 1
    assert summary["support_uid_recall"]["average"] == pytest.approx(0.5)
    assert summary["attachment_ocr_text_evidence_success"] == {"scorable": 0, "passed": 0, "failed": 0}
    assert summary["quote_attribution_precision"]["average"] == pytest.approx(0.5)
    assert summary["quote_attribution_coverage"]["average"] == pytest.approx(1.0)
    assert summary["thread_group_id_match"]["passed"] == 1
    assert summary["thread_group_source_match"]["failed"] == 1
    assert summary["long_thread_answer_present"]["passed"] == 1
    assert summary["long_thread_structure_preserved"]["failed"] == 1
    assert summary["chronology_uid_hit"]["passed"] == 1
    assert summary["chronology_uid_recall"]["average"] == pytest.approx(0.5)
    assert summary["behavior_tag_coverage"]["average"] == pytest.approx(0.5)
    assert summary["behavior_tag_precision"]["average"] == pytest.approx(1.0)
    assert summary["counter_indicator_quality"]["average"] == pytest.approx(0.5)
    assert summary["overclaim_guard_match"]["failed"] == 1
    assert summary["report_completeness"]["passed"] == 1
