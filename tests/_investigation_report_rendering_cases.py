from __future__ import annotations

from src.investigation_report import build_investigation_report


def test_build_investigation_report_renders_supported_sections_with_evidence_links():
    report = build_investigation_report(
        case_bundle={
            "scope": {
                "trigger_events": [
                    {
                        "trigger_type": "complaint",
                        "date": "2026-02-11",
                    }
                ],
                "employment_issue_tracks": ["participation_duty_gap"],
                "context_notes": "SBV participation appears missing after the complaint.",
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
                "message_findings": {
                    "authored_text": {
                        "tone_summary": "Controlling and accusatory wording is visible in the authored text.",
                        "relevant_wording": [{"text": "for the record"}],
                        "omissions_or_process_signals": [{"signal": "institutional_pressure_framing"}],
                        "included_actors": ["alex@example.com", "hr@example.com"],
                        "excluded_actors": [],
                        "communication_classification": {
                            "primary_class": "controlling",
                            "applied_classes": ["controlling", "tense"],
                        },
                    }
                },
            }
        ],
        timeline={
            "event_count": 3,
            "date_range": {"first": "2026-02-10", "last": "2026-02-13"},
            "first_uid": "uid-0",
            "last_uid": "uid-2",
            "key_transition_uid": "uid-1",
            "sender_change_count": 1,
            "thread_change_count": 1,
            "recipient_set_change_count": 1,
            "events": [
                {
                    "uid": "uid-0",
                    "date": "2026-02-10T09:00:00",
                    "sender_name": "Morgan Manager",
                    "sender_email": "manager@example.com",
                    "conversation_id": "conv-1",
                    "thread_group_id": "conv-1",
                    "recipients_summary": {
                        "status": "available",
                        "visible_recipient_count": 1,
                        "visible_recipient_emails": ["alex@example.com"],
                    },
                },
                {
                    "uid": "uid-1",
                    "date": "2026-02-12T10:00:00",
                    "sender_name": "Morgan Manager",
                    "sender_email": "manager@example.com",
                    "conversation_id": "conv-1",
                    "thread_group_id": "conv-1",
                    "recipients_summary": {
                        "status": "available",
                        "visible_recipient_count": 2,
                        "visible_recipient_emails": ["alex@example.com", "hr@example.com"],
                    },
                },
                {
                    "uid": "uid-2",
                    "date": "2026-02-13T11:00:00",
                    "sender_name": "Casey Director",
                    "sender_email": "director@example.com",
                    "conversation_id": "conv-2",
                    "thread_group_id": "conv-2",
                    "recipients_summary": {
                        "status": "available",
                        "visible_recipient_count": 1,
                        "visible_recipient_emails": ["hr@example.com"],
                    },
                },
            ],
        },
        power_context={"missing_org_context": True, "supplied_role_facts": []},
        case_patterns={
            "behavior_patterns": [
                {
                    "cluster_id": "behavior:escalation",
                    "key": "escalation",
                    "primary_recurrence": "repeated",
                    "message_count": 2,
                    "message_uids": ["uid-0", "uid-1"],
                    "thread_group_ids": ["conv-1"],
                    "first_date": "2026-02-10T09:00:00",
                    "last_date": "2026-02-12T10:00:00",
                    "recurrence_flags": ["targeted"],
                }
            ],
            "corpus_behavioral_review": {
                "message_count_reviewed": 1,
                "communication_class_counts": {"controlling": 1},
                "recurring_phrases": [{"phrase": "for the record", "message_count": 1, "message_uids": ["uid-1"]}],
                "escalation_points": [{"uid": "uid-1", "strength": "moderate"}],
                "double_standards": [],
                "procedural_irregularities": [],
                "response_timing_shifts": [],
                "cc_behavior_changes": [],
                "coordination_windows": [],
            },
        },
        retaliation_analysis=None,
        comparative_treatment={"summary": {"no_suitable_comparator_count": 1}, "comparator_summaries": []},
        communication_graph={"graph_findings": []},
        actor_identity_graph={
            "actors": [
                {
                    "actor_id": "actor-target",
                    "primary_email": "alex@example.com",
                    "display_names": ["Alex Example"],
                    "role_hints": ["employee"],
                },
                {
                    "actor_id": "actor-manager",
                    "primary_email": "manager@example.com",
                    "display_names": ["Morgan Manager"],
                    "role_hints": ["manager"],
                    "role_context": {
                        "supplied_role_facts": [{"role": "manager"}],
                    },
                },
            ]
        },
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
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 1}},
            "chronology_anchors": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "date": "2026-02-12T10:00:00",
                    "title": "Status",
                    "reliability_level": "high",
                }
            ],
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "actor_id": "actor-manager",
                    "title": "Status",
                    "date": "2026-02-12T10:00:00",
                    "snippet": (
                        "Wir haben die SBV in diesem Schritt nicht beteiligt und "
                        "senden vorerst keine schriftliche Zusammenfassung."
                    ),
                    "provenance": {"evidence_handle": "email:uid-1"},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                },
                {
                    "source_id": "meeting:uid-1:meeting_data",
                    "source_type": "meeting_note",
                    "document_kind": "calendar_metadata",
                    "uid": "uid-1",
                    "actor_id": "actor-manager",
                    "title": "Gesprächsnotiz",
                    "date": "2026-02-11",
                    "snippet": "Wir werden die SBV beteiligen und eine schriftliche Zusammenfassung senden.",
                    "source_reliability": {"level": "high", "basis": "calendar_meeting_metadata"},
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": False},
                },
            ],
            "source_links": [],
        },
    )

    assert report is not None
    assert report["version"] == "1"
    assert report["bilingual_workflow"]["primary_source_language"] == "de"
    assert report["section_order"][0] == "executive_summary"
    assert report["section_order"][1] == "evidence_triage"
    assert report["interpretation_policy"]["version"] == "1"
    assert report["report_highlights"]["strongest_indicators"]
    assert report["report_highlights"]["strongest_counterarguments"]
    executive = report["sections"]["executive_summary"]
    assert executive["status"] == "supported"
    assert executive["entries"][0]["entry_id"] == "executive:factual_summary"
    assert executive["entries"][0]["claim_level"] == "observed_fact"
    assert "contains 1 analyzed message(s) and 1 finding(s)" in executive["entries"][0]["statement"].lower()
    assert executive["entries"][1]["supporting_finding_ids"] == ["message:uid-1:authored:escalation:1"]
    assert executive["entries"][1]["supporting_citation_ids"] == ["c-1"]
    assert executive["entries"][1]["claim_level"] == "observed_fact"
    assert "directly supports escalation" in executive["entries"][1]["statement"].lower()
    triage = report["sections"]["evidence_triage"]
    assert triage["status"] == "supported"
    assert triage["summary"]["direct_evidence_count"] == 1
    assert triage["summary"]["reasonable_inference_count"] == 0
    assert triage["summary"]["unresolved_point_count"] == 1
    assert triage["summary"]["missing_proof_count"] == 2
    assert triage["direct_evidence"][0]["supporting_citation_ids"] == ["c-1"]
    assert "proves escalation remains unresolved" in triage["unresolved_points"][0]["statement"].lower()
    assert any(
        item["statement"].startswith("Structured org or dependency context is missing") for item in triage["missing_proof"]
    )
    matter_index = report["sections"]["matter_evidence_index"]
    assert matter_index["status"] == "supported"
    assert matter_index["matter_evidence_index"]["row_count"] == 2
    assert matter_index["matter_evidence_index"]["rows"][0]["exhibit_id"] == "EXH-001"
    assert matter_index["matter_evidence_index"]["rows"][0]["supporting_citation_ids"] == ["c-1"]
    assert matter_index["matter_evidence_index"]["rows"][0]["exhibit_reliability"]["strength"] == "strong"
    assert matter_index["matter_evidence_index"]["rows"][0]["source_language"] == "de"
    assert matter_index["matter_evidence_index"]["rows"][0]["quoted_evidence"]["original_text"].startswith("Wir werden")
    assert report["sections"]["lawyer_issue_matrix"]["lawyer_issue_matrix"]["bilingual_rendering"]["output_language"] == "en"
    assert (
        report["sections"]["lawyer_briefing_memo"]["lawyer_briefing_memo"]["bilingual_rendering"]["preserve_original_quotations"]
        is True
    )
    assert (
        report["sections"]["controlled_factual_drafting"]["controlled_factual_drafting"]["bilingual_rendering"][
            "translation_mode"
        ]
        == "translation_aware"
    )
    assert report["sections"]["case_dashboard"]["case_dashboard"]["bilingual_rendering"]["output_language"] == "en"
    assert matter_index["matter_evidence_index"]["rows"][0]["source_conflict_status"] == "disputed"
    assert matter_index["matter_evidence_index"]["summary"]["exhibit_strength_counts"]["strong"] == 2
    assert matter_index["matter_evidence_index"]["summary"]["source_conflict_status_counts"]["disputed"] == 2
    assert matter_index["matter_evidence_index"]["top_15_exhibits"]
    assert matter_index["matter_evidence_index"]["top_10_missing_exhibits"][0]["issue_track"] == "participation_duty_gap"
    issue_frameworks = report["sections"]["employment_issue_frameworks"]
    assert issue_frameworks["status"] == "supported"
    lawyer_matrix = report["sections"]["lawyer_issue_matrix"]
    assert lawyer_matrix["status"] == "supported"
    assert lawyer_matrix["lawyer_issue_matrix"]["row_count"] >= 1
    assert lawyer_matrix["lawyer_issue_matrix"]["rows"][0]["not_legal_advice"] is True
    assert lawyer_matrix["lawyer_issue_matrix"]["rows"][0]["timing_warning_ids"]
    assert lawyer_matrix["lawyer_issue_matrix"]["rows"][0]["source_conflict_status"] in {
        "contains_unresolved_source_conflict",
        "possible_conflict_elsewhere_in_record",
    }
    actor_witness = report["sections"]["actor_and_witness_map"]
    assert actor_witness["status"] == "supported"
    assert actor_witness["actor_map"]["actor_count"] == 2
    assert actor_witness["actor_map"]["actors"][1]["status"]["decision_maker"] is True
    assert actor_witness["witness_map"]["primary_decision_makers"][0]["actor_id"] == "actor-manager"
    witness_packs = report["sections"]["witness_question_packs"]
    assert witness_packs["status"] == "supported"
    assert witness_packs["witness_question_packs"]["pack_count"] >= 1
    promise_analysis = report["sections"]["promise_and_contradiction_analysis"]
    assert promise_analysis["status"] == "supported"
    assert promise_analysis["promise_contradiction_analysis"]["summary"]["promise_action_row_count"] >= 1
    assert promise_analysis["promise_contradiction_analysis"]["summary"]["contradiction_row_count"] >= 1
    memo = report["sections"]["lawyer_briefing_memo"]
    assert memo["status"] == "supported"
    assert memo["lawyer_briefing_memo"]["memo_format"] == "lawyer_onboarding_brief"
    assert memo["lawyer_briefing_memo"]["sections"]["executive_summary"]
    drafting = report["sections"]["controlled_factual_drafting"]
    assert drafting["status"] == "supported"
    assert drafting["controlled_factual_drafting"]["drafting_format"] == "controlled_factual_drafting"
    assert drafting["controlled_factual_drafting"]["controlled_draft"]["sections"]["established_facts"]
    dashboard = report["sections"]["case_dashboard"]
    assert dashboard["status"] == "supported"
    assert dashboard["case_dashboard"]["dashboard_format"] == "refreshable_case_dashboard"
    assert report["deadline_warnings"]["summary"]["warning_count"] >= 1
    assert dashboard["case_dashboard"]["cards"]["timing_warnings"]
    assert dashboard["case_dashboard"]["cards"]["main_actors"]
    consistency = report["sections"]["cross_output_consistency"]
    assert consistency["status"] == "supported"
    assert consistency["cross_output_consistency"]["summary"]["check_count"] >= 1
    assert consistency["cross_output_consistency"]["overall_status"] in {"consistent", "review_required"}
    skeptical_review = report["sections"]["skeptical_employer_review"]
    assert skeptical_review["status"] == "supported"
    assert skeptical_review["skeptical_employer_review"]["summary"]["weakness_count"] >= 1
    first_weakness = skeptical_review["skeptical_employer_review"]["weaknesses"][0]
    assert first_weakness["repair_guidance"]["how_to_fix"]
    assert first_weakness["repair_guidance"]["cautious_rewrite"]
    checklist = report["sections"]["document_request_checklist"]
    assert checklist["status"] == "supported"
    assert checklist["document_request_checklist"]["group_count"] >= 1
    assert checklist["document_request_checklist"]["deadline_warnings"]["summary"]["warning_count"] >= 1
    first_group = checklist["document_request_checklist"]["groups"][0]
    assert any(group["timing_warning_ids"] for group in checklist["document_request_checklist"]["groups"])
    assert first_group["items"][0]["likely_custodian"]
    assert first_group["items"][0]["risk_of_loss"]
    chronology = report["sections"]["chronological_pattern_analysis"]
    assert chronology["status"] == "supported"
    assert chronology["master_chronology"]["entry_count"] == 4
    assert chronology["master_chronology"]["summary"]["date_precision_counts"]["day"] == 1
    assert chronology["master_chronology"]["summary"]["date_precision_counts"]["second"] == 3
    assert chronology["master_chronology"]["summary"]["date_gap_count"] >= 0
    assert "date_gaps_and_unexplained_sequences" in chronology["master_chronology"]["summary"]
    assert chronology["master_chronology"]["summary"]["source_conflict_registry"]["conflict_count"] >= 1
    assert chronology["master_chronology"]["primary_entry_count"] == 3
    assert chronology["master_chronology"]["scope_supplied_entry_count"] == 1
    assert "views" in chronology["master_chronology"]
    assert chronology["master_chronology"]["views"]["short_neutral_chronology"]["entry_count"] == 3
    assert chronology["master_chronology"]["views"]["balanced_timeline_assessment"]["summary"]["strongest_limits"]
    first_chronology_entry = chronology["master_chronology"]["entries"][0]
    assert "event_support_matrix" in first_chronology_entry
    assert "ordinary_managerial_explanation" in first_chronology_entry["event_support_matrix"]
    chronology_statements = [entry["statement"] for entry in chronology["entries"]]
    assert any("before and 2 event(s) after" in statement for statement in chronology_statements)
    assert any(
        "sender change(s), 1 thread change(s), and 1 visible recipient-set change(s)" in statement
        for statement in chronology_statements
    )
    assert any("reads as repeated from 2026-02-10 to 2026-02-12" in statement for statement in chronology_statements)
    language = report["sections"]["language_analysis"]
    assert language["message_behavioral_review"]["message_count"] == 1
    sampled_review = language["message_behavioral_review"]["sampled_messages"][0]
    assert sampled_review["communication_classification"]["primary_class"] == "controlling"
    assert language["retrieval_slice_behavioral_review"]["recurring_phrases"][0]["phrase"] == "for the record"
    assert language["retrieval_slice_behavioral_review"]["coverage_scope"] == "retrieved_candidate_slice"
    overall = report["sections"]["overall_assessment"]
    assert overall["primary_assessment"] == "targeted_hostility_concern"
    assert overall["assessment_strength"] == "moderate_indicator"
    assert overall["secondary_plausible_interpretations"] == ["ordinary_workplace_conflict"]
    assert overall["downgrade_reasons"] == []
    assert "targeted hostility concern" in overall["entries"][0]["statement"].lower()
    assert "targeted hostility" in overall["entries"][-1]["alternative_explanations"][0]
    assert report["report_highlights"]["strongest_indicators"][0]["finding_id"] == "message:uid-1:authored:escalation:1"
    assert "targeted hostility" in report["report_highlights"]["strongest_counterarguments"][0]["text"]
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
    assert report["report_highlights"]["strongest_indicators"] == []
    assert report["report_highlights"]["strongest_counterarguments"] == []
    assert report["sections"]["executive_summary"]["status"] == "insufficient_evidence"
    assert report["sections"]["matter_evidence_index"]["status"] == "insufficient_evidence"
    triage = report["sections"]["evidence_triage"]
    assert triage["status"] == "supported"
    assert triage["summary"]["direct_evidence_count"] == 0
    assert triage["summary"]["reasonable_inference_count"] == 0
    assert triage["summary"]["unresolved_point_count"] == 0
    assert triage["summary"]["missing_proof_count"] == 1
    assert report["sections"]["language_analysis"]["insufficiency_reason"]
    assert report["sections"]["lawyer_issue_matrix"]["status"] == "insufficient_evidence"
    assert report["sections"]["actor_and_witness_map"]["status"] == "insufficient_evidence"
    assert report["sections"]["promise_and_contradiction_analysis"]["status"] == "insufficient_evidence"
    assert report["sections"]["lawyer_briefing_memo"]["status"] == "insufficient_evidence"
    assert report["sections"]["controlled_factual_drafting"]["status"] == "insufficient_evidence"
    assert report["sections"]["case_dashboard"]["status"] == "insufficient_evidence"
    assert report["sections"]["skeptical_employer_review"]["status"] == "insufficient_evidence"
    assert report["sections"]["document_request_checklist"]["status"] == "insufficient_evidence"
    overall = report["sections"]["overall_assessment"]
    assert overall["status"] == "insufficient_evidence"
    assert overall["primary_assessment"] == "insufficient_evidence"
    assert overall["secondary_plausible_interpretations"] == []
    assert overall["assessment_strength"] == "insufficient_evidence"
    assert overall["downgrade_reasons"] == []
