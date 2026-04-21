from __future__ import annotations

from src.lawyer_issue_matrix import build_lawyer_issue_matrix


def test_lawyer_issue_matrix_prefers_explicit_linked_evidence_over_keyword_only_hits() -> None:
    payload = build_lawyer_issue_matrix(
        case_bundle={
            "scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
                "employment_issue_tracks": ["retaliation_after_protected_event"],
            }
        },
        findings=[],
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-keyword",
                    "short_description": "Complaint escalation note",
                    "why_it_matters": "Keyword-heavy but not explicitly linked.",
                    "main_issue_tags": [],
                    "supporting_finding_ids": [],
                    "supporting_citation_ids": [],
                    "supporting_uids": [],
                    "source_language": "en",
                    "quoted_evidence": {"original_text": "Complaint retaliation objection."},
                    "source_conflict_status": "stable",
                    "linked_source_conflicts": [],
                },
                {
                    "exhibit_id": "EXH-002",
                    "source_id": "email:uid-linked",
                    "short_description": "Project withdrawal after complaint",
                    "why_it_matters": "Directly linked to the supported retaliation framework.",
                    "main_issue_tags": [],
                    "supporting_finding_ids": ["finding-ret"],
                    "supporting_citation_ids": ["citation-ret"],
                    "supporting_uids": ["uid-linked"],
                    "source_language": "de",
                    "quoted_evidence": {"original_text": "Nach der Beschwerde wurde das Projekt entzogen."},
                    "source_conflict_status": "stable",
                    "linked_source_conflicts": [],
                },
            ]
        },
        comparative_treatment={},
        retaliation_timeline_assessment={},
        employment_issue_frameworks={
            "issue_tracks": [
                {
                    "issue_track": "retaliation_after_protected_event",
                    "status": "supported_by_current_record",
                    "support_reason": "Complaint followed by project withdrawal on the current record.",
                    "why_not_yet_supported": [],
                    "normal_alternative_explanations": ["Could reflect ordinary staffing changes."],
                    "missing_document_checklist": ["Dated trigger-event record"],
                    "supporting_finding_ids": ["finding-ret"],
                    "supporting_citation_ids": ["citation-ret"],
                    "supporting_uids": ["uid-linked"],
                }
            ]
        },
        master_chronology={"summary": {"source_conflict_registry": {"conflict_count": 0, "conflicts": []}}},
    )

    assert payload is not None
    row = next(item for item in payload["rows"] if item["issue_id"] == "retaliation_massregelungsverbot")

    assert row["supporting_source_ids"] == ["email:uid-linked"]
    assert row["strongest_documents"][0]["source_id"] == "email:uid-linked"
    assert "supporting_finding_link" in row["strongest_documents"][0]["selection_basis"]
    assert "supporting_citation_link" in row["strongest_documents"][0]["selection_basis"]
    assert row["strongest_documents"][0]["supporting_finding_ids"] == ["finding-ret"]
    assert row["strongest_documents"][0]["supporting_citation_ids"] == ["citation-ret"]
    assert len(row["strongest_documents"]) == 1
    assert row["heuristic_candidate_documents"][0]["source_id"] == "email:uid-keyword"
    assert row["heuristic_candidate_documents"][0]["selection_basis"] == ["keyword_fallback"]


def test_lawyer_issue_matrix_marks_keyword_only_documents_as_fallback_when_no_explicit_links_exist() -> None:
    payload = build_lawyer_issue_matrix(
        case_bundle={
            "scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
                "employment_issue_tracks": ["eingruppierung_dispute"],
            }
        },
        findings=[],
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-003",
                    "source_id": "formal_document:td",
                    "short_description": "Tarifliche Bewertung der Tätigkeit",
                    "why_it_matters": "Discusses Eingruppierung and role classification.",
                    "main_issue_tags": [],
                    "supporting_finding_ids": [],
                    "supporting_citation_ids": [],
                    "supporting_uids": [],
                    "source_language": "de",
                    "quoted_evidence": {"original_text": "Die tarifliche Bewertung bleibt unverändert."},
                    "source_conflict_status": "stable",
                    "linked_source_conflicts": [],
                }
            ]
        },
        comparative_treatment={},
        retaliation_timeline_assessment={},
        employment_issue_frameworks={
            "issue_tracks": [
                {
                    "issue_track": "eingruppierung_dispute",
                    "status": "not_yet_supported",
                    "support_reason": "",
                    "why_not_yet_supported": ["Current record does not yet show the actually exercised tasks in detail."],
                    "normal_alternative_explanations": [],
                    "missing_document_checklist": ["Current Tätigkeitsdarstellung"],
                    "supporting_finding_ids": [],
                    "supporting_citation_ids": [],
                    "supporting_uids": [],
                }
            ]
        },
        master_chronology={"summary": {"source_conflict_registry": {"conflict_count": 0, "conflicts": []}}},
    )

    assert payload is not None
    row = next(item for item in payload["rows"] if item["issue_id"] == "eingruppierung_tarifliche_bewertung")

    assert row["supporting_source_ids"] == []
    assert row["strongest_documents"] == []
    assert row["heuristic_candidate_documents"][0]["source_id"] == "formal_document:td"
    assert row["heuristic_candidate_documents"][0]["selection_basis"] == ["keyword_fallback"]
    assert row["not_legal_advice"] is True


