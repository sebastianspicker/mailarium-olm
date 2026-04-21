from __future__ import annotations

from src.investigation_report import build_investigation_report


def test_discrimination_concern_requires_more_than_generic_unequal_treatment() -> None:
    report = build_investigation_report(
        case_bundle={
            "scope": {
                "allegation_focus": ["discrimination"],
                "org_context": {
                    "vulnerability_contexts": [],
                },
            }
        },
        candidates=[],
        timeline={},
        power_context={"missing_org_context": False, "supplied_role_facts": []},
        case_patterns={},
        retaliation_analysis=None,
        comparative_treatment={
            "summary": {"discrimination_supporting_comparator_count": 0},
            "comparator_summaries": [
                {
                    "status": "comparator_available",
                    "comparison_quality": "high",
                    "comparison_quality_label": "high_quality_comparator",
                    "supports_discrimination_concern": False,
                }
            ],
        },
        communication_graph={},
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "cmp-1",
                    "finding_scope": "comparative_treatment",
                    "finding_label": "Unequal treatment",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-1",
                            "message_or_document_id": "uid-1",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "metadata",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "strong_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "medium",
                        }
                    },
                    "alternative_explanations": ["Comparator quality remains bounded to one sender context."],
                }
            ]
        },
        evidence_table={"rows": []},
    )

    overall = report["sections"]["overall_assessment"]
    assert overall["primary_assessment"] == "unequal_treatment_concern"
    assert overall["secondary_plausible_interpretations"] == ["targeted_hostility_concern"]
    assert any("Discrimination concern remains gated" in item for item in overall["downgrade_reasons"])


def test_discrimination_concern_requires_protected_context_and_strong_comparator_support() -> None:
    report = build_investigation_report(
        case_bundle={
            "scope": {
                "allegation_focus": ["discrimination"],
                "org_context": {
                    "vulnerability_contexts": [
                        {
                            "context_type": "disability",
                            "person": {"name": "Alex Example", "email": "alex@example.com"},
                        }
                    ],
                },
            }
        },
        candidates=[],
        timeline={},
        power_context={"missing_org_context": False, "supplied_role_facts": []},
        case_patterns={},
        retaliation_analysis=None,
        comparative_treatment={
            "summary": {"discrimination_supporting_comparator_count": 1},
            "comparator_summaries": [
                {
                    "status": "comparator_available",
                    "comparison_quality": "high",
                    "comparison_quality_label": "high_quality_comparator",
                    "supports_discrimination_concern": True,
                }
            ],
        },
        communication_graph={},
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "cmp-2",
                    "finding_scope": "comparative_treatment",
                    "finding_label": "Unequal treatment",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-2",
                            "message_or_document_id": "uid-2",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "metadata",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "strong_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "medium",
                        }
                    },
                    "alternative_explanations": [],
                }
            ]
        },
        evidence_table={"rows": []},
    )

    overall = report["sections"]["overall_assessment"]
    assert overall["primary_assessment"] == "discrimination_concern"
    assert overall["assessment_strength"] == "strong_indicator"
