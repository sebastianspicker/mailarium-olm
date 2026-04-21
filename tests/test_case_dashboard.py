from __future__ import annotations

from src.case_dashboard import build_case_dashboard


def test_build_case_dashboard_renders_refreshable_cards_from_shared_entities() -> None:
    payload = build_case_dashboard(
        case_bundle={"scope": {"case_label": "Case A", "target_person": {"name": "Morgan Manager"}}},
        matter_workspace={
            "workspace_id": "workspace:123",
            "matter": {
                "matter_id": "matter:123",
                "bundle_id": "case-123",
                "case_label": "Case A",
            },
        },
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "short_description": "Documented exclusion email.",
                    "why_it_matters": "Shows a concrete exclusion step.",
                    "exhibit_reliability": {"strength": "strong"},
                    "source_id": "email:uid-1",
                }
            ],
            "top_15_exhibits": [
                {
                    "exhibit_id": "EXH-001",
                    "short_description": "Documented exclusion email.",
                    "why_it_matters": "Shows a concrete exclusion step.",
                    "exhibit_reliability": {"strength": "strong"},
                    "source_id": "email:uid-1",
                }
            ],
        },
        master_chronology={
            "summary": {
                "date_gaps_and_unexplained_sequences": [
                    {"gap_id": "gap-1", "summary": "Eight-day silence after the complaint.", "gap_days": 8}
                ]
            },
            "entries": [
                {"chronology_id": "CHR-001", "date": "2026-02-03", "title": "Complaint lodged"},
                {"chronology_id": "CHR-002", "date": "2026-02-11", "title": "Follow-up exclusion email"},
            ],
        },
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "issue-1",
                    "title": "Participation duty gap",
                    "legal_relevance_status": "supported_for_further_review",
                    "relevant_facts": "SBV was promised but not included.",
                }
            ]
        },
        actor_map={
            "actors": [
                {
                    "actor_id": "actor-manager",
                    "name": "Morgan Manager",
                    "status": {"decision_maker": True},
                    "helps_hurts_mixed": "hurts",
                }
            ]
        },
        comparative_treatment={
            "comparator_points": [
                {
                    "comparator_point_id": "cmp:1",
                    "issue_id": "control_intensity",
                    "comparison_strength": "moderate",
                    "point_summary": "Control intensity: comparator emails received faster follow-up. Strength: moderate.",
                }
            ]
        },
        case_patterns={
            "corpus_behavioral_review": {
                "procedural_irregularities": [{"summary": "Participation step missing from later summary."}]
            }
        },
        skeptical_employer_review={"weaknesses": [{"weakness_id": "weak-1", "critique": "Comparator pool remains thin."}]},
        document_request_checklist={
            "groups": [{"group_id": "group-1", "items": [{"request": "Obtain SBV invitation records."}]}]
        },
        promise_contradiction_analysis={
            "contradiction_table": [
                {
                    "original_statement_or_promise": "Meeting note says SBV will be included.",
                    "later_action": "Later email says SBV was not included.",
                    "confidence_level": "medium",
                }
            ]
        },
        deadline_warnings={
            "warnings": [
                {
                    "warning_id": "timing:deadline_relevance",
                    "severity": "medium",
                    "summary": "Some selected issue tracks look operationally time-sensitive.",
                }
            ]
        },
    )

    assert payload is not None
    assert payload["version"] == "1"
    assert payload["dashboard_format"] == "refreshable_case_dashboard"
    assert payload["summary"]["refreshable_from_shared_entities"] is True
    assert payload["cards"]["main_claims_or_issues"][0]["title"] == "Participation duty gap"
    assert payload["cards"]["key_dates"][0]["chronology_id"] == "CHR-001"
    assert payload["cards"]["strongest_exhibits"][0]["exhibit_id"] == "EXH-001"
    assert payload["cards"]["open_evidence_gaps"][0]["gap_id"] == "gap-1"
    assert payload["cards"]["main_actors"][0]["actor_id"] == "actor-manager"
    assert payload["cards"]["comparator_points"][0]["comparator_point_id"] == "cmp:1"
    assert payload["cards"]["comparator_points"][0]["strength"] == "moderate"
    assert "comparator emails received faster follow-up" in payload["cards"]["comparator_points"][0]["summary"].lower()
    assert payload["cards"]["process_irregularities"][0]["summary"]
    assert payload["cards"]["drafting_priorities"][0]["confidence"] == "medium"
    assert payload["cards"]["timing_warnings"][0]["warning_id"] == "timing:deadline_relevance"
    assert payload["cards"]["risks_or_weak_spots"][0]["weakness_id"] == "weak-1"
    assert payload["cards"]["recommended_next_actions"][0]["group_id"] == "group-1"


def test_build_case_dashboard_suppresses_blank_placeholder_cards() -> None:
    payload = build_case_dashboard(
        case_bundle={"scope": {"case_label": "Case A"}},
        matter_workspace={"workspace_id": "workspace:123", "matter": {"matter_id": "matter:123"}},
        matter_evidence_index={
            "rows": [{"exhibit_id": "EXH-001", "short_description": "Anchored email."}],
            "top_15_exhibits": [
                {
                    "exhibit_id": "EXH-blank",
                    "quoted_evidence": {},
                    "document_locator": {},
                    "exhibit_reliability": {},
                },
                {
                    "exhibit_id": "EXH-001",
                    "short_description": "Anchored email.",
                    "exhibit_reliability": {"strength": "strong"},
                },
            ],
        },
        master_chronology={
            "summary": {
                "date_gaps_and_unexplained_sequences": [
                    {"gap_id": "gap-blank", "gap_days": 0},
                    {"gap_id": "gap-1", "gap_days": 8},
                ]
            },
            "entries": [],
        },
        lawyer_issue_matrix={"rows": []},
        actor_map={},
        comparative_treatment={},
        case_patterns={
            "corpus_behavioral_review": {
                "procedural_irregularities": [{}, {"summary": "Participation step missing from later summary."}]
            }
        },
        skeptical_employer_review={},
        document_request_checklist={},
        promise_contradiction_analysis={},
    )

    assert payload is not None
    assert payload["cards"]["strongest_exhibits"] == [
        {
            "exhibit_id": "EXH-001",
            "source_id": "",
            "summary": "Anchored email.",
            "strength": "strong",
            "source_language": "",
            "source_conflict_status": "",
            "supporting_source_ids": [],
            "supporting_uids": [],
            "quoted_evidence": {},
            "document_locator": {},
        }
    ]
    assert payload["cards"]["open_evidence_gaps"] == [
        {
            "gap_id": "gap-1",
            "summary": "8-day unexplained gap",
            "gap_days": 8,
            "priority": "",
            "missing_bridge_record_suggestions": [],
        }
    ]
    assert payload["cards"]["process_irregularities"] == [{"summary": "Participation step missing from later summary."}]
    assert payload["cards"]["comparator_points"] == [
        {
            "status": "insufficient_evidence",
            "summary": "Comparator analysis is not yet supported on the current record.",
        }
    ]
    assert payload["cards"]["drafting_priorities"] == [
        {
            "status": "insufficient_evidence",
            "summary": "No contradiction-driven drafting priority is currently available on the shared record.",
        }
    ]