def test_lawyer_issue_matrix_uses_all_issue_tags_and_ranked_priority_for_strongest_documents() -> None:
    payload = build_lawyer_issue_matrix(
        case_bundle={
            "scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
                "employment_issue_tracks": ["retaliation_after_protected_event"],
            }
        },
        findings=[],
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-010",
                    "source_id": "formal_document:priority",
                    "short_description": "Priority-ranked protocol",
                    "why_it_matters": "Issue tags exist only in the expanded tag set.",
                    "main_issue_tags": [],
                    "all_issue_tags": ["retaliation_massregelung"],
                    "supporting_finding_ids": [],
                    "supporting_citation_ids": [],
                    "supporting_uids": [],
                    "source_reliability": {"level": "high"},
                    "exhibit_reliability": {"strength": "strong"},
                    "source_language": "de",
                    "quoted_evidence": {"original_text": "Nach der Beschwerde wurde die Aufgabe entzogen."},
                    "source_conflict_status": "stable",
                    "linked_source_conflicts": [],
                }
            ],
            "top_15_exhibits": [
                {
                    "exhibit_id": "EXH-010",
                    "source_id": "formal_document:priority",
                    "priority_score": 9,
                    "strength": "strong",
                }
            ],
        },
        comparative_treatment={},
        retaliation_timeline_assessment={},
        employment_issue_frameworks={
            "issue_tracks": [
                {
                    "issue_track": "retaliation_after_protected_event",
                    "status": "supported_by_current_record",
                    "support_reason": "The ranked protocol is the strongest current record.",
                    "why_not_yet_supported": [],
                    "normal_alternative_explanations": [],
                    "missing_document_checklist": [],
                    "supporting_finding_ids": [],
                    "supporting_citation_ids": [],
                    "supporting_uids": [],
                }
            ]
        },
        master_chronology={"summary": {"source_conflict_registry": {"conflict_count": 0, "conflicts": []}}},
    )

    assert payload is not None
    row = next(item for item in payload["rows"] if item["issue_id"] == "retaliation_massregelungsverbot")
    assert row["strongest_documents"][0]["source_id"] == "formal_document:priority"
    assert "issue_tag_link" in row["strongest_documents"][0]["selection_basis"]
    assert "ranked_exhibit_priority" in row["strongest_documents"][0]["selection_basis"]


