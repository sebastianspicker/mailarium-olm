from __future__ import annotations

from src.investigation_report import build_investigation_report


def test_build_investigation_report_renders_employment_issue_frameworks_conservatively() -> None:
    report = build_investigation_report(
        case_bundle={
            "scope": {
                "allegation_focus": ["retaliation", "discrimination"],
                "context_notes": "SBV consultation appears absent after the complaint and the BEM process was not followed.",
                "employment_issue_tags": ["sbv_participation"],
                "trigger_events": [{"trigger_type": "complaint", "date": "2026-02-03"}],
                "employment_issue_tracks": [
                    "disability_disadvantage",
                    "retaliation_after_protected_event",
                    "participation_duty_gap",
                    "prevention_duty_gap",
                ],
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
                    "comparator_matrix": {
                        "row_count": 1,
                        "rows": [
                            {
                                "matrix_row_id": "comparator:cmp-1:control_intensity",
                                "issue_id": "control_intensity",
                                "issue_label": "Control intensity",
                                "claimant_treatment": "Higher control cues against the claimant are visible.",
                                "comparator_treatment": "Lower control cues are visible for the comparator.",
                                "evidence": ["uid-2", "uid-3"],
                                "comparison_strength": "strong",
                                "evidence_needed_to_strengthen_point": ["Comparable policy context"],
                                "likely_significance": "May support unequal-treatment review if role similarity holds.",
                            }
                        ],
                    },
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
                },
                {
                    "finding_id": "ret-1",
                    "finding_scope": "retaliation_analysis",
                    "finding_label": "Retaliatory sequence",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-3",
                            "message_or_document_id": "uid-3",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "metadata",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "moderate_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "medium",
                        }
                    },
                    "alternative_explanations": [],
                },
            ]
        },
        evidence_table={"rows": []},
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"formal_document": 1}},
            "sources": [
                {
                    "source_id": "formal_document:uid-3:sbv-bem-note.pdf",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "uid": "uid-3",
                    "title": "SBV BEM Note",
                    "date": "2026-02-16T10:00:00",
                    "snippet": "SBV consultation and BEM prevention concerns are documented here.",
                    "documentary_support": {"text_preview": "SBV consultation and BEM prevention concerns are documented here."},
                    "provenance": {"evidence_handle": "attachment:uid-3:sbv-bem-note.pdf"},
                    "source_reliability": {"level": "high", "basis": "formal_document_text_extracted"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                }
            ],
            "source_links": [],
        },
    )

    issue_frameworks = report["sections"]["employment_issue_frameworks"]
    assert issue_frameworks["status"] == "supported"
    payloads = {item["issue_track"]: item for item in issue_frameworks["issue_tracks"]}
    assert payloads["disability_disadvantage"]["status"] == "supported_by_current_record"
    assert payloads["retaliation_after_protected_event"]["status"] == "supported_by_current_record"
    assert payloads["participation_duty_gap"]["status"] == "supported_by_current_record"
    assert payloads["prevention_duty_gap"]["status"] == "supported_by_current_record"
    assert payloads["prevention_duty_gap"]["minimum_source_quality_expectations"]
    assert payloads["disability_disadvantage"]["required_proof_elements"]
    assert issue_frameworks["issue_tag_summary"]["operator_supplied"][0]["tag_id"] == "sbv_participation"
    direct_tags = [item["tag_id"] for item in issue_frameworks["issue_tag_summary"]["direct_document_content"]]
    inferred_tags = [item["tag_id"] for item in issue_frameworks["issue_tag_summary"]["bounded_inference"]]
    assert "prevention_bem_sgb_ix_167" in direct_tags
    assert "retaliation_massregelung" in inferred_tags
    power = report["sections"]["power_context_analysis"]
    assert power["comparator_matrix"]["row_count"] == 1
    assert power["comparator_matrix"]["rows"][0]["issue_id"] == "control_intensity"
    lawyer_matrix = report["sections"]["lawyer_issue_matrix"]["lawyer_issue_matrix"]
    row_ids = [row["issue_id"] for row in lawyer_matrix["rows"]]
    assert "agg_disadvantage" in row_ids
    assert "sgb_ix_167_bem" in row_ids
    agg_row = next(row for row in lawyer_matrix["rows"] if row["issue_id"] == "agg_disadvantage")
    assert agg_row["legal_relevance_status"] in {"supported_relevance", "potentially_relevant"}
    assert agg_row["strongest_documents"]
    assert agg_row["likely_opposing_argument"]


