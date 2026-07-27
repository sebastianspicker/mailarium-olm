"""QA evaluation scoring for attachment channels, OCR evidence, and weak references."""


def test_evaluate_payload_scores_attachment_channel_success():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="attach-001",
        bucket="attachment_lookup",
        question="Which attachment contains the budget spreadsheet?",
        expected_support_uids=["uid-att-1"],
        expected_top_uid="uid-att-1",
        expected_ambiguity="clear",
    )
    payload = {
        "count": 1,
        "candidates": [],
        "attachment_candidates": [
            {
                "uid": "uid-att-1",
                "score": 0.88,
                "attachment": {
                    "extraction_state": "text_extracted",
                    "evidence_strength": "strong_text",
                    "text_available": True,
                },
            },
        ],
        "answer_quality": {
            "top_candidate_uid": "uid-att-1",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["attachment_answer_success"] is True
    assert result["attachment_support_uid_hit"] is True
    assert result["attachment_text_evidence_success"] is True
    assert result["attachment_ocr_text_evidence_success"] is None


def test_evaluate_payload_scores_ocr_attachment_text_evidence_separately():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="attach-ocr-001",
        bucket="attachment_lookup",
        question="What did the scanned invoice say?",
        expected_support_uids=["uid-att-ocr-1"],
        expected_top_uid="uid-att-ocr-1",
        expected_ambiguity="clear",
        triage_tags=["attachment_ocr"],
    )
    payload = {
        "count": 1,
        "candidates": [],
        "attachment_candidates": [
            {
                "uid": "uid-att-ocr-1",
                "score": 0.9,
                "attachment": {
                    "extraction_state": "ocr_text_extracted",
                    "evidence_strength": "strong_text",
                    "text_available": True,
                    "ocr_used": True,
                },
            },
        ],
        "answer_quality": {
            "top_candidate_uid": "uid-att-ocr-1",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["attachment_text_evidence_success"] is True
    assert result["attachment_ocr_text_evidence_success"] is True


def test_evaluate_payload_marks_weak_attachment_reference_separately():
    from mailarium.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="attach-weak-001",
        bucket="attachment_lookup",
        question="Which attachment contains the archive?",
        expected_support_uids=["uid-att-2"],
        expected_top_uid="uid-att-2",
        expected_ambiguity="clear",
    )
    payload = {
        "count": 1,
        "candidates": [],
        "attachment_candidates": [
            {
                "uid": "uid-att-2",
                "score": 0.82,
                "attachment": {
                    "extraction_state": "binary_only",
                    "evidence_strength": "weak_reference",
                    "text_available": False,
                    "failure_reason": "no_text_extracted",
                },
            }
        ],
        "answer_quality": {
            "top_candidate_uid": "uid-att-2",
            "confidence_label": "medium",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["attachment_support_uid_hit"] is True
    assert result["attachment_answer_success"] is True
    assert result["attachment_text_evidence_success"] is False
    assert result["attachment_ocr_text_evidence_success"] is None