def test_lawyer_issue_matrix_surfaces_comparator_signals_and_source_conflicts() -> None:
    payload = build_lawyer_issue_matrix(
        case_bundle={
            "scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "context_notes": "Comparator review after complaint and mobile-work restriction.",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
                "employment_issue_tracks": ["disability_disadvantage", "retaliation_after_protected_event"],
            }
        },
        findings=[{"finding_id": "deadline-1", "finding_label": "Deadline pressure"}],
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-004",
                    "source_id": "email:uid-conflict",
                    "short_description": "Restriction email",
                    "why_it_matters": "Shows tighter control after complaint.",
                    "main_issue_tags": ["comparator_evidence"],
                    "supporting_finding_ids": ["finding-disability"],
                    "supporting_citation_ids": ["citation-disability"],
                    "supporting_uids": ["uid-conflict"],
                    "source_language": "en",
                    "quoted_evidence": {"original_text": "Please stop using home office until further notice."},
                    "source_conflict_status": "disputed",
                    "linked_source_conflicts": [
                        {
                            "conflict_id": "SCF-1",
                            "summary": "Meeting note and later email describe the restriction differently.",
                        }
                    ],
                }
            ]
        },
        comparative_treatment={
            "comparator_points": [
                {
                    "comparator_point_id": "cmp:1",
                    "issue_id": "control_intensity",
                    "issue_label": "Control intensity",
                    "comparison_strength": "strong",
                    "point_summary": "Control intensity: claimant-facing messages were harsher. Strength: strong.",
                    "counterargument": "Comparator support remains bounded by current role comparability.",
                }
            ]
        },
        retaliation_timeline_assessment={
            "temporal_correlation_analysis": [
                {
                    "timeline_id": "temporal_correlation:1",
                    "trigger_type": "complaint",
                    "trigger_date": "2025-02-03",
                    "assessment_status": "mixed_shift",
                    "analysis_quality": "medium",
                    "confounder_signals": ["new_sender_appears_after_trigger"],
                    "supporting_uids": ["uid-conflict"],
                }
            ],
            "overall_evidentiary_rating": {"reason": "Timing support remains mixed."},
        },
        employment_issue_frameworks={
            "issue_tracks": [
                {
                    "issue_track": "disability_disadvantage",
                    "status": "supported_by_current_record",
                    "support_reason": "Medical-needs handling may differ from comparator treatment.",
                    "why_not_yet_supported": [],
                    "normal_alternative_explanations": [],
                    "missing_document_checklist": [],
                    "supporting_finding_ids": ["finding-disability"],
                    "supporting_citation_ids": ["citation-disability"],
                    "supporting_uids": ["uid-conflict"],
                }
            ]
        },
        master_chronology={"summary": {"source_conflict_registry": {"conflict_count": 1, "conflicts": []}}},
    )

    assert payload is not None
    row = next(item for item in payload["rows"] if item["issue_id"] == "agg_disadvantage")

    assert any("Comparator point supports unequal-treatment review" in fact for fact in row["relevant_facts"])
    retaliation_row = next(item for item in payload["rows"] if item["issue_id"] == "retaliation_massregelungsverbot")
    assert any("Retaliation timing point" in fact for fact in retaliation_row["relevant_facts"])
    assert "new_sender_appears_after_trigger" in retaliation_row["likely_opposing_argument"]
    assert row["source_conflict_status"] == "contains_unresolved_source_conflict"
    assert row["unresolved_source_conflicts"] == ["Meeting note and later email describe the restriction differently."]
    assert (
        row["urgency_or_deadline_relevance"]
        == "Review for possible deadline-sensitive employment measures in the supporting record."
    )


def test_lawyer_issue_matrix_keeps_full_issue_set_under_exhaustive_scope() -> None:
    payload = build_lawyer_issue_matrix(
        case_bundle={
            "scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-03-31",
                "employment_issue_tracks": ["retaliation_after_protected_event"],
            }
        },
        findings=[],
        matter_evidence_index={"rows": []},
        comparative_treatment={
            "summary": {"status": "insufficient_comparator_scope"},
            "insufficiency": {"recommended_next_inputs": ["Add named comparator actors tied to the same manager or policy."]},
        },
        retaliation_timeline_assessment={},
        employment_issue_frameworks={"issue_tracks": []},
        master_chronology={"summary": {"source_conflict_registry": {"conflict_count": 0, "conflicts": []}}},
        case_scope_quality={"missing_recommended_fields": ["comparator_actors", "org_context", "alleged_adverse_actions"]},
        analysis_limits={"downgrade_reasons": ["retaliation_focus_without_alleged_adverse_actions"]},
        include_full_issue_set=True,
    )

    assert payload is not None
    assert payload["row_count"] == 9
    burden = next(item for item in payload["rows"] if item["issue_id"] == "burden_shifting_indicators")
    retaliation = next(item for item in payload["rows"] if item["issue_id"] == "retaliation_massregelungsverbot")
    participation = next(item for item in payload["rows"] if item["issue_id"] == "pr_lpvg_participation")
    assert any("comparator actors" in item.lower() for item in burden["missing_proof"])
    assert any("adverse actions" in item.lower() for item in retaliation["missing_proof"])
    assert any("org context" in item.lower() for item in participation["missing_proof"]) is False
