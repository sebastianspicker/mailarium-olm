from __future__ import annotations

from src.controlled_factual_drafting import build_controlled_factual_drafting


def test_build_controlled_factual_drafting_applies_preflight_and_allegation_ceiling() -> None:
    payload = build_controlled_factual_drafting(
        case_bundle={
            "scope": {
                "target_person": {"name": "Alex Example", "email": "alex@example.com"},
                "analysis_goal": "lawyer_briefing",
            }
        },
        findings=[
            {
                "finding_id": "finding-1",
                "finding_label": "Retaliation concern",
                "finding_scope": "retaliation_analysis",
                "evidence_strength": {"label": "moderate_indicator"},
                "confidence_split": {"interpretation_confidence": {"label": "medium"}},
                "supporting_evidence": [
                    {
                        "citation_id": "citation-1",
                        "message_or_document_id": "uid-1",
                        "text_attribution": {"authored_quoted_inferred_status": "authored"},
                    }
                ],
                "alternative_explanations": ["Operational urgency remains possible."],
            }
        ],
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "short_description": "Email excludes the target from the follow-up process.",
                    "why_it_matters": "Shows a documented exclusion step.",
                }
            ]
        },
        master_chronology={
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2026-02-03",
                    "title": "Complaint lodged",
                    "source_linkage": {"source_ids": ["email:uid-1"]},
                },
                {
                    "chronology_id": "CHR-002",
                    "date": "2024-01-01",
                    "title": "case_prompt.md",
                    "source_linkage": {"source_ids": [], "source_evidence_status": "scope_only"},
                },
            ]
        },
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "retaliation_massregelungsverbot",
                    "title": "Retaliation / Maßregelungsverbot",
                    "legal_relevance_status": "supported_relevance",
                }
            ]
        },
        comparative_treatment={
            "comparator_points": [
                {
                    "comparator_point_id": "cmp:1",
                    "issue_id": "control_intensity",
                    "issue_label": "Control intensity",
                    "comparison_strength": "moderate",
                    "point_summary": "Control intensity: claimant-facing messages were harsher. Strength: moderate.",
                    "counterargument": "Comparator support remains bounded by the present role match.",
                }
            ]
        },
        retaliation_timeline_assessment={
            "temporal_correlation_analysis": [
                {
                    "timeline_id": "temporal_correlation:1",
                    "trigger_type": "complaint",
                    "trigger_date": "2026-02-03",
                    "assessment_status": "mixed_shift",
                    "analysis_quality": "medium",
                    "confounder_signals": ["new_sender_appears_after_trigger"],
                    "supporting_uids": ["uid-1"],
                }
            ],
            "overall_evidentiary_rating": {"reason": "Timing support remains mixed."},
        },
        skeptical_employer_review={
            "weaknesses": [
                {
                    "weakness_id": "weakness:unsupported_motive_claim",
                    "category": "unsupported_motive_claim",
                    "critique": "Motive remains inferential.",
                    "repair_guidance": {"how_to_fix": "Add tighter chronology support."},
                }
            ]
        },
        document_request_checklist={
            "group_count": 1,
            "groups": [
                {
                    "group_id": "calendar_meeting_records",
                    "title": "Calendar Invites / Meeting Notes",
                    "items": [{"request": "Provide the meeting records for the exclusion discussion."}],
                }
            ],
        },
        promise_contradiction_analysis={
            "contradiction_table": [
                {
                    "original_statement_or_promise": "SBV would be included.",
                    "later_action": "SBV was not included.",
                    "original_source_id": "meeting:uid-1:meeting_data",
                    "later_source_id": "email:uid-1",
                }
            ]
        },
    )

    assert payload is not None
    assert payload["drafting_format"] == "controlled_factual_drafting"
    assert payload["framing_preflight"]["objective_of_draft"]
    assert payload["framing_preflight"]["allegation_ceiling"]["ceiling_level"] == "concern_only"
    assert payload["framing_preflight"]["legal_and_factual_risks"][0]["risk_type"] == "unsupported_motive_claim"
    assert any(
        "Comparator evidence may support unequal-treatment review" in row["text"]
        for row in payload["framing_preflight"]["strongest_framing"]
    )
    assert any(
        "Retaliation timing may support further review" in row["text"]
        for row in payload["framing_preflight"]["strongest_framing"]
    )
    assert payload["controlled_draft"]["sections"]["established_facts"]
    assert payload["controlled_draft"]["sections"]["concerns"]
    assert payload["controlled_draft"]["sections"]["requests_for_clarification"]
    assert payload["controlled_draft"]["sections"]["formal_demands"]
    assert "Established Facts:" in payload["controlled_draft"]["rendered_text"]
    assert all("case_prompt" not in row["text"].lower() for row in payload["controlled_draft"]["sections"]["established_facts"])


def test_build_controlled_factual_drafting_keeps_documentary_anchors_on_concerns() -> None:
    payload = build_controlled_factual_drafting(
        case_bundle={
            "scope": {
                "target_person": {"name": "Alex Example", "email": "alex@example.com"},
                "analysis_goal": "lawyer_briefing",
            }
        },
        findings=[
            {
                "finding_id": "finding-1",
                "finding_label": "Retaliation concern",
                "finding_scope": "retaliation_analysis",
                "evidence_strength": {"label": "moderate_indicator"},
                "confidence_split": {"interpretation_confidence": {"label": "medium"}},
                "supporting_evidence": [
                    {
                        "citation_id": "citation-1",
                        "message_or_document_id": "uid-1",
                        "text_attribution": {"authored_quoted_inferred_status": "authored"},
                    }
                ],
                "alternative_explanations": ["Operational urgency remains possible."],
            }
        ],
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "supporting_uids": ["uid-1"],
                    "short_description": "Email excludes the target from the follow-up process.",
                    "why_it_matters": "Shows a documented exclusion step.",
                }
            ]
        },
        master_chronology={
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "uid": "uid-1",
                    "date": "2026-02-03",
                    "title": "Complaint lodged",
                    "source_linkage": {"source_ids": ["email:uid-1"]},
                }
            ]
        },
        lawyer_issue_matrix={"rows": []},
        comparative_treatment={
            "comparator_points": [
                {
                    "comparator_point_id": "cmp:1",
                    "issue_id": "control_intensity",
                    "issue_label": "Control intensity",
                    "comparison_strength": "moderate",
                    "point_summary": "Control intensity: claimant-facing messages were harsher. Strength: moderate.",
                    "counterargument": "Comparator support remains bounded by the present role match.",
                    "supporting_source_ids": ["email:uid-1"],
                    "evidence_uids": ["uid-1"],
                }
            ]
        },
        retaliation_timeline_assessment={
            "retaliation_points": [
                {
                    "retaliation_point_id": "ret:1",
                    "support_strength": "moderate",
                    "point_summary": "Project withdrawal appears shortly after the complaint.",
                    "counterargument": "Project staffing needs remain a plausible neutral explanation.",
                    "supporting_uids": ["uid-1"],
                    "supporting_source_ids": ["email:uid-1"],
                }
            ]
        },
        skeptical_employer_review={"weaknesses": []},
        document_request_checklist={"group_count": 0, "groups": []},
        promise_contradiction_analysis={"contradiction_table": []},
    )

    assert payload is not None
    concerns = payload["controlled_draft"]["sections"]["concerns"]
    assert concerns
    assert all(row["supporting_source_ids"] == ["email:uid-1"] for row in concerns)
    assert all(row["supporting_exhibit_ids"] == ["EXH-001"] for row in concerns)