def test_build_investigation_report_embeds_retaliation_timeline_assessment() -> None:
    report = build_investigation_report(
        case_bundle={
            "scope": {
                "trigger_events": [
                    {
                        "trigger_type": "complaint",
                        "date": "2026-02-03",
                    }
                ]
            }
        },
        candidates=[],
        timeline={"events": [], "event_count": 0},
        power_context={"missing_org_context": False, "supplied_role_facts": []},
        case_patterns={},
        retaliation_analysis={
            "version": "1",
            "trigger_event_count": 1,
            "trigger_events": [],
            "protected_activity_candidates": [{"candidate_id": "protected_activity:1", "candidate_type": "complaint"}],
            "adverse_action_candidates": [{"candidate_id": "adverse_action:1", "action_type": "project_removal"}],
            "retaliation_timeline_assessment": {
                "version": "1",
                "protected_activity_timeline": [
                    {
                        "timeline_id": "protected_activity:1",
                        "trigger_type": "complaint",
                        "date": "2026-02-03",
                        "actor": {"name": "Alex Example", "email": "alex@example.com"},
                        "notes": "",
                    }
                ],
                "adverse_action_timeline": [
                    {
                        "uid": "uid-5",
                        "date": "2026-02-05T10:00:00",
                        "days_from_trigger": 2,
                        "subject": "After complaint",
                        "sender_actor_id": "actor-manager",
                        "adverse_signals": ["escalation"],
                    }
                ],
                "temporal_correlation_analysis": [
                    {
                        "timeline_id": "temporal_correlation:1",
                        "trigger_type": "complaint",
                        "trigger_date": "2026-02-03",
                        "assessment_status": "adverse_shift_after_trigger",
                        "analysis_quality": "medium",
                        "before_message_count": 1,
                        "after_message_count": 1,
                        "immediate_after_count": 1,
                        "strongest_metric_changes": [
                            {
                                "metric": "escalation_rate",
                                "direction": "higher_after_trigger",
                                "magnitude": 1.0,
                                "reason": "Normalized escalation rate increased after the trigger event.",
                            }
                        ],
                        "confounder_signals": [],
                        "confounder_summary": {"confounder_count": 0, "confounder_weight": "low"},
                        "supporting_uids": ["uid-4", "uid-5"],
                    }
                ],
                "strongest_retaliation_indicators": [
                    {
                        "indicator": "Normalized escalation rate increased after the trigger event.",
                        "trigger_date": "2026-02-03",
                        "assessment_status": "adverse_shift_after_trigger",
                        "supporting_uids": ["uid-5"],
                    }
                ],
                "strongest_non_retaliatory_explanations": [],
                "overall_evidentiary_rating": {
                    "rating": "limited_or_mixed_timing_support",
                    "reason": "Some trigger-linked timing indicators are present, but context remains limited.",
                },
            },
        },
        comparative_treatment={},
        communication_graph={},
        finding_evidence_index={"findings": []},
        evidence_table={"rows": []},
        multi_source_case_bundle={"summary": {"source_type_counts": {}}},
    )

    chronology = report["sections"]["chronological_pattern_analysis"]
    protected_candidates = chronology["retaliation_timeline_assessment"]["protected_activity_candidates"]
    adverse_candidates = chronology["retaliation_timeline_assessment"]["adverse_action_candidates"]
    assert protected_candidates[0]["candidate_id"] == "protected_activity:1"
    assert adverse_candidates[0]["candidate_id"] == "adverse_action:1"
    assert chronology["retaliation_timeline_assessment"]["protected_activity_timeline"][0]["trigger_type"] == "complaint"
    assert chronology["retaliation_timeline_assessment"]["adverse_action_timeline"][0]["uid"] == "uid-5"
    assert chronology["retaliation_timeline_assessment"]["confounder_summary"]["confounder_weight"] == "low"
    assert chronology["retaliation_timeline_assessment"]["overall_evidentiary_rating"]["rating"] == (
        "limited_or_mixed_timing_support"
    )
    assert any(entry["entry_id"] == "timeline:retaliation_assessment" for entry in chronology["entries"])


