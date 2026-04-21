from __future__ import annotations

from src.investigation_report import build_investigation_report


def test_build_investigation_report_uses_guarded_pattern_concern_wording_for_interpretive_findings():
    report = build_investigation_report(
        case_bundle={"scope": {"trigger_events": []}},
        candidates=[],
        timeline={},
        power_context={"missing_org_context": False, "supplied_role_facts": []},
        case_patterns={},
        retaliation_analysis=None,
        comparative_treatment={},
        communication_graph={},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-comparator",
                    "primary_email": "comparator@example.com",
                    "display_names": ["Comparator Person"],
                    "role_hints": ["colleague"],
                }
            ]
        },
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "pattern-1",
                    "finding_scope": "retaliation_analysis",
                    "finding_label": "Retaliatory sequence",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-2",
                            "message_or_document_id": "uid-2",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "metadata",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "weak_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "low",
                        }
                    },
                    "alternative_explanations": [
                        "Before/after changes may reflect independent operational developments rather than retaliation."
                    ],
                }
            ]
        },
        evidence_table={"rows": []},
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 1}},
            "chronology_anchors": [
                {
                    "source_id": "email:uid-3",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "date": "2026-02-16T10:00:00",
                    "title": "Comparator",
                    "reliability_level": "high",
                }
            ],
            "sources": [
                {
                    "source_id": "email:uid-2",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-2",
                    "title": "Follow-up",
                    "date": "2026-02-13T10:00:00",
                    "snippet": "For the record, you failed to provide the figures.",
                    "provenance": {"evidence_handle": "email:uid-2"},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                }
            ],
            "source_links": [],
        },
    )

    executive_entry = report["sections"]["executive_summary"]["entries"][1]
    assert executive_entry["claim_level"] == "pattern_concern"
    assert "raises a concern pattern" in executive_entry["statement"].lower()
    assert "motive" not in executive_entry["statement"].lower()
    assert "legal conclusion" not in executive_entry["statement"].lower()
    overall = report["sections"]["overall_assessment"]
    assert overall["primary_assessment"] == "insufficient_evidence"
    assert overall["assessment_strength"] == "weak_indicator"
    assert overall["secondary_plausible_interpretations"] == ["retaliation_concern", "poor_communication_or_process_noise"]
    assert "The strongest supported findings remain in the weak-indicator range." in overall["downgrade_reasons"]
    assert "insufficient evidence" in overall["entries"][0]["statement"].lower()
    triage = report["sections"]["evidence_triage"]
    assert triage["summary"]["direct_evidence_count"] == 0
    assert triage["summary"]["reasonable_inference_count"] == 1
    assert triage["summary"]["unresolved_point_count"] == 1
    assert "proves retaliatory sequence remains unresolved" in triage["unresolved_points"][0]["statement"].lower()


def test_build_investigation_report_surfaces_mixed_evidence_in_overall_assessment():
    report = build_investigation_report(
        case_bundle={"scope": {"trigger_events": []}},
        candidates=[],
        timeline={},
        power_context={"missing_org_context": False, "supplied_role_facts": []},
        case_patterns={},
        retaliation_analysis=None,
        comparative_treatment={},
        communication_graph={},
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "msg-1",
                    "finding_scope": "message_behavior",
                    "finding_label": "Escalation",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-10",
                            "message_or_document_id": "uid-10",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "authored",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "moderate_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "medium",
                        }
                    },
                    "alternative_explanations": [
                        "The escalation may reflect a live operational incident rather than targeted hostility."
                    ],
                },
                {
                    "finding_id": "graph-1",
                    "finding_scope": "communication_graph",
                    "finding_label": "Visibility asymmetry",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-11",
                            "message_or_document_id": "uid-11",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "metadata",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "moderate_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "low",
                        }
                    },
                    "alternative_explanations": ["Recipient visibility may reflect a limited need-to-know distribution."],
                },
            ]
        },
        evidence_table={"rows": []},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-comparator",
                    "primary_email": "comparator@example.com",
                    "display_names": ["Comparator Person"],
                    "role_hints": ["colleague"],
                }
            ]
        },
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 2}},
            "sources": [
                {
                    "source_id": "email:uid-10",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-10",
                    "title": "Escalation",
                    "date": "2026-02-14T10:00:00",
                    "snippet": "Escalation snippet",
                    "provenance": {"evidence_handle": "email:uid-10"},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                },
                {
                    "source_id": "email:uid-11",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-11",
                    "title": "Visibility",
                    "date": "2026-02-15T10:00:00",
                    "snippet": "Visibility snippet",
                    "provenance": {"evidence_handle": "email:uid-11"},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                },
            ],
            "source_links": [],
        },
    )

    overall = report["sections"]["overall_assessment"]
    assert overall["primary_assessment"] == "targeted_hostility_concern"
    assert "The current record contains mixed evidence and material alternative explanations." in overall["downgrade_reasons"]
    mixed_entry = next(entry for entry in overall["entries"] if entry["entry_id"] == "overall:mixed_evidence")
    assert "record remains mixed" in mixed_entry["statement"].lower()
    assert len(mixed_entry["alternative_explanations"]) == 2
