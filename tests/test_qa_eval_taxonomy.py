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


def test_build_failure_taxonomy_does_not_flag_product_only_case_as_missing_supported_hit():
    from src.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(
            id="legal-support-product-001",
            bucket="legal_support_workspace",
            question="Do the legal-support products exist?",
            expected_legal_support_products=["case_dashboard"],
        )
    ]
    results = [
        {
            "id": "legal-support-product-001",
            "bucket": "legal_support_workspace",
            "count": 0,
            "support_uid_hit": None,
            "support_source_id_hit": None,
            "top_uid_match": None,
            "evidence_precision": None,
            "legal_support_product_completeness": True,
            "legal_support_grounding_hit": None,
            "answer_content_match": None,
        }
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert "retrieval_recall" not in taxonomy["categories"]


def test_build_failure_taxonomy_flags_support_source_grounding_and_benchmark_regressions():
    from src.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(
            id="fact-benchmark-001",
            bucket="fact_lookup",
            question="Who sent the complaint note?",
            expected_support_uids=["uid-1"],
            expected_support_source_ids=["email:uid-1"],
            expected_top_uid="uid-1",
        )
    ]
    results = [
        {
            "id": "fact-benchmark-001",
            "bucket": "fact_lookup",
            "count": 1,
            "support_uid_hit": True,
            "support_source_id_hit": False,
            "support_source_id_recall": 0.0,
            "top_uid_match": True,
            "evidence_precision": 1.0,
            "benchmark_actor_recovery": 0.0,
            "benchmark_actor_recovery_total": 1,
            "benchmark_issue_family_recovery": 0.5,
            "benchmark_issue_family_recovery_total": 1,
            "benchmark_chronology_anchor_recovery": None,
            "benchmark_chronology_anchor_recovery_total": 0,
            "benchmark_manifest_link_recovery": None,
            "benchmark_manifest_link_recovery_total": 0,
            "benchmark_report_recovery": 1.0,
            "benchmark_report_recovery_total": 1,
        }
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert taxonomy["categories"]["retrieval_recall"]["drivers"] == [
        "support_source_grounding_missing",
        "support_source_grounding_recall_below_one",
        "benchmark_actor_recovery_zero",
        "benchmark_issue_family_recovery_partial",
    ]


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
    assert taxonomy["categories"]["counter_indicator_handling"]["drivers"] == ["counter_indicator_quality_below_one"]
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