def test_compact_investigation_report_preserves_overall_assessment_contract_fields():
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
                    "finding_id": "cmp-1",
                    "finding_scope": "comparative_treatment",
                    "finding_label": "Unequal treatment",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-3",
                            "message_or_document_id": "uid-3",
                            "text_attribution": {
                                "authored_quoted_inferred_status": "metadata",
                            },
                        }
                    ],
                    "evidence_strength": {"label": "moderate_indicator"},
                    "confidence_split": {
                        "interpretation_confidence": {
                            "label": "medium",
                        }
                    },
                    "alternative_explanations": ["Comparator quality remains partial."],
                    "quote_ambiguity": {
                        "downgraded_due_to_quote_ambiguity": True,
                    },
                }
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
                    "source_id": "email:uid-3",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-3",
                    "title": "Comparator",
                    "date": "2026-02-16T10:00:00",
                    "snippet": "Comparator snippet",
                    "provenance": {"evidence_handle": "email:uid-3"},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                }
            ],
            "source_links": [],
        },
    )

    from src.investigation_report import compact_investigation_report

    compact = compact_investigation_report(report)
    triage = compact["sections"]["evidence_triage"]
    matter_index = compact["sections"]["matter_evidence_index"]
    lawyer_matrix = compact["sections"]["lawyer_issue_matrix"]
    actor_witness = compact["sections"]["actor_and_witness_map"]
    witness_packs = compact["sections"]["witness_question_packs"]
    promise_analysis = compact["sections"]["promise_and_contradiction_analysis"]
    memo = compact["sections"]["lawyer_briefing_memo"]
    drafting = compact["sections"]["controlled_factual_drafting"]
    dashboard = compact["sections"]["case_dashboard"]
    skeptical_review = compact["sections"]["skeptical_employer_review"]
    checklist = compact["sections"]["document_request_checklist"]
    overall = compact["sections"]["overall_assessment"]
    assert compact["report_highlights"] == report["report_highlights"]
    assert compact["bilingual_workflow"]["output_language"] == "en"
    assert triage["summary"]["reasonable_inference_count"] == 1
    assert len(triage["reasonable_inference"]) == 1
    assert len(triage["missing_proof"]) == 1
    assert matter_index["matter_evidence_index"]["row_count"] == 1
    assert matter_index["matter_evidence_index"]["rows"][0]["exhibit_reliability"]["strength"] == "strong"
    assert lawyer_matrix["lawyer_issue_matrix"]["row_count"] == 0
    assert lawyer_matrix["lawyer_issue_matrix"]["bilingual_rendering"]["output_language"] == "en"
    assert lawyer_matrix["lawyer_issue_matrix"]["rows"] == []
    assert actor_witness["actor_map"]["actor_count"] == 1
    assert actor_witness["witness_map"]["primary_decision_makers"] == []
    assert witness_packs["witness_question_packs"]["pack_count"] >= 0
    assert promise_analysis["promise_contradiction_analysis"]["summary"]["promise_action_row_count"] == 0
    assert promise_analysis["promise_contradiction_analysis"]["summary"]["contradiction_row_count"] == 0
    assert memo["lawyer_briefing_memo"]["memo_format"] == "lawyer_onboarding_brief"
    assert memo["lawyer_briefing_memo"]["bilingual_rendering"]["preserve_original_quotations"] is True
    assert memo["lawyer_briefing_memo"]["sections"]["executive_summary"]
    assert drafting["controlled_factual_drafting"]["drafting_format"] == "controlled_factual_drafting"
    assert drafting["controlled_factual_drafting"]["bilingual_rendering"]["translation_mode"] == "translation_aware"
    assert drafting["controlled_factual_drafting"]["framing_preflight"]["allegation_ceiling"]["ceiling_level"]
    assert dashboard["case_dashboard"]["dashboard_format"] == "refreshable_case_dashboard"
    assert dashboard["case_dashboard"]["bilingual_rendering"]["output_language"] == "en"
    assert dashboard["case_dashboard"]["summary"]["refreshable_from_shared_entities"] is True
    assert dashboard["case_dashboard"]["cards"]["main_actors"]
    assert skeptical_review["skeptical_employer_review"]["summary"]["weakness_count"] >= 1
    assert checklist["document_request_checklist"]["group_count"] >= 1
    assert compact["sections"]["chronological_pattern_analysis"]["master_chronology"]["entry_count"] == 1
    assert compact["sections"]["chronological_pattern_analysis"]["retaliation_timeline_assessment"]["version"] == ""
    assert overall["primary_assessment"] == "unequal_treatment_concern"
    assert overall["assessment_strength"] == "moderate_indicator"
    assert overall["secondary_plausible_interpretations"] == ["targeted_hostility_concern"]
    assert "Quoted-speaker ambiguity downgrades part of the current record." in overall["downgrade_reasons"]
