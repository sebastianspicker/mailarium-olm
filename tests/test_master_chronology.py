from __future__ import annotations

from src.master_chronology import build_master_chronology


def test_build_master_chronology_adds_source_linkage_and_date_precision() -> None:
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "employment_issue_tracks": [
                    "disability_disadvantage",
                    "retaliation_after_protected_event",
                    "participation_duty_gap",
                ],
                "employment_issue_tags": ["sbv_participation"],
                "context_notes": "SBV participation concerns arose after the complaint and disability context was known.",
                "org_context": {
                    "vulnerability_contexts": [
                        {
                            "context_type": "disability",
                        }
                    ]
                },
                "trigger_events": [
                    {
                        "trigger_type": "complaint",
                        "date": "2026-02-11",
                    }
                ],
            }
        },
        timeline={
            "events": [
                {
                    "uid": "uid-1",
                    "date": "2026-02-12T10:00:00",
                    "subject": "Status",
                    "conversation_id": "conv-1",
                },
                {
                    "uid": "uid-9",
                    "date": "2026-03-01T10:30",
                    "subject": "Fallback",
                    "conversation_id": "conv-9",
                },
            ]
        },
        multi_source_case_bundle={
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
                    "uid": "uid-1",
                    "title": "Status",
                    "date": "2026-02-12T10:00:00",
                    "snippet": "For the record, SBV participation was still missing after the complaint.",
                    "provenance": {"evidence_handle": "email:uid-1"},
                }
            ],
        },
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "finding-1",
                    "supporting_evidence": [
                        {"citation_id": "c-1", "message_or_document_id": "uid-1"},
                        {"citation_id": "c-9", "message_or_document_id": "uid-9"},
                    ],
                }
            ]
        },
    )

    assert payload is not None
    assert payload["entry_count"] == 3
    assert payload["primary_entry_count"] == 2
    assert payload["scope_supplied_entry_count"] == 1
    assert payload["summary"]["entry_type_counts"] == {
        "trigger_event": 1,
        "source_event": 1,
        "timeline_event": 1,
    }
    assert payload["summary"]["date_precision_counts"] == {
        "day": 1,
        "second": 1,
        "minute": 1,
    }
    assert payload["summary"]["source_evidence_status_counts"] == {
        "linked_record": 1,
        "scope_only": 1,
        "timeline_only": 1,
    }
    assert payload["summary"]["date_range"] == {
        "first": "2026-02-12T10:00:00",
        "last": "2026-03-01T10:30",
    }
    assert payload["summary"]["combined_date_range"] == {
        "first": "2026-02-11",
        "last": "2026-03-01T10:30",
    }
    assert payload["summary"]["source_linked_entry_count"] == 2
    assert payload["summary"]["date_gap_count"] == 1
    assert payload["summary"]["largest_gap_days"] == 17
    gap = payload["summary"]["date_gaps_and_unexplained_sequences"][0]
    assert gap["gap_days"] == 17
    assert gap["priority"] == "high"
    assert gap["from_chronology_id"] == "CHR-002"
    assert gap["to_chronology_id"] == "CHR-003"

    source_entry = next(entry for entry in payload["entries"] if entry["entry_type"] == "source_event")
    assert source_entry["source_linkage"]["source_ids"] == ["email:uid-1"]
    assert source_entry["source_linkage"]["supporting_citation_ids"] == ["c-1"]
    assert source_entry["source_linkage"]["evidence_handles"] == ["email:uid-1"]
    assert source_entry["event_support_matrix"]["participation_duty_gap"]["status"] == "direct_event_support"
    assert source_entry["event_support_matrix"]["disability_disadvantage"]["status"] == "contextual_support_only"
    assert source_entry["event_support_matrix"]["ordinary_managerial_explanation"]["status"] == "plausible_alternative"

    trigger_entry = next(entry for entry in payload["entries"] if entry["entry_type"] == "trigger_event")
    assert trigger_entry["event_support_matrix"]["retaliation_after_protected_event"]["status"] == "direct_event_support"

    fallback_entry = next(entry for entry in payload["entries"] if entry["entry_type"] == "timeline_event")
    assert fallback_entry["date_precision"] == "minute"
    assert fallback_entry["source_linkage"]["supporting_citation_ids"] == ["c-9"]
    assert fallback_entry["source_linkage"]["source_ids"] == ["email:uid-9"]
    assert fallback_entry["source_linkage"]["evidence_handles"] == ["email:uid-9"]
    assert payload["summary"]["event_read_status_counts"]["ordinary_managerial_explanation:plausible_alternative"] == 2
    neutral_view = payload["views"]["short_neutral_chronology"]
    assert neutral_view["entry_count"] == 2
    assert neutral_view["items"][0]["chronology_id"] == "CHR-002"
    assert neutral_view["items"][0]["structured_row"]["source_document"]["source_ids"] == ["email:uid-1"]
    assert neutral_view["items"][0]["structured_row"]["event_description"]
    claimant_view = payload["views"]["claimant_favorable_chronology"]
    assert any(item["favored_read_id"] == "retaliation_after_protected_event" for item in claimant_view["items"])
    assert claimant_view["items"][0]["uncertainty_note"]
    assert claimant_view["items"][0]["structured_row"]["supports"]["retaliation"] in {
        "direct_event_support",
        "contextual_support_only",
        "not_signaled",
    }
    defense_view = payload["views"]["defense_favorable_chronology"]
    assert defense_view["entry_count"] == 2
    assert defense_view["items"][0]["favored_read_id"] == "ordinary_managerial_explanation"
    assert defense_view["items"][0]["counterargument_note"]
    balanced_view = payload["views"]["balanced_timeline_assessment"]
    assert balanced_view["summary"]["strongest_timeline_inferences"]
    assert balanced_view["summary"]["strongest_limits"]
    assert balanced_view["items"][0]["structured_row"]["significance_to_case"]


