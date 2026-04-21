from __future__ import annotations

from src.matter_evidence_index import build_matter_evidence_index


def test_build_matter_evidence_index_adds_structured_exhibit_reliability_layers():
    payload = build_matter_evidence_index(
        case_bundle={
            "scope": {
                "employment_issue_tracks": [
                    "retaliation_after_protected_event",
                    "participation_duty_gap",
                ]
            }
        },
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 1, "formal_document": 1, "attachment": 1}},
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "title": "Status",
                    "date": "2026-02-10T10:00:00",
                    "snippet": "Please comply with the updated process.",
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "provenance": {"evidence_handle": "email:uid-1"},
                },
                {
                    "source_id": "formal_document:uid-2:note.pdf",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "uid": "uid-2",
                    "title": "OCR Note",
                    "date": "2026-02-11T10:00:00",
                    "snippet": "OCR text preview for the note.",
                    "documentary_support": {
                        "text_available": True,
                        "evidence_strength": "strong_text",
                        "extraction_state": "ocr_text_extracted",
                        "ocr_used": True,
                        "format_profile": {
                            "format_id": "scanned_pdf",
                            "format_label": "Scanned PDF",
                            "support_level": "degraded_supported",
                            "manual_review_required": True,
                            "lossiness": "medium",
                        },
                        "extraction_quality": {
                            "quality_label": "ocr_text_recovered",
                            "quality_rank": "medium",
                            "lossiness": "medium",
                            "manual_review_required": True,
                            "visible_limitations": [
                                "Text depends on OCR recovery rather than native PDF text.",
                            ],
                        },
                        "review_recommendation": (
                            "OCR-recovered text is usable, but the original page image should be checked "
                            "before relying on fine wording."
                        ),
                    },
                    "source_reliability": {"level": "medium", "basis": "formal_document_ocr_text_extracted"},
                    "provenance": {"evidence_handle": "attachment:uid-2:note.pdf"},
                },
                {
                    "source_id": "attachment:uid-3:image.png",
                    "source_type": "attachment",
                    "document_kind": "image_attachment",
                    "uid": "uid-3",
                    "title": "Photo Reference",
                    "date": "2026-02-12T10:00:00",
                    "snippet": "",
                    "documentary_support": {
                        "text_available": False,
                        "evidence_strength": "weak_reference",
                        "extraction_state": "ocr_failed",
                        "ocr_used": True,
                        "failure_reason": "ocr_failed",
                        "format_profile": {
                            "format_id": "image_only_exhibit",
                            "format_label": "Screenshot or image-only exhibit",
                            "support_level": "reference_only",
                            "manual_review_required": True,
                            "lossiness": "high",
                        },
                        "extraction_quality": {
                            "quality_label": "ocr_failed",
                            "quality_rank": "low",
                            "lossiness": "high",
                            "manual_review_required": True,
                            "visible_limitations": [
                                "Image-only exhibits need manual visual review before exact wording is relied on.",
                            ],
                        },
                        "review_recommendation": (
                            "Treat this source as a weak documentary reference until the original file is reviewed manually."
                        ),
                    },
                    "source_reliability": {"level": "low", "basis": "attachment_ocr_failed"},
                    "provenance": {"evidence_handle": "attachment:uid-3:image.png"},
                },
            ],
            "source_links": [],
        },
        master_chronology={
            "summary": {
                "date_gaps_and_unexplained_sequences": [
                    {
                        "gap_id": "GAP-001",
                        "gap_days": 18,
                        "priority": "high",
                        "linked_issue_tracks": ["retaliation_after_protected_event"],
                    }
                ],
                "source_conflict_registry": {
                    "conflict_count": 1,
                    "conflicts": [
                        {
                            "conflict_id": "SCF-001",
                            "conflict_kind": "inconsistent_summary",
                            "resolution_status": "provisional_preference",
                            "summary": "Meeting summary and later email describe the same step differently.",
                            "source_ids": ["email:uid-1", "formal_document:uid-2:note.pdf"],
                        }
                    ],
                },
            }
        },
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "finding-1",
                    "finding_label": "Process pressure",
                    "supporting_evidence": [
                        {
                            "citation_id": "c-1",
                            "message_or_document_id": "uid-1",
                        }
                    ],
                }
            ]
        },
    )

    assert payload is not None
    assert payload["row_count"] == 3
    rows = {row["source_id"]: row for row in payload["rows"]}

    strong = rows["email:uid-1"]["exhibit_reliability"]
    assert strong["strength"] == "strong"
    assert strong["source_basis"] == "authored_email_body"
    assert strong["next_step_logic"]["readiness"] == "usable_now"

    moderate = rows["formal_document:uid-2:note.pdf"]["exhibit_reliability"]
    assert moderate["strength"] == "moderate"
    assert moderate["next_step_logic"]["readiness"] == "usable_with_original_source_check"
    assert "OCR" in moderate["reason"]
    assert rows["formal_document:uid-2:note.pdf"]["source_format_support"]["format_id"] == "scanned_pdf"
    assert rows["formal_document:uid-2:note.pdf"]["extraction_quality"]["quality_label"] == "ocr_text_recovered"

    weak = rows["attachment:uid-3:image.png"]["exhibit_reliability"]
    assert weak["strength"] == "weak"
    assert weak["next_step_logic"]["readiness"] == "manual_review_required"
    assert weak["next_step_logic"]["blocking_points"]
    assert any("Screenshot or image-only exhibit" in step for step in rows["attachment:uid-3:image.png"]["follow_up_needed"])

    assert payload["summary"]["exhibit_strength_counts"] == {
        "strong": 1,
        "moderate": 1,
        "weak": 1,
        "unknown": 0,
    }
    assert payload["summary"]["exhibit_readiness_counts"] == {
        "usable_now": 1,
        "usable_with_original_source_check": 1,
        "manual_review_required": 1,
    }
    assert payload["summary"]["source_conflict_status_counts"] == {
        "stable": 1,
        "disputed": 2,
    }
    assert payload["top_15_exhibits"][0]["source_id"] == "email:uid-1"
    assert payload["top_15_exhibits"][0]["priority_score"] >= payload["top_15_exhibits"][1]["priority_score"]
    assert payload["top_10_missing_exhibits"]
    assert payload["top_10_missing_exhibits"][0]["linked_date_gap_ids"] == ["GAP-001"]
    assert payload["top_10_missing_exhibits"][0]["issue_track"] == "retaliation_after_protected_event"
    assert (
        "Complaint, objection, HR-contact, or participation-event record"
        in payload["top_10_missing_exhibits"][0]["requested_exhibit"]
    )
    assert rows["email:uid-1"]["source_conflict_status"] == "disputed"
    assert rows["email:uid-1"]["linked_source_conflicts"][0]["conflict_kind"] == "inconsistent_summary"


