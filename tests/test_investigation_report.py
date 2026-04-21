from __future__ import annotations

from src.investigation_report import build_investigation_report


def test_build_investigation_report_renders_supported_sections_with_evidence_links():
    report = build_investigation_report(
        case_bundle={
            "scope": {
                "trigger_events": [],
            }
        },
        candidates=[
            {
                "uid": "uid-1",
                "language_rhetoric": {
                    "authored_text": {
                        "signals": [
                            {
                                "signal_id": "implicit_accusation",
                            }
                        ]
                    }
                },
            }
        ],
        timeline={"events": [{"uid": "uid-1", "date": "2026-02-12T10:00:00"}]},
        power_context={"missing_org_context": True, "supplied_role_facts": []},
        case_patterns={
            "behavior_patterns": [
                {
                    "cluster_id": "behavior:escalation",
                    "key": "escalation",
                    "primary_recurrence": "repeated",
                    "message_uids": ["uid-1"],
                }
            ]
        },
        retaliation_analysis=None,
        comparative_treatment={"summary": {"no_suitable_comparator_count": 1}, "comparator_summaries": []},
        communication_graph={"graph_findings": []},
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "message:uid-1:authored:escalation:1",
                    "finding_scope": "message_behavior",
                    "finding_label": "Escalation",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-1",
                            "message_or_document_id": "uid-1",
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
                        "The pattern may reflect repeated process friction rather than targeted hostility."
                    ],
                }
            ]
        },
        evidence_table={
            "rows": [
                {
                    "finding_id": "message:uid-1:authored:escalation:1",
                    "finding_label": "Escalation",
                    "evidence_handle": "email:uid-1:1",
                    "message_or_document_id": "uid-1",
                }
            ]
        },
    )

    assert report is not None
    assert report["version"] == "1"
    assert report["section_order"][0] == "executive_summary"
    assert report["interpretation_policy"]["version"] == "1"
    executive = report["sections"]["executive_summary"]
    assert executive["status"] == "supported"
    assert executive["entries"][0]["supporting_finding_ids"] == ["message:uid-1:authored:escalation:1"]
    assert executive["entries"][0]["supporting_citation_ids"] == ["c-1"]
    assert executive["entries"][0]["claim_level"] == "observed_fact"
    assert "directly supports escalation" in executive["entries"][0]["statement"].lower()
    assert "targeted hostility" in report["sections"]["overall_assessment"]["entries"][1]["alternative_explanations"][0]
    missing = report["sections"]["missing_information"]
    assert missing["status"] == "supported"
    assert any(entry["entry_id"] == "missing:org_context" for entry in missing["entries"])


def test_build_investigation_report_marks_sections_insufficient_when_no_evidence():
    report = build_investigation_report(
        case_bundle={"scope": {"trigger_events": []}},
        candidates=[],
        timeline={},
        power_context={"missing_org_context": False, "supplied_role_facts": []},
        case_patterns={},
        retaliation_analysis=None,
        comparative_treatment={},
        communication_graph={},
        finding_evidence_index={"findings": []},
        evidence_table={"rows": []},
    )

    assert report is not None
    assert report["sections"]["executive_summary"]["status"] == "insufficient_evidence"
    assert report["sections"]["language_analysis"]["insufficiency_reason"]
    assert report["sections"]["overall_assessment"]["status"] == "insufficient_evidence"


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
    )

    executive_entry = report["sections"]["executive_summary"]["entries"][0]
    assert executive_entry["claim_level"] == "pattern_concern"
    assert "raises a concern pattern" in executive_entry["statement"].lower()
    assert "motive" not in executive_entry["statement"].lower()
    assert "legal conclusion" not in executive_entry["statement"].lower()
