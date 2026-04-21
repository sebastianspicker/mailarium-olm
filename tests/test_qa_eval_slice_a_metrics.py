import pytest


def test_same_name_attachment_hard_negative_stays_non_exact() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-001",
        bucket="attachment_same_name_hard_negative",
        question="Which attachment contains the signed excerpt?",
        expected_support_uids=["uid-correct"],
        benchmark_pack={
            "slice_a": {
                "near_exact_support_source_ids": ["attachment:uid-correct:anlage.pdf"],
                "forbidden_exact_source_ids": ["attachment:uid-wrong:anlage.pdf"],
                "require_locator_coverage": True,
            }
        },
    )
    payload = {
        "attachment_candidates": [
            {
                "uid": "uid-correct",
                "source_id": "attachment:uid-correct:anlage.pdf",
                "quote_match_class": "near_exact",
                "document_locator": {"attachment_id": "att-1", "surface_id": "native_verbatim", "page": 2},
                "attachment": {"extraction_state": "text_extracted", "evidence_strength": "strong_text", "text_available": True},
            },
            {
                "uid": "uid-wrong",
                "source_id": "attachment:uid-wrong:anlage.pdf",
                "quote_match_class": "near_exact",
                "document_locator": {"attachment_id": "att-2", "surface_id": "native_verbatim", "page": 1},
                "attachment": {"extraction_state": "text_extracted", "evidence_strength": "strong_text", "text_available": True},
            },
        ],
        "quote_attribution_metrics": {
            "near_exact_support_source_ids": ["attachment:uid-correct:anlage.pdf"],
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert "slice_a_exact_verified_quote_rate" not in result
    assert result["slice_a_near_exact_quote_rate"] == pytest.approx(1.0)
    assert result["slice_a_false_exact_flag"] == pytest.approx(0.0)
    assert result["slice_a_locator_completeness"] == pytest.approx(1.0)


def test_wrong_attachment_quote_match_is_scored_as_failure() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-002",
        bucket="wrong_attachment_quote_match",
        question="Is this quote grounded in the right file?",
        expected_support_uids=["uid-right"],
        benchmark_pack={
            "slice_a": {
                "near_exact_support_source_ids": ["attachment:uid-right:zitat.pdf"],
                "forbidden_exact_source_ids": ["attachment:uid-wrong:zitat.pdf"],
                "require_locator_coverage": True,
            }
        },
    )
    payload = {
        "attachment_candidates": [
            {
                "uid": "uid-right",
                "source_id": "attachment:uid-right:zitat.pdf",
                "quote_match_class": "near_exact",
                "document_locator": {"attachment_id": "att-right", "surface_id": "native_verbatim", "page": 2},
                "attachment": {"extraction_state": "text_extracted", "evidence_strength": "strong_text", "text_available": True},
            },
            {
                "uid": "uid-wrong",
                "source_id": "attachment:uid-wrong:zitat.pdf",
                "quote_match_class": "exact",
                "document_locator": {"attachment_id": "att-wrong", "surface_id": "native_verbatim", "page": 4},
                "attachment": {"extraction_state": "text_extracted", "evidence_strength": "strong_text", "text_available": True},
            },
        ],
        "quote_attribution_metrics": {
            "near_exact_support_source_ids": ["attachment:uid-right:zitat.pdf"],
            "exact_support_source_ids": ["attachment:uid-wrong:zitat.pdf"],
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["slice_a_near_exact_quote_rate"] == pytest.approx(1.0)
    assert result["slice_a_false_exact_flag"] == pytest.approx(1.0)


def test_authored_german_plus_quoted_english_stays_german_primary() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-003",
        bucket="authored_german_quoted_english",
        question="Which language should dominate?",
        benchmark_pack={"slice_a": {"expected_authored_language": "de", "expected_quoted_language": "en"}},
    )
    payload = {
        "language_analytics": {
            "authored_dominant_language": "de",
            "quoted_dominant_language": "en",
        }
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["slice_a_authored_german_primary_match"] is True


def test_weak_ocr_case_is_near_exact_but_not_exact() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-004",
        bucket="weak_ocr_near_exact",
        question="How should weak OCR be classified?",
        expected_support_uids=["uid-ocr"],
        triage_tags=["attachment_ocr"],
        benchmark_pack={
            "slice_a": {
                "near_exact_support_source_ids": ["attachment:uid-ocr:scan.pdf"],
                "forbidden_exact_source_ids": ["attachment:uid-ocr:scan.pdf"],
                "require_locator_coverage": True,
                "require_ocr_attachment_recall": True,
            }
        },
    )
    payload = {
        "attachment_candidates": [
            {
                "uid": "uid-ocr",
                "source_id": "attachment:uid-ocr:scan.pdf",
                "quote_match_class": "near_exact",
                "document_locator": {"attachment_id": "att-ocr", "surface_id": "ocr_verbatim", "page": 1},
                "attachment": {
                    "extraction_state": "ocr_text_extracted",
                    "evidence_strength": "strong_text",
                    "text_available": True,
                    "ocr_used": True,
                },
            }
        ],
        "quote_attribution_metrics": {
            "near_exact_support_source_ids": ["attachment:uid-ocr:scan.pdf"],
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert "slice_a_exact_verified_quote_rate" not in result
    assert result["slice_a_near_exact_quote_rate"] == pytest.approx(1.0)
    assert result["slice_a_false_exact_flag"] == pytest.approx(0.0)
    assert result["slice_a_ocr_heavy_attachment_recall"] is True


def test_calendar_only_exclusion_remains_benchmark_visible() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-005",
        bucket="calendar_only_exclusion",
        question="Is calendar-only evidence visible?",
        benchmark_pack={
            "slice_a": {
                "require_calendar_evidence": True,
                "required_source_types": ["calendar_event"],
            }
        },
    )
    payload = {
        "multi_source_case_bundle": {
            "sources": [
                {"source_type": "calendar_event"},
            ]
        }
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["slice_a_calendar_exclusion_visible"] is True
    assert result["slice_a_mixed_source_completeness"] == pytest.approx(1.0)


def test_silence_omission_case_requires_reply_edge_and_anchor() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-006",
        bucket="silence_omission_chain",
        question="Is silence anchored?",
        benchmark_pack={"slice_a": {"require_reply_expectation_anchor": True}},
    )
    payload = {
        "reply_pairing": {
            "expected_reply_edges": [
                {"request_uid": "uid-a", "status": "missing"},
            ]
        },
        "timeline": {
            "events": [
                {"uid": "uid-a"},
            ]
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["slice_a_silence_omission_anchor_match"] is True


def test_contradiction_pair_precision_uses_two_locator_backed_sources() -> None:
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="slice-a-007",
        bucket="promise_then_denial",
        question="Is contradiction quality high enough?",
        benchmark_pack={"slice_a": {"required_contradiction_pairs": 1}},
    )
    payload = {
        "finding_evidence_index": {
            "findings": [
                {
                    "contradiction_pairs": [
                        {
                            "left": {"source_id": "email:uid-1", "locator": {"message_id": "<m1>", "char_span": [1, 8]}},
                            "right": {"source_id": "email:uid-2", "locator": {"message_id": "<m2>", "char_span": [2, 9]}},
                        },
                        {
                            "left": {"source_id": "email:uid-3"},
                            "right": {"source_id": "email:uid-3"},
                        },
                    ]
                }
            ]
        }
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["slice_a_contradiction_pair_precision"] == pytest.approx(0.5)