def test_build_matter_evidence_index_surfaces_adverse_action_review_hints() -> None:
    payload = build_matter_evidence_index(
        case_bundle={"scope": {"employment_issue_tracks": ["retaliation_after_protected_event"]}},
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 1}},
            "sources": [
                {
                    "source_id": "email:uid-4",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-4",
                    "title": "Project removal notice",
                    "date": "2026-02-12T10:00:00",
                    "snippet": "You are removed from project X and home office is suspended.",
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "provenance": {"evidence_handle": "email:uid-4"},
                }
            ],
            "source_links": [],
        },
        master_chronology={
            "summary": {
                "date_gaps_and_unexplained_sequences": [],
                "source_conflict_registry": {"conflict_count": 0},
            }
        },
        finding_evidence_index={"findings": []},
    )

    assert payload is not None
    row = payload["rows"][0]
    assert "adverse-action review" in row["why_it_matters"]
    assert any("adverse action candidate" in item for item in row["follow_up_needed"])


def test_build_matter_evidence_index_uses_document_author_and_recipients_when_available() -> None:
    payload = build_matter_evidence_index(
        case_bundle={"scope": {"employment_issue_tracks": []}},
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"formal_document": 1}},
            "sources": [
                {
                    "source_id": "manifest:file:1",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "title": "Arbeitsunfähigkeitsmeldung",
                    "date": "2026-03-06T10:57:24",
                    "snippet": "Lieber manager, liebe Anabel, ich melde mich heute krank.",
                    "author": "Target, Person <target.person@example.org>",
                    "recipients": [
                        "Manager, Two <manager.two@example.org>",
                        "Recipient, One <recipient.one@example.org>",
                    ],
                    "source_reliability": {"level": "high", "basis": "matter_manifest_parsed"},
                    "provenance": {"evidence_handle": "manifest:file:1"},
                }
            ],
            "source_links": [],
        },
        master_chronology={
            "summary": {
                "date_gaps_and_unexplained_sequences": [],
                "source_conflict_registry": {"conflict_count": 0},
            }
        },
        finding_evidence_index={"findings": []},
    )

    assert payload is not None
    row = payload["rows"][0]
    assert row["sender_or_author"] == "Target, Person"
    assert row["recipients"] == [
        "Manager, Two",
        "Recipient, One",
    ]


