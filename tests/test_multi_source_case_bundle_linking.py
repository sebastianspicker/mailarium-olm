# ruff: noqa: F401
from __future__ import annotations

from src.multi_source_case_bundle import append_chat_log_sources, append_manifest_sources, build_multi_source_case_bundle


def test_append_manifest_sources_accounts_for_supplied_artifacts_and_source_classes() -> None:
    bundle = append_manifest_sources(
        {
            "version": "1",
            "summary": {},
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "title": "Status",
                    "date": "2026-03-11T10:00:00",
                    "snippet": "Status email.",
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                }
            ],
            "source_links": [],
            "source_type_profiles": [],
            "chronology_anchors": [],
        },
        matter_manifest={
            "manifest_id": "matter-1",
            "artifacts": [
                {
                    "source_id": "manifest:personnel:1",
                    "source_class": "personnel_file_record",
                    "title": "Personnel file excerpt",
                    "date": "2026-03-10",
                    "filename": "personnel-file.pdf",
                    "mime_type": "application/pdf",
                    "custodian": "HR",
                    "text": "Personnel record excerpt about assignment and complaints.",
                    "summary": "Operator summary that should not replace direct text.",
                    "author": "HR Department",
                    "recipients": ["alex@example.org"],
                    "date_start": "2026-03-01",
                    "date_end": "2026-03-31",
                    "date_is_approximate": True,
                    "text_source_path": "/tmp/personnel-file.pdf",
                    "text_locator": {"kind": "full_document_text", "page_hint": 2},
                    "review_status": "parsed",
                },
                {
                    "source_id": "manifest:chat:1",
                    "source_class": "chat_export",
                    "title": "Teams export",
                    "date": "2026-03-12",
                    "custodian": "IT",
                    "text": "Keep this off email for now.",
                    "participants": ["alex@example.org", "manager@example.org"],
                    "related_email_uid": "uid-1",
                    "review_status": "degraded",
                },
                {
                    "source_id": "manifest:image:1",
                    "source_class": "screenshot",
                    "title": "Screenshot with transcript",
                    "date": "2026-03-13",
                    "text": "Recovered screenshot text.",
                    "review_status": "degraded",
                    "weak_format_semantics": {
                        "recovery_mode": "sidecar_transcript",
                        "sidecar_source_path": "/tmp/screenshot.ocr.txt",
                        "original_format_family": "image",
                    },
                },
            ],
        },
    )

    assert bundle is not None
    assert bundle["summary"]["source_type_counts"]["email"] == 1
    assert bundle["summary"]["source_type_counts"]["formal_document"] == 1
    assert bundle["summary"]["source_type_counts"]["chat_log"] == 1
    assert bundle["summary"]["source_class_counts"]["personnel_file_record"] == 1
    assert bundle["summary"]["source_class_counts"]["chat_export"] == 1
    assert bundle["summary"]["chronology_anchor_count"] >= 3
    manifest_doc = next(source for source in bundle["sources"] if source["source_id"] == "manifest:personnel:1")
    manifest_chat = next(source for source in bundle["sources"] if source["source_id"] == "manifest:chat:1")
    manifest_image = next(source for source in bundle["sources"] if source["source_id"] == "manifest:image:1")
    assert manifest_doc["source_type"] == "formal_document"
    assert manifest_doc["document_kind"] == "personnel_file_record"
    assert manifest_doc["snippet"] == "Personnel record excerpt about assignment and complaints."
    assert manifest_doc["operator_summary"] == "Operator summary that should not replace direct text."
    assert manifest_doc["author"] == "HR Department"
    assert manifest_doc["recipients"] == ["alex@example.org"]
    assert manifest_doc["date_context"] == {
        "display_date": "2026-03-10",
        "date_start": "2026-03-01",
        "date_end": "2026-03-31",
        "is_approximate": True,
        "has_range": True,
    }
    assert manifest_doc["document_locator"]["text_source_path"] == "/tmp/personnel-file.pdf"
    assert manifest_doc["document_locator"]["text_locator"] == {"kind": "full_document_text", "page_hint": 2}
    assert manifest_doc["document_locator"]["snippet_locator"] == {
        "kind": "quoted_snippet",
        "char_start": 0,
        "char_end": len("Personnel record excerpt about assignment and complaints."),
        "line_start": 1,
        "line_end": 1,
    }
    assert manifest_chat["source_type"] == "chat_log"
    assert manifest_chat["participants"] == ["alex@example.org", "manager@example.org"]
    assert manifest_image["weak_format_semantics"]["recovery_mode"] == "sidecar_transcript"
    explicit_link = next(link for link in bundle["source_links"] if link["relationship"] == "matter_manifest_cross_reference")
    assert explicit_link["confidence"] == "high"
    assert explicit_link["match_basis"] == ["explicit_related_email_uid"]


