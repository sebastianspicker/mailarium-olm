import asyncio
import json
from pathlib import Path

import pytest


def _make_email(*, subject: str, sender_email: str, body_text: str, has_attachments: bool = False):
    from src.parse_olm import Email

    return Email(
        message_id=f"<{subject}-{sender_email}>",
        subject=subject,
        sender_name=sender_email.split("@", 1)[0].title(),
        sender_email=sender_email,
        to=["team@example.com"],
        cc=[],
        bcc=[],
        date="2026-04-10T10:00:00Z",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=has_attachments,
        attachment_names=["budget.xlsx"] if has_attachments else [],
        attachments=(
            [{"name": "budget.xlsx", "mime_type": "application/vnd.ms-excel", "size": 1234, "content_id": "", "is_inline": False}]
            if has_attachments
            else []
        ),
    )


def test_load_question_cases_reads_template_object(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "question": "Who asked for the updated budget?",
                        "expected_support_uids": ["uid-1"],
                        "triage_tags": ["retrieval_recall"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert len(cases) == 1
    assert cases[0].id == "fact-001"
    assert cases[0].expected_support_uids == ["uid-1"]
    assert cases[0].triage_tags == ["retrieval_recall"]


def test_load_question_cases_reads_case_scope_and_bundle_expectations(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "investigation-001",
                        "bucket": "investigation_case",
                        "question": "Analyze the quick and dirty conversation.",
                        "case_scope": {
                            "target_person": {"name": "Alex Example"},
                            "suspected_actors": [{"name": "Morgan Manager", "email": "manager@example.com"}],
                            "allegation_focus": ["hostility", "exclusion"],
                            "analysis_goal": "internal_review",
                        },
                        "expected_case_bundle_uids": ["uid-1", "uid-2"],
                        "expected_source_types": ["email"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert len(cases) == 1
    assert cases[0].case_scope is not None
    assert cases[0].case_scope.analysis_goal == "internal_review"
    assert cases[0].expected_case_bundle_uids == ["uid-1", "uid-2"]
    assert cases[0].expected_source_types == ["email"]


def test_load_question_cases_reads_behavioral_analysis_expectations(tmp_path: Path):
    from src.qa_eval import load_question_cases

    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "behavior-001",
                        "bucket": "explicit_hostility",
                        "question": "Assess the conduct in this message.",
                        "expected_timeline_uids": ["uid-1"],
                        "expected_behavior_ids": ["escalation", "public_correction"],
                        "expected_counter_indicator_markers": ["process friction"],
                        "expected_max_claim_level": "observed_fact",
                        "expected_report_sections": ["executive_summary", "overall_assessment"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_question_cases(path)

    assert cases[0].expected_timeline_uids == ["uid-1"]
    assert cases[0].expected_behavior_ids == ["escalation", "public_correction"]
    assert cases[0].expected_counter_indicator_markers == ["process friction"]
    assert cases[0].expected_max_claim_level == "observed_fact"
    assert cases[0].expected_report_sections == ["executive_summary", "overall_assessment"]


def test_evaluate_payload_scores_support_and_ambiguity():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="thread-001",
        bucket="thread_process",
        question="How did the budget discussion evolve?",
        expected_support_uids=["uid-2", "uid-3"],
        expected_top_uid="uid-2",
        expected_ambiguity="ambiguous",
    )
    payload = {
        "count": 2,
        "candidates": [
            {"uid": "uid-2", "score": 0.81},
            {"uid": "uid-3", "score": 0.79},
        ],
        "attachment_candidates": [],
        "answer_quality": {
            "top_candidate_uid": "uid-2",
            "confidence_label": "ambiguous",
            "ambiguity_reason": "close_top_scores",
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["top_1_correctness"] is True
    assert result["support_uid_hit"] is True
    assert result["support_uid_hit_top_3"] is True
    assert result["support_uid_recall"] == pytest.approx(1.0)
    assert result["evidence_precision"] == pytest.approx(1.0)
    assert result["top_uid_match"] is True
    assert result["ambiguity_match"] is True
    assert result["confidence_calibration_match"] is True
    assert result["matched_support_uids"] == ["uid-2", "uid-3"]


def test_evaluate_payload_scores_case_bundle_completeness():
    from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="investigation-001",
        bucket="investigation_case",
        question="Analyze the quick and dirty conversation.",
        case_scope=BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example"),
            suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
            allegation_focus=["hostility", "exclusion"],
            analysis_goal="internal_review",
        ),
        expected_case_bundle_uids=["uid-2", "uid-3"],
        expected_source_types=["email"],
    )
    payload = {
        "count": 2,
        "candidates": [
            {"uid": "uid-2", "score": 0.88},
            {"uid": "uid-3", "score": 0.84},
        ],
        "attachment_candidates": [],
        "case_bundle": {"bundle_id": "case-1"},
        "actor_identity_graph": {"actors": []},
        "case_patterns": {"behavior_patterns": []},
        "finding_evidence_index": {"version": "1", "findings": []},
        "evidence_table": {"version": "1", "rows": []},
        "quote_attribution_metrics": {"version": "1"},
        "multi_source_case_bundle": {"sources": [{"source_type": "email"}]},
        "answer_quality": {
            "top_candidate_uid": "uid-2",
            "confidence_label": "high",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="live")

    assert result["case_bundle_present"] is True
    assert result["investigation_blocks_present"] is True
    assert result["case_bundle_support_uid_hit"] is True
    assert result["case_bundle_support_uid_recall"] == pytest.approx(1.0)
    assert result["multi_source_source_types_match"] is True


def test_evaluate_payload_scores_behavioral_analysis_metrics():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="behavior-002",
        bucket="retaliation_case",
        question="Assess whether this record suggests retaliation.",
        expected_support_uids=["uid-ret-1"],
        expected_top_uid="uid-ret-1",
        expected_ambiguity="clear",
        expected_timeline_uids=["uid-ret-1", "uid-ret-2"],
        expected_behavior_ids=["escalation", "public_correction"],
        expected_counter_indicator_markers=["independent operational developments", "process friction"],
        expected_max_claim_level="pattern_concern",
        expected_report_sections=["executive_summary", "overall_assessment", "missing_information"],
    )
    payload = {
        "count": 1,
        "candidates": [
            {
                "uid": "uid-ret-1",
                "score": 0.9,
                "message_findings": {
                    "authored_text": {
                        "behavior_candidates": [
                            {"behavior_id": "escalation"},
                            {"behavior_id": "public_correction"},
                        ],
                        "counter_indicators": [
                            (
                                "Some rhetorical cues remained wording-only because "
                                "message-level behavioural support was insufficient."
                            )
                        ],
                    },
                    "quoted_blocks": [],
                },
            }
        ],
        "attachment_candidates": [],
        "timeline": {
            "events": [
                {"uid": "uid-ret-1"},
                {"uid": "uid-ret-2"},
            ]
        },
        "finding_evidence_index": {
            "findings": [
                {
                    "finding_id": "ret-1",
                    "counter_indicators": [],
                    "alternative_explanations": [
                        "Before/after changes may reflect independent operational developments rather than retaliation.",
                        "The pattern may reflect repeated process friction rather than targeted hostility.",
                    ],
                }
            ]
        },
        "investigation_report": {
            "sections": {
                "executive_summary": {
                    "status": "supported",
                    "entries": [
                        {
                            "claim_level": "pattern_concern",
                            "alternative_explanations": [
                                "Before/after changes may reflect independent operational developments rather than retaliation."
                            ],
                            "ambiguity_disclosures": [],
                        }
                    ],
                },
                "overall_assessment": {
                    "status": "supported",
                    "entries": [
                        {
                            "claim_level": "pattern_concern",
                            "alternative_explanations": [
                                "The pattern may reflect repeated process friction rather than targeted hostility."
                            ],
                            "ambiguity_disclosures": [],
                        }
                    ],
                },
                "missing_information": {
                    "status": "supported",
                    "entries": [{"statement": "No explicit trigger events were supplied."}],
                },
            }
        },
        "answer_quality": {
            "top_candidate_uid": "uid-ret-1",
            "confidence_label": "medium",
            "ambiguity_reason": None,
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["chronology_uid_hit"] is True
    assert result["chronology_uid_recall"] == pytest.approx(1.0)
    assert result["behavior_tag_coverage"] == pytest.approx(1.0)
    assert result["behavior_tag_precision"] == pytest.approx(1.0)
    assert result["counter_indicator_quality"] == pytest.approx(1.0)
    assert result["overclaim_guard_match"] is True
    assert result["report_completeness"] is True


def test_evaluate_payload_handles_insufficient_result():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="weak-001",
        bucket="ambiguity_stress",
        question="Which message contained the scan?",
        expected_ambiguity="insufficient",
    )
    payload = {
        "count": 0,
        "candidates": [],
        "attachment_candidates": [],
        "answer_quality": {
            "top_candidate_uid": None,
            "confidence_label": "low",
            "ambiguity_reason": "no_results",
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["top_uid"] is None
    assert result["ambiguity_match"] is True
    assert result["confidence_calibration_match"] is True


def test_evaluate_payload_scores_weak_evidence_explained():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="weak-002",
        bucket="ambiguity_stress",
        question="Which source-shell message discussed the certificate?",
        expected_support_uids=["uid-weak-1"],
        expected_top_uid="uid-weak-1",
        expected_ambiguity="insufficient",
    )
    payload = {
        "count": 1,
        "candidates": [
            {
                "uid": "uid-weak-1",
                "score": 0.71,
                "weak_message": {
                    "code": "source_shell_only",
                    "label": "Source-shell message",
                },
            }
        ],
        "attachment_candidates": [],
        "answer_quality": {
            "top_candidate_uid": "uid-weak-1",
            "confidence_label": "low",
            "ambiguity_reason": "source_shell_only",
        },
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["weak_evidence_explained"] is True


def test_evaluate_payload_scores_attachment_channel_success():
    from src.qa_eval import QuestionCase, evaluate_payload

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
    from src.qa_eval import QuestionCase, evaluate_payload

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
    from src.qa_eval import QuestionCase, evaluate_payload

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
                    "authored_speaker": {"email": "alice@example.com"},
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
                    "authored_speaker": {"email": "alice@example.com"},
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


def test_build_failure_taxonomy_classifies_weak_and_failed_cases():
    from src.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(
            id="attach-weak-001",
            bucket="attachment_lookup",
            question="Which attachment contains the archive?",
            triage_tags=["attachment_extraction"],
            expected_support_uids=["uid-att-2"],
            expected_top_uid="uid-att-2",
            expected_ambiguity="clear",
        ),
        QuestionCase(
            id="thread-weak-001",
            bucket="thread_process",
            question="When did the reboot thread begin?",
            expected_support_uids=["uid-thread-1"],
            expected_top_uid="uid-thread-1",
            expected_ambiguity="clear",
        ),
    ]
    results = [
        {
            "id": "attach-weak-001",
            "bucket": "attachment_lookup",
            "top_1_correctness": True,
            "support_uid_hit": True,
            "support_uid_hit_top_3": True,
            "support_uid_recall": 1.0,
            "evidence_precision": 1.0,
            "top_uid_match": True,
            "ambiguity_match": True,
            "confidence_calibration_match": True,
            "attachment_support_uid_hit": True,
            "attachment_answer_success": True,
            "attachment_text_evidence_success": False,
            "attachment_ocr_text_evidence_success": False,
            "weak_evidence_explained": None,
            "expected_ambiguity": "clear",
            "count": 1,
            "observed_confidence_label": "medium",
            "observed_ambiguity_reason": None,
        },
        {
            "id": "thread-weak-001",
            "bucket": "thread_process",
            "top_1_correctness": True,
            "support_uid_hit": True,
            "support_uid_hit_top_3": True,
            "support_uid_recall": 1.0,
            "evidence_precision": 0.3333333333333333,
            "top_uid_match": True,
            "ambiguity_match": True,
            "confidence_calibration_match": True,
            "attachment_support_uid_hit": None,
            "attachment_answer_success": None,
            "attachment_text_evidence_success": None,
            "attachment_ocr_text_evidence_success": None,
            "weak_evidence_explained": None,
            "expected_ambiguity": "clear",
            "count": 3,
            "observed_confidence_label": "medium",
            "observed_ambiguity_reason": None,
        },
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert taxonomy["total_flagged_cases"] == 2
    assert taxonomy["ranked_categories"][0]["category"] == "attachment_extraction"
    assert taxonomy["categories"]["attachment_extraction"]["case_ids"] == ["attach-weak-001"]
    assert taxonomy["categories"]["attachment_extraction"]["weak_cases"] == 1
    assert taxonomy["categories"]["retrieval_recall"]["case_ids"] == ["thread-weak-001"]
    assert taxonomy["categories"]["retrieval_recall"]["drivers"] == ["evidence_precision_below_one"]


def test_build_failure_taxonomy_classifies_long_thread_structure_failures():
    from src.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(
            id="long-thread-002",
            bucket="thread_process",
            question="Which message anchors the packed long thread?",
            triage_tags=["long_thread"],
            expected_support_uids=["uid-long-1"],
            expected_top_uid="uid-long-1",
            expected_ambiguity="clear",
        )
    ]
    results = [
        {
            "id": "long-thread-002",
            "bucket": "thread_process",
            "top_1_correctness": True,
            "support_uid_hit": True,
            "support_uid_hit_top_3": True,
            "support_uid_recall": 1.0,
            "evidence_precision": 1.0,
            "top_uid_match": True,
            "ambiguity_match": True,
            "confidence_calibration_match": True,
            "attachment_support_uid_hit": None,
            "attachment_answer_success": None,
            "attachment_text_evidence_success": None,
            "attachment_ocr_text_evidence_success": None,
            "weak_evidence_explained": None,
            "quote_attribution_precision": None,
            "quote_attribution_coverage": None,
            "thread_group_id_match": None,
            "thread_group_source_match": None,
            "long_thread_answer_present": True,
            "long_thread_structure_preserved": False,
            "expected_ambiguity": "clear",
            "count": 1,
            "observed_confidence_label": "high",
            "observed_ambiguity_reason": None,
        }
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert taxonomy["categories"]["long_thread_summarization"]["case_ids"] == ["long-thread-002"]
    assert taxonomy["categories"]["long_thread_summarization"]["drivers"] == ["missing_long_thread_structure"]


def test_build_failure_taxonomy_ignores_unlabeled_quote_observations():
    from src.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(
            id="thread-quote-unlabeled-001",
            bucket="thread_process",
            question="What happened in the reboot thread?",
            expected_support_uids=["uid-thread-quote-1"],
            expected_top_uid="uid-thread-quote-1",
            expected_ambiguity="clear",
        )
    ]
    results = [
        {
            "id": "thread-quote-unlabeled-001",
            "bucket": "thread_process",
            "top_1_correctness": True,
            "support_uid_hit": True,
            "support_uid_hit_top_3": True,
            "support_uid_recall": 1.0,
            "evidence_precision": 1.0,
            "top_uid_match": True,
            "ambiguity_match": True,
            "confidence_calibration_match": True,
            "attachment_support_uid_hit": None,
            "attachment_answer_success": None,
            "attachment_text_evidence_success": None,
            "attachment_ocr_text_evidence_success": None,
            "weak_evidence_explained": None,
            "quote_attribution_precision": None,
            "quote_attribution_coverage": None,
            "expected_ambiguity": "clear",
            "count": 1,
            "observed_confidence_label": "high",
            "observed_ambiguity_reason": None,
        }
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert taxonomy["total_flagged_cases"] == 0
    assert taxonomy["ranked_categories"] == []
    assert taxonomy["categories"] == {}


def test_build_failure_taxonomy_classifies_behavioral_analysis_failures():
    from src.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(
            id="behavior-weak-001",
            bucket="retaliation_case",
            question="Assess whether this record suggests retaliation.",
        )
    ]
    results = [
        {
            "id": "behavior-weak-001",
            "bucket": "retaliation_case",
            "top_1_correctness": True,
            "support_uid_hit": True,
            "support_uid_hit_top_3": True,
            "support_uid_recall": 1.0,
            "evidence_precision": 1.0,
            "top_uid_match": True,
            "ambiguity_match": True,
            "confidence_calibration_match": True,
            "attachment_support_uid_hit": None,
            "attachment_answer_success": None,
            "attachment_text_evidence_success": None,
            "attachment_ocr_text_evidence_success": None,
            "weak_evidence_explained": None,
            "quote_attribution_precision": None,
            "quote_attribution_coverage": None,
            "thread_group_id_match": None,
            "thread_group_source_match": None,
            "long_thread_answer_present": None,
            "long_thread_structure_preserved": None,
            "case_bundle_present": None,
            "investigation_blocks_present": None,
            "case_bundle_support_uid_hit": None,
            "case_bundle_support_uid_recall": None,
            "multi_source_source_types_match": None,
            "chronology_uid_hit": False,
            "chronology_uid_recall": 0.0,
            "behavior_tag_coverage": 0.5,
            "behavior_tag_precision": 0.5,
            "counter_indicator_quality": 0.0,
            "overclaim_guard_match": False,
            "report_completeness": False,
            "expected_ambiguity": "clear",
            "count": 1,
            "observed_confidence_label": "medium",
            "observed_ambiguity_reason": None,
        }
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert taxonomy["categories"]["behavioral_tagging"]["drivers"] == [
        "behavior_tag_coverage_below_one",
        "behavior_tag_precision_below_one",
    ]
    assert taxonomy["categories"]["overclaiming_guard"]["drivers"] == ["claim_level_exceeds_label_ceiling"]
    assert taxonomy["categories"]["counter_indicator_handling"]["drivers"] == [
        "counter_indicator_quality_below_one"
    ]
    assert taxonomy["categories"]["chronology_analysis"]["drivers"] == [
        "missing_timeline_anchor",
        "timeline_recall_below_one",
    ]
    assert taxonomy["categories"]["report_completeness"]["drivers"] == ["missing_supported_report_sections"]


def test_build_remediation_summary_ranks_categories_and_tracks():
    from src.qa_eval import build_remediation_summary

    report = {
        "summary": {
            "total_cases": 6,
            "bucket_counts": {"fact_lookup": 2, "attachment_lookup": 2, "thread_process": 2},
            "top_1_correctness": {"scorable": 6, "passed": 1, "failed": 5},
            "support_uid_hit_top_3": {"scorable": 6, "passed": 2, "failed": 4},
            "confidence_calibration_match": {"scorable": 6, "passed": 2, "failed": 4},
        },
        "failure_taxonomy": {
            "total_flagged_cases": 4,
            "ranked_categories": [
                {
                    "category": "retrieval_recall",
                    "flagged_cases": 3,
                    "failed_cases": 3,
                    "weak_cases": 0,
                    "case_ids": ["fact-1", "fact-2", "thread-1"],
                    "drivers": ["no_supported_hit"],
                },
                {
                    "category": "attachment_extraction",
                    "flagged_cases": 2,
                    "failed_cases": 1,
                    "weak_cases": 1,
                    "case_ids": ["attach-1", "attach-2"],
                    "drivers": ["attachment_answer_failed", "weak_attachment_text_evidence"],
                },
            ],
        },
    }

    summary = build_remediation_summary(report)

    assert summary["total_cases"] == 6
    assert summary["failure_taxonomy"]["ranked_categories"][0]["category"] == "retrieval_recall"
    assert summary["failure_taxonomy"]["ranked_categories"][0]["recommended_track"] == "retrieval_quality"
    assert summary["failure_taxonomy"]["ranked_categories"][1]["recommended_track"] == "AQ21"
    assert summary["immediate_next_targets"][0]["category"] == "retrieval_recall"


def test_default_live_report_path_uses_agent_report_convention():
    from src.qa_eval import default_live_report_path

    path = default_live_report_path(Path("docs/agent/qa_eval_questions.core.json"))

    assert path.name == "qa_eval_report.core.live.json"
    assert str(path).endswith("docs/agent/qa_eval_report.core.live.json")


def test_default_live_report_path_uses_backend_specific_suffix():
    from src.qa_eval import default_live_report_path

    path = default_live_report_path(Path("docs/agent/qa_eval_questions.live_expanded.json"), backend="embedding")

    assert path.name == "qa_eval_report.live_expanded.embedding.live.json"
    assert str(path).endswith("docs/agent/qa_eval_report.live_expanded.embedding.live.json")


def test_default_remediation_report_path_uses_agent_report_convention():
    from src.qa_eval import default_remediation_report_path

    path = default_remediation_report_path(Path("docs/agent/qa_eval_report.live_expanded.live.json"))

    assert path.name == "qa_eval_remediation.live_expanded.live.json"
    assert str(path).endswith("docs/agent/qa_eval_remediation.live_expanded.live.json")


def test_query_terms_extracts_lowercase_natural_language_tokens():
    from src.qa_eval import _query_terms

    terms = _query_terms("Which email had attachments and discussed Configurator 2 Blueprints?")

    assert "which" not in terms
    assert "attachments" not in terms
    assert "configurator" in terms
    assert "blueprints" in terms


def test_query_terms_drop_mailbox_noise_but_keep_topic_words():
    from src.qa_eval import _query_terms

    terms = _query_terms("Which image-only message was titled Manual and who sent the HARICA certificate mail?")

    assert "message" not in terms
    assert "sent" not in terms
    assert "mail" not in terms
    assert "manual" in terms
    assert "harica" in terms


def test_run_evaluation_reports_source_counts(tmp_path: Path):
    from src.qa_eval import run_evaluation_sync

    questions_path = tmp_path / "questions.json"
    questions_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "question": "Who asked for the updated budget?",
                        "expected_support_uids": ["uid-1"],
                        "expected_top_uid": "uid-1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "fact-001": {
                    "count": 1,
                    "candidates": [{"uid": "uid-1", "score": 0.91}],
                    "attachment_candidates": [],
                    "answer_quality": {"top_candidate_uid": "uid-1", "confidence_label": "high", "ambiguity_reason": ""},
                }
            }
        ),
        encoding="utf-8",
    )

    report = run_evaluation_sync(questions_path=questions_path, results_path=results_path)

    assert report["source_counts"] == {"captured": 1}


def test_run_qa_eval_live_defaults_to_persistent_report(monkeypatch, tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    output_path = tmp_path / "qa_eval_report.core.live.json"

    monkeypatch.setattr(runner, "ROOT", tmp_path)

    def fake_resolve_live_deps(*, preferred_backend="auto"):
        assert preferred_backend == "auto"
        return object()

    def fake_default_live_report_path(path: Path, *, backend=None) -> Path:
        assert path == questions_path
        assert backend is None
        return output_path

    def fake_run_evaluation_sync(*, questions_path, results_path=None, live_deps=None, limit=None):
        assert questions_path == questions_path
        assert live_deps is not None
        return {"summary": {"total_cases": 0}, "results": []}

    monkeypatch.setattr("src.qa_eval.resolve_live_deps", fake_resolve_live_deps)
    monkeypatch.setattr("src.qa_eval.default_live_report_path", fake_default_live_report_path)
    monkeypatch.setattr("src.qa_eval.run_evaluation_sync", fake_run_evaluation_sync)

    exit_code = runner.main(["--questions", str(questions_path), "--live"])

    assert exit_code == 0
    assert output_path.exists()
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "live"
    assert status["status"] == "ok"
    assert status["output"] == str(output_path)
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["summary"]["total_cases"] == 0
    assert persisted["results"] == []


def test_run_qa_eval_live_embedding_reexecs_into_project_venv(monkeypatch, tmp_path: Path):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    monkeypatch.setattr(runner, "_interpreter_has_module", lambda name: False)
    monkeypatch.setattr(runner, "_project_venv_python", lambda: venv_python)

    seen: dict[str, object] = {}

    class _Completed:
        returncode = 0

    def fake_run(cmd, cwd):
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        return _Completed()

    monkeypatch.setattr("subprocess.run", fake_run)

    exit_code = runner.main(["--questions", str(questions_path), "--live", "--live-backend", "embedding"])

    assert exit_code == 0
    assert seen["cmd"] == [
        str(venv_python),
        str(runner.__file__),
        "--questions",
        str(questions_path),
        "--live",
        "--live-backend",
        "embedding",
    ]


def test_run_qa_eval_live_writes_blocked_report(monkeypatch, tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    questions_path = tmp_path / "qa_eval_questions.core.json"
    questions_path.write_text(json.dumps({"cases": []}), encoding="utf-8")
    output_path = tmp_path / "qa_eval_report.core.live.json"

    def fake_resolve_live_deps(*, preferred_backend="auto"):
        assert preferred_backend == "auto"
        raise ModuleNotFoundError("No module named 'chromadb'")

    def fake_default_live_report_path(path: Path, *, backend=None) -> Path:
        assert path == questions_path
        assert backend is None
        return output_path

    monkeypatch.setattr("src.qa_eval.resolve_live_deps", fake_resolve_live_deps)
    monkeypatch.setattr("src.qa_eval.default_live_report_path", fake_default_live_report_path)

    exit_code = runner.main(["--questions", str(questions_path), "--live"])

    assert exit_code == 1
    assert output_path.exists()
    status = json.loads(capsys.readouterr().out)
    assert status["mode"] == "live"
    assert status["status"] == "blocked"
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["live_status"]["status"] == "blocked"
    assert persisted["live_status"]["error_type"] == "ModuleNotFoundError"
    assert "chromadb" in persisted["live_status"]["error"]


def test_run_qa_eval_remediation_writes_persistent_summary(monkeypatch, tmp_path: Path, capsys):
    import scripts.run_qa_eval as runner

    report_path = tmp_path / "qa_eval_report.live_expanded.live.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total_cases": 3,
                    "bucket_counts": {"fact_lookup": 1, "thread_process": 2},
                    "top_1_correctness": {"scorable": 3, "passed": 1, "failed": 2},
                    "support_uid_hit_top_3": {"scorable": 3, "passed": 1, "failed": 2},
                    "confidence_calibration_match": {"scorable": 3, "passed": 1, "failed": 2},
                },
                "failure_taxonomy": {
                    "total_flagged_cases": 2,
                    "ranked_categories": [
                        {
                            "category": "retrieval_recall",
                            "flagged_cases": 2,
                            "failed_cases": 2,
                            "weak_cases": 0,
                            "case_ids": ["fact-1", "thread-1"],
                            "drivers": ["no_supported_hit"],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "qa_eval_remediation.live_expanded.live.json"

    monkeypatch.setattr(runner, "ROOT", tmp_path)

    exit_code = runner.main(["--remediation-from", str(report_path), "--output", str(output_path)])

    assert exit_code == 0
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["total_cases"] == 3
    assert persisted["failure_taxonomy"]["ranked_categories"][0]["category"] == "retrieval_recall"
    assert json.loads(capsys.readouterr().out)["immediate_next_targets"][0]["category"] == "retrieval_recall"


def test_resolve_live_deps_falls_back_to_sqlite_when_chromadb_missing(monkeypatch, tmp_path: Path):
    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    db.insert_email(
        _make_email(
            subject="Budget request",
            sender_email="alice@example.com",
            body_text="Please send the budget draft.",
        )
    )
    db.close()

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)

    def fake_resolve(email_db, *, preferred_backend="auto"):
        assert preferred_backend == "auto"
        from src.qa_eval import _SQLiteEvalRetriever

        return _SQLiteEvalRetriever(email_db)

    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", fake_resolve)

    try:
        deps = resolve_live_deps()
    finally:
        get_settings.cache_clear()

    assert deps.live_backend == "sqlite_fallback"
    assert deps.get_retriever().backend_name == "sqlite_fallback"


def test_resolve_live_deps_uses_embedding_backend_when_requested(monkeypatch, tmp_path: Path):
    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    db.insert_email(
        _make_email(
            subject="Budget request",
            sender_email="alice@example.com",
            body_text="Please send the budget draft.",
        )
    )
    db.close()

    class _EmbeddingRetriever:
        backend_name = "embedding"

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)
    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", lambda email_db, preferred_backend="auto": _EmbeddingRetriever())

    try:
        deps = resolve_live_deps(preferred_backend="embedding")
    finally:
        get_settings.cache_clear()

    assert deps.live_backend == "embedding"
    assert deps.get_retriever().backend_name == "embedding"


def test_sqlite_live_retriever_returns_real_results(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    db.insert_email(
        _make_email(
            subject="Budget request",
            sender_email="alice@example.com",
            body_text="Please send the updated budget draft for the committee.",
            has_attachments=True,
        )
    )

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="updated budget draft", top_k=5)

    assert results
    assert results[0].metadata["uid"]
    assert any(result.metadata.get("is_attachment") == "True" for result in results)
    assert any("budget" in result.text.lower() for result in results)


def test_sqlite_live_retriever_preserves_attachment_evidence_metadata(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    email = _make_email(
        subject="Invoice scan",
        sender_email="alice@example.com",
        body_text="Please review the scanned invoice attachment.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "invoice-scan.pdf",
            "mime_type": "application/pdf",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "ocr_text_extracted",
            "evidence_strength": "strong_text",
            "ocr_used": True,
            "failure_reason": None,
            "text_preview": "Invoice total 123.45 EUR approved for payment.",
        }
    ]
    db.insert_email(email)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="invoice scan", top_k=5)

    attachment_results = [result for result in results if result.metadata.get("is_attachment") == "True"]
    assert attachment_results
    metadata = attachment_results[0].metadata
    assert metadata["extraction_state"] == "ocr_text_extracted"
    assert metadata["evidence_strength"] == "strong_text"
    assert metadata["ocr_used"] is True
    assert metadata["failure_reason"] in (None, "")
    assert metadata["text_preview"] == "Invoice total 123.45 EUR approved for payment."


def test_sqlite_live_retriever_uses_attachment_text_preview_in_result_text(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    email = _make_email(
        subject="Budget spreadsheet",
        sender_email="alice@example.com",
        body_text="See the attachment.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "budget.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "text_extracted",
            "evidence_strength": "strong_text",
            "ocr_used": False,
            "failure_reason": None,
            "text_preview": "Budget Q4 total: 25000 EUR",
        }
    ]
    db.insert_email(email)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="What does the budget spreadsheet say?", top_k=5)

    attachment_results = [result for result in results if result.metadata.get("is_attachment") == "True"]
    assert attachment_results
    assert "Budget Q4 total: 25000 EUR" in attachment_results[0].text


def test_live_payload_preserves_strong_attachment_text_with_sqlite_preview(tmp_path: Path, monkeypatch):
    import asyncio

    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import QuestionCase, _live_payload, resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    email = _make_email(
        subject="Budget spreadsheet",
        sender_email="alice@example.com",
        body_text="Please review the sheet.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "budget.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "text_extracted",
            "evidence_strength": "strong_text",
            "ocr_used": False,
            "failure_reason": None,
            "text_preview": "Budget Q4 total: 25000 EUR",
        }
    ]
    db.insert_email(email)
    db.close()

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)

    def fake_resolve(email_db, *, preferred_backend="auto"):
        assert preferred_backend == "auto"
        from src.qa_eval import _SQLiteEvalRetriever

        return _SQLiteEvalRetriever(email_db)

    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", fake_resolve)

    try:
        deps = resolve_live_deps()
        payload = asyncio.run(
            _live_payload(
                QuestionCase(
                    id="attach-preview-001",
                    bucket="attachment_lookup",
                    question="What does the budget spreadsheet say?",
                    expected_support_uids=[email.uid],
                ),
                deps,
            )
        )
    finally:
        get_settings.cache_clear()

    assert payload["attachment_candidates"]
    attachment = payload["attachment_candidates"][0]["attachment"]
    assert attachment["evidence_strength"] == "strong_text"
    assert attachment["text_available"] is True
    assert "Budget Q4 total: 25000 EUR" in payload["attachment_candidates"][0]["snippet"]


def test_sqlite_live_retriever_finds_attachment_case_from_natural_language_query(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    email = _make_email(
        subject="MDM",
        sender_email="alice@example.com",
        body_text="Configurator 2 Blueprints stores the blueprints in the Apple Configurator profile path.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "profile.mobileconfig",
            "mime_type": "application/x-apple-aspen-config",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "binary_only",
            "evidence_strength": "weak_reference",
            "ocr_used": False,
            "failure_reason": "no_text_extracted",
        }
    ]
    db.insert_email(email)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(
        query="Which email had attachments and discussed Configurator 2 Blueprints?",
        top_k=5,
        has_attachments=True,
    )

    assert results
    assert results[0].metadata["uid"] == email.uid


def test_sqlite_live_retriever_prefers_subject_topic_match_for_fact_queries(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    generic = _make_email(
        subject="Please confirm your email address",
        sender_email="no-reply@researchgatemail.net",
        body_text="This certificate email requires confirmation.",
    )
    expected = _make_email(
        subject="AW: Zertifikat Harica",
        sender_email="pki@hfmt-koeln.de",
        body_text="Your HARICA certificate is attached.",
    )
    db.insert_email(generic)
    db.insert_email(expected)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="Who sent the HARICA certificate mail?", top_k=5)

    assert results
    assert results[0].metadata["uid"] == expected.uid


def test_sqlite_live_retriever_prefers_earliest_topic_anchor_for_begin_questions(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    early = _make_email(
        subject="Re: Physics Reimagined",
        sender_email="jubobroff@gmail.com",
        body_text="Short reply on the thread.",
    )
    early.date = "2022-06-28T16:04:50"
    late = _make_email(
        subject="Re: [WARNING: UNSCANNABLE EXTRACTION FAILED]RE: Physics Reimagined",
        sender_email="frederic.bouquet@universite-paris-saclay.fr",
        body_text="Physics Reimagined thread notes with repeated Physics Reimagined details.",
    )
    late.date = "2022-07-06T07:21:37"
    db.insert_email(early)
    db.insert_email(late)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="When did the Physics Reimagined thread begin?", top_k=5)

    assert results
    assert results[0].metadata["uid"] == early.uid


def test_sqlite_live_retriever_prefers_exact_title_match_for_titled_queries(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    expected = _make_email(
        subject="Manual",
        sender_email="sebastian.spicker@googlemail.com",
        body_text="",
    )
    distractor = _make_email(
        subject="ICETOL: International Conference on Educational Technology and Online Learning",
        sender_email="events@example.com",
        body_text="Attached manual and conference guide for participants.",
    )
    db.insert_email(expected)
    db.insert_email(distractor)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="Which image-only message was titled Manual?", top_k=5)

    assert results
    assert results[0].metadata["uid"] == expected.uid


def test_sqlite_live_retriever_prefers_exact_forward_topic_over_version_variant(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    older = _make_email(
        subject="Fwd: Aktuelle Version Videographie-Manual",
        sender_email="sebastian.spicker@googlemail.com",
        body_text="Forwarding the current manual version.",
        has_attachments=True,
    )
    older.date = "2022-03-14T14:03:38"
    expected = _make_email(
        subject="Fwd: Videographie-Manual",
        sender_email="sebastian.spicker@googlemail.com",
        body_text="Forwarding the manual thread anchor.",
        has_attachments=True,
    )
    expected.date = "2023-04-21T10:37:09"
    db.insert_email(older)
    db.insert_email(expected)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(
        query="Which forwarded email opened the Videographie-Manual attachment thread?",
        top_k=5,
        has_attachments=True,
    )

    assert results
    assert results[0].metadata["uid"] == expected.uid


def test_resolve_live_deps_uses_sqlite_fallback_backend(monkeypatch, tmp_path: Path):
    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    db.insert_email(
        _make_email(
            subject="Budget request",
            sender_email="alice@example.com",
            body_text="Please send the updated budget draft.",
        )
    )
    db.close()

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)

    def fake_resolve(email_db, *, preferred_backend="auto"):
        assert preferred_backend == "auto"
        from src.qa_eval import _SQLiteEvalRetriever

        return _SQLiteEvalRetriever(email_db)

    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", fake_resolve)

    try:
        deps = resolve_live_deps()
        payload = asyncio.run(
            __import__("src.qa_eval", fromlist=["_live_payload"])._live_payload(
                __import__("src.qa_eval", fromlist=["QuestionCase"]).QuestionCase(
                    id="fact-001",
                    bucket="fact_lookup",
                    question="updated budget draft",
                    expected_support_uids=[],
                ),
                deps,
            )
        )
    finally:
        get_settings.cache_clear()

    assert deps.live_backend == "sqlite_fallback"
    assert payload["count"] >= 1
    assert payload["candidates"][0]["subject"] == "Budget request"


@pytest.mark.asyncio
async def test_run_evaluation_uses_results_payloads(tmp_path: Path):
    from src.qa_eval import run_evaluation

    questions_path = tmp_path / "questions.json"
    results_path = tmp_path / "results.json"

    questions_path.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "fact-001",
                        "bucket": "fact_lookup",
                        "question": "Who asked for the updated budget?",
                        "expected_support_uids": ["uid-1"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    results_path.write_text(
        json.dumps(
            {
                "fact-001": {
                    "count": 1,
                    "candidates": [{"uid": "uid-1", "score": 0.91}],
                    "attachment_candidates": [],
                    "answer_quality": {
                        "top_candidate_uid": "uid-1",
                        "confidence_label": "high",
                        "ambiguity_reason": None,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    report = await run_evaluation(questions_path=questions_path, results_path=results_path)

    assert report["summary"]["total_cases"] == 1
    assert report["results"][0]["support_uid_hit"] is True
    assert report["results"][0]["source"] == "captured"