def test_build_master_chronology_uses_document_dates_ranges_and_bridge_hints() -> None:
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "employment_issue_tracks": ["retaliation_after_protected_event", "participation_duty_gap"],
                "context_notes": "SBV participation remained open after the complaint.",
                "trigger_events": [{"trigger_type": "complaint", "date": "2026-03-05"}],
            }
        },
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [
                {
                    "source_id": "note_record:uid-2:summary.txt",
                    "source_type": "note_record",
                    "document_kind": "attached_note_record",
                    "date": "2026-03-05",
                    "title": "Meeting Summary",
                    "reliability_level": "high",
                    "date_origin": "document_text",
                },
                {
                    "source_id": "time_record:uid-3:attendance.xlsx",
                    "source_type": "time_record",
                    "document_kind": "attached_time_record",
                    "date": "2026-03-01",
                    "title": "Attendance Record",
                    "reliability_level": "high",
                    "date_origin": "time_record_range_start",
                    "date_range": {
                        "start": "2026-03-01",
                        "end": "2026-03-31",
                    },
                    "source_recorded_date": "2026-03-31T18:00:00",
                },
                {
                    "source_id": "participation_record:uid-4:sbv.pdf",
                    "source_type": "participation_record",
                    "document_kind": "attached_participation_record",
                    "date": "2026-04-20",
                    "title": "SBV Record",
                    "reliability_level": "high",
                    "date_origin": "source_timestamp",
                },
            ],
            "sources": [
                {
                    "source_id": "note_record:uid-2:summary.txt",
                    "source_type": "note_record",
                    "uid": "uid-2",
                    "title": "Meeting Summary",
                    "date": "2026-03-20T11:00:00",
                    "snippet": "Meeting summary for 2026-03-05 about the complaint follow-up.",
                    "provenance": {"evidence_handle": "attachment:uid-2:summary.txt"},
                },
                {
                    "source_id": "time_record:uid-3:attendance.xlsx",
                    "source_type": "time_record",
                    "uid": "uid-3",
                    "title": "Attendance Record",
                    "date": "2026-03-31T18:00:00",
                    "snippet": "Attendance record covering 2026-03-01 to 2026-03-31.",
                    "provenance": {"evidence_handle": "attachment:uid-3:attendance.xlsx"},
                },
                {
                    "source_id": "participation_record:uid-4:sbv.pdf",
                    "source_type": "participation_record",
                    "uid": "uid-4",
                    "title": "SBV Record",
                    "date": "2026-04-20",
                    "snippet": "SBV participation request remained unresolved.",
                    "provenance": {"evidence_handle": "attachment:uid-4:sbv.pdf"},
                },
            ],
        },
        finding_evidence_index={"findings": []},
    )

    assert payload is not None
    assert payload["entry_count"] == 4
    time_entry = next(entry for entry in payload["entries"] if entry["source_linkage"]["source_types"] == ["time_record"])
    assert time_entry["coverage_window"] == {"start": "2026-03-01", "end": "2026-03-31"}
    assert time_entry["date_origin"] == "time_record_range_start"
    gaps = payload["summary"]["date_gaps_and_unexplained_sequences"]
    assert len(gaps) == 1
    assert gaps[0]["gap_days"] == 46
    assert gaps[0]["missing_bridge_record_suggestions"]
    assert "formal decision" in gaps[0]["missing_bridge_record_suggestions"][0].lower()
    sequence_break = payload["summary"]["sequence_breaks_and_contradictions"][0]
    assert sequence_break["delta_days"] == 30


def test_build_master_chronology_includes_asserted_rights_timeline_entries() -> None:
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "employment_issue_tracks": ["retaliation_after_protected_event"],
                "asserted_rights_timeline": [
                    {
                        "trigger_type": "escalation_to_hr",
                        "date": "2026-02-03",
                        "notes": "Escalation to HR about the exclusion sequence.",
                    }
                ],
            }
        },
        timeline={"events": []},
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )

    assert payload is not None
    assert payload["entry_count"] == 1
    entry = payload["entries"][0]
    assert entry["entry_type"] == "trigger_event"
    assert entry["date"] == "2026-02-03"
    assert "escalation" in entry["title"].lower()


