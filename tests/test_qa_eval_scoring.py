import pytest

from ._qa_eval_scoring_tail_cases import *  # noqa: F403


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


def test_evaluate_payload_scores_support_source_grounding_and_benchmark_recovery():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="fact-002",
        bucket="fact_lookup",
        question="Who sent the complaint note?",
        expected_support_uids=["uid-1"],
        expected_support_source_ids=["email:uid-1"],
        expected_top_uid="uid-1",
        benchmark_pack={
            "benchmark_id": "bench-1",
            "usage_rule": "evaluation_only_not_search_filter",
            "seed_actors": ["Morgan Manager"],
            "issue_families": ["retaliation"],
            "required_report_sections": ["overall_assessment"],
        },
    )
    payload = {
        "count": 1,
        "candidates": [
            {
                "uid": "uid-1",
                "source_id": "email:uid-1",
                "sender_name": "Morgan Manager",
                "subject": "Retaliation note",
                "score": 0.91,
                "snippet": "Retaliation note.",
                "provenance": {"evidence_handle": "email:uid-1"},
            }
        ],
        "attachment_candidates": [],
        "answer_quality": {"top_candidate_uid": "uid-1", "confidence_label": "high", "ambiguity_reason": None},
        "archive_harvest": {"evidence_bank": [{"sender_name": "Morgan Manager", "subject": "Retaliation note"}]},
        "investigation_report": {"sections": {"overall_assessment": {"status": "supported", "entries": []}}},
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["support_source_id_hit"] is True
    assert result["support_source_id_recall"] == pytest.approx(1.0)
    assert result["benchmark_actor_recovery"] == pytest.approx(1.0)
    assert result["benchmark_issue_family_recovery"] == pytest.approx(1.0)
    assert result["benchmark_report_recovery"] == pytest.approx(1.0)


def test_benchmark_detection_recovery_ignores_incidental_unstructured_mentions():
    from src.qa_eval_bootstrap import benchmark_detection_recovery

    result = benchmark_detection_recovery(
        benchmark_pack={
            "benchmark_id": "bench-structured",
            "seed_actors": ["Morgan Manager"],
            "issue_families": ["retaliation"],
        },
        payload={
            "investigation_report": {
                "notes": "Morgan Manager and retaliation are mentioned here incidentally.",
            },
        },
    )

    assert result["actor_recovery"]["coverage"] == pytest.approx(0.0)
    assert result["issue_family_recovery"]["coverage"] == pytest.approx(0.0)


def test_evaluate_payload_scores_archive_harvest_gates_and_recovery_signals():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="harvest-001",
        bucket="legal_support_workspace",
        question="Did archive harvest preserve mixed-source evidence?",
    )
    payload = {
        "archive_harvest": {
            "coverage_gate": {"status": "pass"},
            "quality_gate": {"status": "pass"},
            "mixed_source_candidate_count": 2,
            "later_round_only_evidence_handles": ["attachment:uid-1:note.pdf"],
            "rerun_rounds": [
                {"round": 0, "recovered_count": 0},
                {"round": 1, "recovered_count": 1},
            ],
        }
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["archive_harvest_coverage_pass"] is True
    assert result["archive_harvest_quality_pass"] is True
    assert result["archive_harvest_mixed_source_present"] is True
    assert result["archive_harvest_later_round_recovery"] is True


def test_evaluate_payload_scores_case_bundle_completeness():
    from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="investigation-001",
        bucket="investigation_case",
        question="Analyze the rapid review conversation.",
        case_scope=BehavioralCaseScopeInput(
            target_person=CasePartyInput(name="Alex Example"),
            suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.com")],
            allegation_focus=["hostility", "exclusion"],
            analysis_goal="internal_review",
        ),
        expected_case_bundle_uids=["uid-2", "uid-3"],
        expected_case_bundle_source_ids=["email:uid-2", "email:uid-3"],
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
        "multi_source_case_bundle": {
            "sources": [
                {"source_type": "email", "source_id": "email:uid-2", "uid": "uid-2"},
                {"source_type": "email", "source_id": "email:uid-3", "uid": "uid-3"},
            ]
        },
        "master_chronology": {
            "entries": [
                {"source_linkage": {"source_ids": ["email:uid-2"], "supporting_uids": ["uid-2"]}},
                {"source_linkage": {"source_ids": ["email:uid-3"], "supporting_uids": ["uid-3"]}},
            ]
        },
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
    assert result["case_bundle_support_source_id_hit"] is True
    assert result["case_bundle_support_source_id_recall"] == pytest.approx(1.0)
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


def test_evaluate_payload_scores_legal_support_metrics():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="legal-support-001",
        bucket="legal_support_workspace",
        question="Evaluate the legal-support workspace outputs for this matter.",
        expected_legal_support_products=[
            "lawyer_issue_matrix",
            "case_dashboard",
            "actor_map",
            "document_request_checklist",
            "controlled_factual_drafting",
        ],
        expected_legal_support_source_ids=["email:uid-1"],
        expected_comparator_issue_ids=["control_intensity"],
        expected_dashboard_cards=["main_claims_or_issues", "main_actors", "recommended_next_actions"],
        expected_actor_ids=["actor-manager", "actor-hr"],
        expected_checklist_group_ids=["calendar_meeting_records", "comparator_evidence"],
        expected_draft_ceiling_level="concern_only",
        expected_draft_sections=["established_facts", "requests_for_clarification", "formal_demands"],
    )
    payload = {
        "lawyer_issue_matrix": {
            "row_count": 1,
            "rows": [{"issue_id": "retaliation_massregelungsverbot", "supporting_source_ids": ["email:uid-1"]}],
        },
        "comparative_treatment": {
            "comparator_summaries": [
                {
                    "comparator_matrix": {
                        "rows": [
                            {
                                "issue_id": "control_intensity",
                                "comparison_strength": "strong",
                                "supporting_source_ids": ["email:uid-1"],
                            },
                        ]
                    }
                }
            ]
        },
        "case_dashboard": {
            "dashboard_format": "refreshable_case_dashboard",
            "summary": {"refreshable_from_shared_entities": True},
            "cards": {
                "main_claims_or_issues": [
                    {"issue_id": "retaliation_massregelungsverbot", "supporting_source_ids": ["email:uid-1"]}
                ],
                "main_actors": [{"actor_id": "actor-manager", "supporting_source_ids": ["email:uid-1"]}],
                "recommended_next_actions": [{"group_id": "calendar_meeting_records", "supporting_source_ids": ["email:uid-1"]}],
            },
        },
        "actor_map": {
            "actors": [
                {"actor_id": "actor-manager"},
                {"actor_id": "actor-hr"},
            ]
        },
        "document_request_checklist": {
            "groups": [
                {"group_id": "calendar_meeting_records", "supporting_source_ids": ["email:uid-1"]},
                {"group_id": "comparator_evidence", "supporting_source_ids": ["email:uid-1"]},
            ]
        },
        "controlled_factual_drafting": {
            "framing_preflight": {"allegation_ceiling": {"ceiling_level": "concern_only"}},
            "controlled_draft": {
                "sections": {
                    "established_facts": [{"item_id": "fact-1", "supporting_source_ids": ["email:uid-1"]}],
                    "requests_for_clarification": [{"item_id": "clarify-1", "supporting_source_ids": ["email:uid-1"]}],
                    "formal_demands": [{"item_id": "demand-1", "supporting_source_ids": ["email:uid-1"]}],
                }
            },
        },
        "final_answer": {"text": "The policy meeting note supports the conclusion."},
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["legal_support_product_completeness"] is True
    assert result["legal_support_grounding_hit"] is True
    assert result["legal_support_grounding_recall"] == pytest.approx(1.0)
    assert result["comparator_matrix_coverage"] == pytest.approx(1.0)
    assert result["dashboard_card_coverage"] == pytest.approx(1.0)
    assert result["actor_map_coverage"] == pytest.approx(1.0)
    assert result["checklist_group_coverage"] == pytest.approx(1.0)
    assert result["drafting_ceiling_match"] is True
    assert result["draft_section_completeness"] is True


def test_evaluate_payload_scores_answer_content_and_forbidden_controls():
    from src.qa_eval import QuestionCase, evaluate_payload

    case = QuestionCase(
        id="guard-001",
        bucket="legal_support_workspace",
        question="Check the grounded answer and forbid unrelated items.",
        expected_answer_terms=["policy", "meeting"],
        forbidden_support_source_ids=["email:uid-forbidden"],
        forbidden_issue_ids=["forbidden_issue"],
        forbidden_actor_ids=["actor-forbidden"],
        forbidden_dashboard_cards=["forbidden_card"],
        forbidden_checklist_group_ids=["forbidden_group"],
    )
    payload = {
        "candidates": [
            {"uid": "uid-1", "provenance": {"evidence_handle": "email:uid-1"}},
        ],
        "attachment_candidates": [],
        "final_answer": {"text": "The policy meeting was confirmed in the record."},
        "case_dashboard": {
            "cards": {
                "main_claims_or_issues": [{"issue_id": "allowed_issue"}],
            }
        },
        "actor_map": {"actors": [{"actor_id": "actor-allowed"}]},
        "document_request_checklist": {"groups": [{"group_id": "allowed_group"}]},
        "lawyer_issue_matrix": {"rows": [{"issue_id": "allowed_issue"}]},
    }

    result = evaluate_payload(case, payload, source="captured")

    assert result["answer_content_match"] is True
    assert result["forbidden_support_ids_excluded"] is True
    assert result["forbidden_issue_ids_excluded"] is True
    assert result["forbidden_actor_ids_excluded"] is True
    assert result["forbidden_dashboard_cards_excluded"] is True
    assert result["forbidden_checklist_groups_excluded"] is True


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
