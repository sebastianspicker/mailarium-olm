from __future__ import annotations

from src.skeptical_employer_review import build_skeptical_employer_review


def test_build_skeptical_employer_review_pairs_weaknesses_with_repair_guidance() -> None:
    payload = build_skeptical_employer_review(
        findings=[
            {
                "finding_id": "ret-1",
                "finding_label": "Retaliatory sequence",
                "finding_scope": "retaliation_analysis",
                "alternative_explanations": [
                    "Before/after changes may reflect independent operational developments rather than retaliation."
                ],
                "supporting_evidence": [{"citation_id": "c-1", "message_or_document_id": "uid-1"}],
                "evidence_strength": {"label": "moderate_indicator"},
                "confidence_split": {"interpretation_confidence": {"label": "medium"}},
            }
        ],
        master_chronology={
            "entries": [
                {
                    "chronology_id": "chron-1",
                    "uid": "uid-gap-1",
                    "source_linkage": {"source_ids": ["email:uid-gap-1"]},
                },
                {
                    "chronology_id": "chron-2",
                    "uid": "uid-gap-2",
                    "source_linkage": {"source_ids": ["email:uid-gap-2"]},
                },
            ],
            "summary": {
                "date_gaps_and_unexplained_sequences": [
                    {"gap_id": "GAP-001", "from_chronology_id": "chron-1", "to_chronology_id": "chron-2"},
                ]
            },
        },
        matter_evidence_index={
            "top_10_missing_exhibits": [
                {
                    "requested_exhibit": "Complaint, objection, HR-contact, or participation-event record",
                }
            ]
        },
        comparative_treatment={
            "summary": {"no_suitable_comparator_count": 1},
            "comparator_points": [
                {
                    "comparator_point_id": "cmp:1",
                    "issue_label": "Control intensity",
                    "comparison_strength": "not_comparable",
                    "missing_proof": ["Role-matched comparator records"],
                }
            ],
        },
        lawyer_issue_matrix={
            "rows": [
                {
                    "title": "Retaliation / Maßregelungsverbot",
                    "legal_relevance_status": "currently_under_supported",
                    "missing_proof": ["Complaint record", "Employer response record"],
                    "supporting_finding_ids": ["ret-1"],
                    "supporting_citation_ids": ["c-1"],
                    "supporting_uids": ["uid-1"],
                }
            ]
        },
        overall_assessment={"primary_assessment": "retaliation_concern"},
        retaliation_timeline_assessment={
            "strongest_non_retaliatory_explanations": [{"explanation": "new_sender_appears_after_trigger"}],
            "temporal_correlation_analysis": [{"confounder_summary": {"confounder_weight": "high"}}],
        },
        case_scope_quality={"missing_recommended_fields": ["comparator_actors", "org_context", "alleged_adverse_actions"]},
        analysis_limits={"downgrade_reasons": ["retaliation_focus_without_alleged_adverse_actions"]},
    )

    assert payload["summary"]["weakness_count"] >= 4
    categories = {item["category"] for item in payload["weaknesses"]}
    assert "chronology_problem" in categories
    assert "overstated_comparison" in categories
    assert "missing_documentation" in categories
    assert "unsupported_motive_claim" in categories
    assert "factual_leap" in categories
    comparison = next(item for item in payload["weaknesses"] if item["category"] == "overstated_comparison")
    assert "Role-matched comparator records" in comparison["repair_guidance"]["evidence_that_would_repair"]
    chronology = next(item for item in payload["weaknesses"] if item["category"] == "chronology_problem")
    assert chronology["supporting_chronology_ids"] == ["chron-1", "chron-2"]
    assert chronology["linked_date_gap_ids"] == ["GAP-001"]
    assert chronology["supporting_source_ids"] == ["email:uid-gap-1", "email:uid-gap-2"]
    ordinary = next(item for item in payload["weaknesses"] if item["category"] == "ordinary_management_explanation")
    assert "Confounder weight is currently high" in ordinary["critique"]
    first = payload["weaknesses"][0]
    assert first["repair_guidance"]["how_to_fix"]
    assert first["repair_guidance"]["evidence_that_would_repair"]
    assert first["repair_guidance"]["cautious_rewrite"]