def test_build_matter_evidence_index_uses_entity_occurrence_issue_tag_basis() -> None:
    payload = build_matter_evidence_index(
        case_bundle={"scope": {"employment_issue_tracks": []}},
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 1}},
            "sources": [
                {
                    "source_id": "email:uid-entity-occ",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-entity-occ",
                    "title": "Participation process",
                    "date": "2026-03-01T10:00:00",
                    "snippet": "",
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "provenance": {"evidence_handle": "email:uid-entity-occ"},
                    "entity_occurrences": [
                        {
                            "entity_text": "SBV",
                            "entity_type": "organization",
                            "normalized_form": "sbv",
                            "source_scope": "authored_body",
                            "segment_ordinal": 0,
                            "char_start": 12,
                            "char_end": 15,
                            "occurrence_text": "without SBV participation in the process",
                        }
                    ],
                }
            ],
            "source_links": [],
        },
        master_chronology={
            "summary": {
                "date_gaps_and_unexplained_sequences": [],
                "source_conflict_registry": {"conflict_count": 0},
            }
        },
        finding_evidence_index={"findings": []},
    )

    row = payload["rows"][0]
    issue_tags = [item for item in row.get("issue_tags", []) if isinstance(item, dict)]
    assert issue_tags
    assert any(str(item.get("assignment_basis") or "") == "entity_occurrence_locator" for item in issue_tags)


def test_build_matter_evidence_index_links_manifest_only_document_to_email_findings_and_identities() -> None:
    payload = build_matter_evidence_index(
        case_bundle={"scope": {"employment_issue_tracks": ["participation_duty_gap"]}},
        multi_source_case_bundle={
            "summary": {"source_type_counts": {"email": 1, "formal_document": 1}},
            "sources": [
                {
                    "source_id": "email:uid-linked",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-linked",
                    "title": "Participation reminder",
                    "date": "2026-03-11T10:00:00",
                    "snippet": "SBV participation was still missing.",
                    "sender_name": "manager",
                    "sender_email": "manager@example.test",
                    "to": ["alex@example.org"],
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "provenance": {"evidence_handle": "email:uid-linked"},
                },
                {
                    "source_id": "manifest:doc:1",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "title": "Exported note",
                    "date": "2026-03-11",
                    "snippet": "Exported note mirroring the email.",
                    "source_reliability": {"level": "medium", "basis": "matter_manifest_parsed"},
                    "provenance": {"evidence_handle": "manifest:doc:1"},
                },
            ],
            "source_links": [
                {
                    "from_source_id": "manifest:doc:1",
                    "to_source_id": "email:uid-linked",
                    "link_type": "related_to_email",
                    "relationship": "conservative_document_email_correlation",
                }
            ],
        },
        master_chronology={
            "summary": {"date_gaps_and_unexplained_sequences": [], "source_conflict_registry": {"conflict_count": 0}}
        },
        finding_evidence_index={
            "findings": [
                {
                    "finding_id": "finding-linked",
                    "finding_label": "Participation gap",
                    "supporting_evidence": [
                        {
                            "citation_id": "citation-linked",
                            "message_or_document_id": "uid-linked",
                            "source_id": "email:uid-linked",
                            "provenance": {"evidence_handle": "email:uid-linked"},
                        }
                    ],
                }
            ]
        },
    )

    assert payload is not None
    row = next(row for row in payload["rows"] if row["source_id"] == "manifest:doc:1")
    assert row["supporting_finding_ids"] == ["finding-linked"]
    assert row["supporting_citation_ids"] == ["citation-linked"]
    assert row["supporting_source_ids"] == ["manifest:doc:1", "email:uid-linked"]
    assert row["sender_or_author"] == "manager"
    assert row["recipients"] == ["alex@example.org"]
