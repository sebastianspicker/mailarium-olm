from __future__ import annotations

from src.lawyer_briefing_memo import build_lawyer_briefing_memo


def test_build_lawyer_briefing_memo_renders_compact_evidence_bound_sections() -> None:
    payload = build_lawyer_briefing_memo(
        case_bundle={
            "scope": {
                "target_person": {"name": "Alex Example", "email": "alex@example.com"},
                "date_from": "2026-02-01",
                "date_to": "2026-02-20",
            }
        },
        matter_workspace={
            "matter": {
                "case_label": "Case A",
                "target_person_entity_id": "person-target",
            }
        },
        matter_evidence_index={
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "short_description": "Provides direct record material relevant to the synthetic matter review.",
                    "why_it_matters": "Shows a documented exclusion step.",
                    "exhibit_reliability": {"strength": "strong"},
                }
            ],
            "top_15_exhibits": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "short_description": "Email excluding the target from the follow-up step.",
                    "why_it_matters": "Shows a documented exclusion step.",
                    "exhibit_reliability": {"strength": "strong"},
                }
            ],
        },
        master_chronology={
            "summary": {"date_range": {"first": "2026-02-03", "last": "2026-02-18"}},
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2026-02-03",
                    "title": "Complaint lodged",
                    "source_linkage": {"source_ids": ["email:uid-1"]},
                }
            ],
        },
        lawyer_issue_matrix={
            "rows": [
                {
                    "issue_id": "issue-1",
                    "title": "Participation duty gap",
                    "legal_relevance_status": "supported_for_further_review",
                    "relevant_facts": "Meeting records suggest promised participation did not occur.",
                    "strongest_documents": [{"exhibit_id": "EXH-001"}],
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
                    "confounder_signals": ["organizational_restructuring_context_after_trigger"],
                    "supporting_uids": ["uid-1"],
                }
            ],
            "strongest_non_retaliatory_explanations": [{"explanation": "organizational_restructuring_context_after_trigger"}],
        },
        skeptical_employer_review={
            "weaknesses": [
                {
                    "critique": "Comparator support is still thin.",
                    "repair_guidance": {"how_to_fix": "Obtain comparator records."},
                    "supporting_issue_ids": ["issue-1"],
                }
            ]
        },
        document_request_checklist={
            "groups": [
                {
                    "group_id": "group-1",
                    "title": "Participation records",
                    "items": [{"request": "Obtain SBV and meeting invitation records."}],
                }
            ]
        },
        promise_contradiction_analysis={
            "contradiction_table": [
                {
                    "original_statement_or_promise": "Meeting note says SBV will be included.",
                    "later_action": "Later email states SBV was not included.",
                    "original_source_id": "meeting:uid-1:meeting_data",
                    "later_source_id": "email:uid-1",
                }
            ]
        },
    )

    assert payload is not None
    assert payload["version"] == "1"
    assert payload["memo_format"] == "lawyer_onboarding_brief"
    assert payload["summary"]["compact_length_budget"] == "short_onboarding_memo"
    assert payload["summary"]["non_repetition_policy"] is True
    assert payload["sections"]["executive_summary"]
    assert payload["sections"]["executive_summary"][0]["supporting_source_ids"] == ["email:uid-1"]
    assert payload["sections"]["key_facts"][0]["text"] == "Shows a documented exclusion step."
    assert payload["sections"]["core_theories"][0]["supporting_issue_ids"] == ["issue-1"]
    assert any("Retaliation timing:" in entry["text"] for entry in payload["sections"]["core_theories"])
    assert payload["sections"]["strongest_evidence"][0]["supporting_exhibit_ids"] == ["EXH-001"]
    assert any(
        "Retaliation timing remains bounded by explicit confounders" in entry["text"]
        for entry in payload["sections"]["weaknesses_or_risks"]
    )
    assert payload["sections"]["open_questions_for_counsel"][0]["supporting_source_ids"] == [
        "meeting:uid-1:meeting_data",
        "email:uid-1",
    ]
    assert payload["sections"]["urgent_next_steps"][0]["supporting_issue_ids"] == ["issue-1"]


def test_build_lawyer_briefing_memo_labels_unlinked_chronology_when_no_source_backed_entries() -> None:
    payload = build_lawyer_briefing_memo(
        case_bundle={"scope": {"target_person": {"name": "Alex Example"}}},
        matter_workspace={"matter": {"case_label": "Case A"}},
        matter_evidence_index={"rows": [{"exhibit_id": "EXH-001", "short_description": "Record"}], "top_15_exhibits": []},
        master_chronology={
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2026-02-03",
                    "title": "Complaint lodged",
                    "source_linkage": {"source_ids": [], "source_evidence_status": "scope_only"},
                },
                {
                    "chronology_id": "CHR-002",
                    "date": "2026-02-04",
                    "title": "Timeline event",
                    "source_linkage": {"source_ids": [], "source_evidence_status": "timeline_only"},
                },
            ]
        },
        lawyer_issue_matrix={"rows": []},
        retaliation_timeline_assessment={},
        skeptical_employer_review={},
        document_request_checklist={},
        promise_contradiction_analysis={},
    )

    assert payload is not None
    timeline = payload["sections"]["timeline"]
    assert timeline[0]["text"].startswith("[Scope-supplied chronology]")
    assert timeline[1]["text"].startswith("[Timeline-only chronology]")