def test_build_master_chronology_includes_alleged_adverse_actions() -> None:
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "employment_issue_tracks": ["retaliation_after_protected_event"],
                "alleged_adverse_actions": [
                    {
                        "action_type": "project_removal",
                        "date": "2026-02-10",
                    }
                ],
            }
        },
        timeline={"events": []},
        multi_source_case_bundle={"chronology_anchors": [], "sources": []},
        finding_evidence_index={"findings": []},
    )

    assert payload is not None
    assert payload["entry_count"] == 1
    entry = payload["entries"][0]
    assert entry["entry_type"] == "adverse_action_event"
    assert entry["title"] == "Project removal"


def test_build_master_chronology_carries_linked_source_ids_and_anchor_metadata() -> None:
    payload = build_master_chronology(
        case_bundle={"scope": {"employment_issue_tracks": ["participation_duty_gap"]}},
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [
                {
                    "source_id": "manifest:doc:1",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "date": "2026-03-05",
                    "title": "Meeting summary",
                    "date_origin": "document_text",
                    "anchor_confidence": "medium",
                    "date_candidates": [
                        {"date": "2026-03-05", "origin": "document_text", "confidence": "medium"},
                        {"date": "2026-03-20", "origin": "source_timestamp", "confidence": "medium"},
                    ],
                }
            ],
            "sources": [
                {
                    "source_id": "manifest:doc:1",
                    "source_type": "formal_document",
                    "title": "Meeting summary",
                    "date": "2026-03-20T11:00:00",
                    "snippet": "Summary of the meeting.",
                    "provenance": {"evidence_handle": "manifest:doc:1"},
                },
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "uid": "uid-1",
                    "title": "Meeting summary",
                    "date": "2026-03-05T09:00:00",
                    "snippet": "The meeting summary confirms the process gap.",
                    "provenance": {"evidence_handle": "email:uid-1"},
                },
            ],
            "source_links": [
                {
                    "from_source_id": "manifest:doc:1",
                    "to_source_id": "email:uid-1",
                    "link_type": "related_to_email",
                    "relationship": "conservative_document_email_correlation",
                }
            ],
        },
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "finding-1",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-1",
                            "message_or_document_id": "uid-1",
                            "source_id": "email:uid-1",
                            "provenance": {"evidence_handle": "email:uid-1"},
                        }
                    ],
                }
            ]
        },
    )

    assert payload is not None
    entry = payload["entries"][0]
    assert entry["source_linkage"]["source_ids"] == ["manifest:doc:1", "email:uid-1"]
    assert entry["source_linkage"]["supporting_uids"] == ["uid-1"]
    assert entry["source_linkage"]["supporting_citation_ids"] == ["c-1"]
    assert entry["anchor_confidence"] == "medium"
    assert len(entry["date_candidates"]) == 2


def test_build_master_chronology_surfaces_source_conflicts_and_priority_rules() -> None:
    payload = build_master_chronology(
        case_bundle={
            "scope": {
                "employment_issue_tracks": ["participation_duty_gap"],
                "context_notes": "SBV participation remained disputed in later summaries.",
            }
        },
        timeline={"events": []},
        multi_source_case_bundle={
            "chronology_anchors": [
                {
                    "source_id": "meeting:uid-1:meeting_data",
                    "source_type": "meeting_note",
                    "document_kind": "calendar_metadata",
                    "date": "2026-02-11",
                    "title": "Meeting notes",
                    "reliability_level": "high",
                    "date_origin": "meeting_metadata",
                },
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "date": "2026-02-12T10:00:00",
                    "title": "Status",
                    "reliability_level": "high",
                    "date_origin": "source_timestamp",
                },
            ],
            "sources": [
                {
                    "source_id": "meeting:uid-1:meeting_data",
                    "source_type": "meeting_note",
                    "uid": "uid-1",
                    "title": "Meeting notes",
                    "date": "2026-02-11",
                    "snippet": "We agreed to include SBV and will send a written summary.",
                    "source_reliability": {"level": "high", "basis": "calendar_meeting_metadata"},
                },
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "uid": "uid-1",
                    "title": "Status",
                    "date": "2026-02-12T10:00:00",
                    "snippet": "We did not include SBV and will not send a written summary yet.",
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                },
            ],
            "source_links": [
                {
                    "from_source_id": "meeting:uid-1:meeting_data",
                    "to_source_id": "email:uid-1",
                    "link_type": "related_to_email",
                }
            ],
        },
        finding_evidence_index={"findings": []},
    )

    assert payload is not None
    registry = payload["summary"]["source_conflict_registry"]
    assert registry["source_conflict_status"] == "conflicted"
    assert registry["conflict_count"] >= 1
    assert any(rule["rule_id"] == "primary_document_over_operator_note" for rule in registry["priority_rules"])
    summary_conflict = next(conflict for conflict in registry["conflicts"] if conflict["conflict_kind"] == "inconsistent_summary")
    assert summary_conflict["priority_rule_applied"] == "authored_text_over_metadata"
    assert summary_conflict["preferred_source_id"] == "email:uid-1"
    disputed_entry = next(
        entry for entry in payload["entries"] if "meeting:uid-1:meeting_data" in entry["source_linkage"]["source_ids"]
    )
    assert disputed_entry["fact_stability"] == "disputed"
    assert disputed_entry["source_conflict_ids"]