def test_append_manifest_sources_keeps_operator_summary_separate_from_quoteable_snippet() -> None:
    bundle = append_manifest_sources(
        {"version": "1", "summary": {}, "sources": [], "source_links": [], "source_type_profiles": [], "chronology_anchors": []},
        matter_manifest={
            "manifest_id": "matter-2",
            "artifacts": [
                {
                    "source_id": "manifest:meeting:1",
                    "source_class": "meeting_note",
                    "title": "Meeting note",
                    "date": "2026-03-14",
                    "summary": "Operator summary only.",
                    "participants": ["alex@example.org", "manager@example.org"],
                    "review_status": "degraded",
                }
            ],
        },
    )

    assert bundle is not None
    source = bundle["sources"][0]
    assert source["snippet"] == ""
    assert source["operator_summary"] == "Operator summary only."
    assert source["source_weighting"]["text_available"] is False


def test_append_manifest_sources_links_exported_document_to_email_via_headers() -> None:
    bundle = append_manifest_sources(
        {
            "version": "1",
            "summary": {},
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "title": "Status update",
                    "date": "2026-03-11T10:00:00",
                    "snippet": "Status email.",
                    "sender_name": "manager",
                    "sender_email": "manager@example.test",
                    "to": ["employee@example.test"],
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                }
            ],
            "source_links": [],
            "source_type_profiles": [],
            "chronology_anchors": [],
        },
        matter_manifest={
            "manifest_id": "matter-link-1",
            "artifacts": [
                {
                    "source_id": "manifest:doc:1",
                    "source_class": "formal_document",
                    "filename": "status-export.html",
                    "review_status": "parsed",
                    "text": (
                        "# Status update\n"
                        "From: manager <manager@example.test>\n"
                        "To: employee <employee@example.test>\n"
                        "Date: 2026-03-11T10:00:00\n"
                        "Subject: Status update\n"
                        "This is the exported document form of the email."
                    ),
                }
            ],
        },
    )

    assert bundle is not None
    link = next(link for link in bundle["source_links"] if link["from_source_id"] == "manifest:doc:1")
    assert link["to_source_id"] == "email:uid-1"
    assert link["link_type"] == "related_to_email"
    assert link["confidence"] in {"medium", "high"}
    assert "normalized_subject_match" in link["match_basis"]
    assert "same_day_match" in link["match_basis"]
    assert "participant_overlap" in link["match_basis"]


def test_append_manifest_sources_surfaces_ambiguous_header_matches_in_diagnostics() -> None:
    bundle = append_manifest_sources(
        {
            "version": "1",
            "summary": {},
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "title": "Status update",
                    "date": "2026-03-11T10:00:00",
                    "snippet": "Status email.",
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                },
                {
                    "source_id": "email:uid-2",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-2",
                    "title": "Status update",
                    "date": "2026-03-11T12:00:00",
                    "snippet": "Status email copy.",
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                },
            ],
            "source_links": [],
            "source_type_profiles": [],
            "chronology_anchors": [],
        },
        matter_manifest={
            "manifest_id": "matter-link-2",
            "artifacts": [
                {
                    "source_id": "manifest:doc:ambiguous",
                    "source_class": "formal_document",
                    "filename": "status-export.html",
                    "review_status": "parsed",
                    "text": "# Status update\nSubject: Status update\nThis is the exported document form of the email.",
                }
            ],
        },
    )

    assert bundle is not None
    assert all(link["from_source_id"] != "manifest:doc:ambiguous" for link in bundle["source_links"])
    diagnostics = [item for item in bundle["source_link_diagnostics"] if item["source_id"] == "manifest:doc:ambiguous"]
    assert diagnostics
    assert diagnostics[0]["status"] in {"candidate_link", "ambiguous_candidate_link"}


