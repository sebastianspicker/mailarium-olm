"""Exercises QA failure classification and remediation ranking so scored deficiencies take precedence over noise."""


def test_build_failure_taxonomy_classifies_generic_failures():
    from mailarium.qa_eval import QuestionCase, build_failure_taxonomy

    cases = [
        QuestionCase(id="fact-1", bucket="fact_lookup", question="Who approved it?"),
        QuestionCase(id="attach-1", bucket="attachment_lookup", question="Which file?"),
    ]
    results = [
        {
            "id": "fact-1",
            "support_uid_hit": False,
            "support_source_id_hit": False,
            "evidence_precision": 0.5,
            "forbidden_support_ids_excluded": False,
        },
        {
            "id": "attach-1",
            "attachment_answer_success": True,
            "attachment_text_evidence_success": False,
        },
    ]

    taxonomy = build_failure_taxonomy(cases, results)

    assert taxonomy["total_flagged_cases"] == 2
    assert taxonomy["categories"]["retrieval_recall"]["failed_cases"] == 1
    assert "evidence_precision_below_one" in taxonomy["categories"]["retrieval_recall"]["drivers"]
    assert taxonomy["categories"]["negative_controls"]["case_ids"] == ["fact-1"]
    assert taxonomy["categories"]["attachment_extraction"]["weak_cases"] == 1


def test_build_failure_taxonomy_ignores_unscored_metrics():
    from mailarium.qa_eval import QuestionCase, build_failure_taxonomy

    taxonomy = build_failure_taxonomy(
        [QuestionCase(id="open-1", bucket="exploration", question="What is relevant?")],
        [{"id": "open-1", "support_uid_hit": None, "answer_content_match": None}],
    )

    assert taxonomy == {"total_flagged_cases": 0, "categories": {}, "ranked_categories": []}


def test_build_remediation_summary_ranks_failed_before_weak():
    from mailarium.qa_eval import build_remediation_summary

    summary = build_remediation_summary(
        {
            "summary": {"total_cases": 3, "bucket_counts": {"fact_lookup": 3}},
            "failure_taxonomy": {
                "total_flagged_cases": 3,
                "ranked_categories": [
                    {"category": "weak", "failed_cases": 0, "weak_cases": 2},
                    {"category": "failed", "failed_cases": 2, "weak_cases": 0},
                ],
            },
        }
    )

    assert summary["immediate_next_targets"][0]["category"] == "failed"
    assert summary["immediate_next_targets"][0]["priority_score"] == 6
