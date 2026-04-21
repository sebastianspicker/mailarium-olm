from __future__ import annotations

from src.cross_output_consistency import build_cross_output_consistency


def test_build_cross_output_consistency_flags_mismatches() -> None:
    payload = build_cross_output_consistency(
        master_chronology={
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "event_support_matrix": {
                        "retaliation_after_protected_event": {
                            "selected_in_case_scope": True,
                            "status": "direct_event_support",
                        }
                    },
                }
            ]
        },
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EX-001",
                    "exhibit_reliability": {"strength": "strong"},
                }
            ],
            "top_15_exhibits": [
                {
                    "exhibit_id": "EX-001",
                    "exhibit_reliability": {"strength": "strong"},
                }
            ],
        },
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "agg_disadvantage",
                    "legal_relevance_status": "supported_relevance",
                }
            ]
        },
        lawyer_briefing_memo={
            "sections": {
                "timeline": [{"supporting_chronology_ids": ["CHR-999"]}],
                "core_theories": [{"supporting_issue_ids": ["missing-issue"]}],
                "strongest_evidence": [{"supporting_exhibit_ids": ["EX-404"]}],
                "weaknesses_or_risks": [],
            }
        },
        case_dashboard={
            "cards": {
                "key_dates": [{"chronology_id": "CHR-001"}],
                "main_claims_or_issues": [{"issue_id": "agg_disadvantage", "title": "AGG", "status": "supported"}],
                "strongest_exhibits": [{"exhibit_id": "EX-001", "strength": "weak"}],
                "main_actors": [{"actor_id": "actor-1", "status": {"decision_maker": False}}],
                "risks_or_weak_spots": [],
            }
        },
        skeptical_employer_review={"weaknesses": [{"weakness_id": "weak-1"}]},
        controlled_factual_drafting={
            "framing_preflight": {"allegation_ceiling": {"ceiling_level": "observed_facts_only"}},
            "controlled_draft": {
                "allegation_ceiling_applied": "concern_only",
                "sections": {
                    "established_facts": [{"supporting_chronology_ids": ["CHR-001"]}],
                    "concerns": [{"item_id": "draft:concern:1"}],
                },
            },
        },
        retaliation_timeline_assessment={
            "temporal_correlation_analysis": [
                {
                    "timeline_id": "temporal_correlation:1",
                    "assessment_status": "mixed_shift",
                    "analysis_quality": "medium",
                    "confounder_signals": ["new_sender_appears_after_trigger"],
                }
            ]
        },
        actor_map={
            "actors": [{"actor_id": "actor-1", "status": {"decision_maker": True}}],
        },
    )

    assert payload is not None
    assert payload["overall_status"] == "review_required"
    assert payload["summary"]["mismatch_count"] >= 5
    check_ids = {check["check_id"] for check in payload["checks"]}
    assert "chronology_references" in check_ids
    assert "chronology_issue_matrix_alignment" in check_ids
    assert "draft_preflight_alignment" in check_ids
    assert "retaliation_support_alignment" in check_ids


def test_build_cross_output_consistency_passes_for_aligned_outputs() -> None:
    payload = build_cross_output_consistency(
        master_chronology={
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "event_support_matrix": {
                        "retaliation_after_protected_event": {
                            "selected_in_case_scope": True,
                            "status": "direct_event_support",
                        }
                    },
                }
            ]
        },
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EX-001",
                    "exhibit_reliability": {"strength": "strong"},
                }
            ],
            "top_15_exhibits": [
                {
                    "exhibit_id": "EX-001",
                    "exhibit_reliability": {"strength": "strong"},
                }
            ],
        },
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "retaliation_massregelungsverbot",
                    "legal_relevance_status": "supported_relevance",
                }
            ]
        },
        lawyer_briefing_memo={
            "sections": {
                "timeline": [{"supporting_chronology_ids": ["CHR-001"]}],
                "core_theories": [{"supporting_issue_ids": ["retaliation_massregelungsverbot"]}],
                "strongest_evidence": [{"supporting_exhibit_ids": ["EX-001"]}],
                "weaknesses_or_risks": [{"entry_id": "memo:risk:1"}],
            }
        },
        case_dashboard={
            "cards": {
                "key_dates": [{"chronology_id": "CHR-001"}],
                "main_claims_or_issues": [
                    {
                        "issue_id": "retaliation_massregelungsverbot",
                        "title": "Retaliation",
                        "status": "supported_relevance",
                    }
                ],
                "strongest_exhibits": [{"exhibit_id": "EX-001", "strength": "strong"}],
                "main_actors": [{"actor_id": "actor-1", "status": {"decision_maker": True}}],
                "risks_or_weak_spots": [{"weakness_id": "weak-1"}],
            }
        },
        skeptical_employer_review={"weaknesses": [{"weakness_id": "weak-1"}]},
        controlled_factual_drafting={
            "framing_preflight": {"allegation_ceiling": {"ceiling_level": "concern_only"}},
            "controlled_draft": {
                "allegation_ceiling_applied": "concern_only",
                "sections": {
                    "established_facts": [{"supporting_chronology_ids": ["CHR-001"]}],
                    "concerns": [{"supporting_issue_ids": ["retaliation_massregelungsverbot"]}],
                    "formal_demands": [{"supporting_exhibit_ids": ["EX-001"]}],
                },
            },
        },
        retaliation_timeline_assessment={
            "temporal_correlation_analysis": [
                {
                    "timeline_id": "temporal_correlation:1",
                    "assessment_status": "mixed_shift",
                    "analysis_quality": "medium",
                    "confounder_signals": ["new_sender_appears_after_trigger"],
                }
            ]
        },
        actor_map={
            "actors": [{"actor_id": "actor-1", "status": {"decision_maker": True}}],
        },
    )

    assert payload is not None
    assert payload["overall_status"] == "consistent"
    assert payload["summary"]["mismatch_count"] == 0