def test_append_manifest_sources_links_manifest_email_even_when_document_appears_first() -> None:
    bundle = append_manifest_sources(
        {
            "version": "1",
            "summary": {},
            "sources": [],
            "source_links": [],
            "source_type_profiles": [],
            "chronology_anchors": [],
        },
        matter_manifest={
            "manifest_id": "matter-order-1",
            "artifacts": [
                {
                    "source_id": "manifest:doc:1",
                    "source_class": "formal_document",
                    "filename": "status-export.html",
                    "review_status": "parsed",
                    "text": (
                        "# Status update\n"
                        "From: manager <manager@example.test>\n"
                        "To: employee <employee@example.test>\n"
                        "Date: 2026-03-11T10:00:00\n"
                        "Subject: Status update\n"
                        "Exported document copy."
                    ),
                },
                {
                    "source_id": "manifest:email:1",
                    "source_class": "formal_document",
                    "filename": "status-mail.html",
                    "review_status": "parsed",
                    "related_email_uid": "uid-1",
                    "text": (
                        "# Status update\n"
                        "From: manager <manager@example.test>\n"
                        "To: employee <employee@example.test>\n"
                        "Date: 2026-03-11T10:00:00\n"
                        "Subject: Status update\n"
                        "Email export body."
                    ),
                },
            ],
        },
    )

    assert bundle is not None
    link = next(link for link in bundle["source_links"] if link["from_source_id"] == "manifest:doc:1")
    assert link["to_source_id"] == "manifest:email:1"
    assert link["confidence"] in {"medium", "high"}


def test_append_chat_log_sources_can_link_without_explicit_related_email_uid() -> None:
    bundle = append_chat_log_sources(
        {
            "version": "1",
            "summary": {},
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "title": "Budget meeting",
                    "date": "2026-03-12T11:00:00",
                    "snippet": "Please keep this off email for now and join the budget meeting.",
                    "sender_name": "Morgan Manager",
                    "sender_email": "manager@example.org",
                    "to": ["alex@example.org"],
                    "source_weighting": {"text_available": True, "can_corroborate_or_contradict": True},
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                }
            ],
            "source_links": [],
            "source_type_profiles": [],
            "source_link_diagnostics": [],
        },
        chat_log_entries=[
            {
                "source_id": "chat-heuristic-1",
                "platform": "Teams",
                "title": "Budget meeting",
                "date": "2026-03-12T11:30:00",
                "participants": ["alex@example.org", "manager@example.org"],
                "text": "Please keep this off email for now.",
            }
        ],
    )

    assert bundle is not None
    heuristic_link = next(link for link in bundle["source_links"] if link["from_source_id"] == "chat-heuristic-1")
    assert heuristic_link["to_source_id"] == "email:uid-1"
    assert heuristic_link["relationship"] == "conservative_chat_email_correlation"


def test_resolve_manifest_email_links_uses_message_or_thread_key_overlap() -> None:
    from src.multi_source_case_bundle_helpers import resolve_manifest_email_links

    links, diagnostics = resolve_manifest_email_links(
        {
            "source_id": "manifest:doc:msgid",
            "source_type": "formal_document",
            "title": "Status update",
            "date": "2026-03-11T10:00:00",
            "snippet": "Document mirror of the message.",
            "searchable_text": "Document mirror of the message.",
            "provenance": {"message_id": "<message-1@example.org>"},
        },
        email_sources=[
            {
                "source_id": "email:uid-1",
                "source_type": "email",
                "title": "Status update",
                "date": "2026-03-11T10:00:00",
                "snippet": "Original message body.",
                "searchable_text": "Original message body.",
                "provenance": {"message_id": "<message-1@example.org>"},
            }
        ],
    )

    assert links[0]["to_source_id"] == "email:uid-1"
    assert "message_or_thread_key_overlap" in links[0]["match_basis"]
    assert any("message_or_thread_key_overlap" in item["match_basis"] for item in diagnostics)
