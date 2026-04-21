from __future__ import annotations

from src.multi_source_case_bundle import build_multi_source_case_bundle


def test_build_multi_source_case_bundle_preserves_source_types_links_and_reliability():
    case_bundle = {
        "scope": {
            "case_label": "case-a",
        }
    }
    candidates = [
        {
            "uid": "uid-1",
            "sender_actor_id": "actor-manager",
            "subject": "Re: Process",
            "date": "2026-02-12T10:00:00",
            "snippet": "Please see the attached policy update.",
            "verification_status": "forensic_exact",
            "provenance": {"evidence_handle": "email:uid-1"},
            "follow_up": {"tool": "email_deep_context", "uid": "uid-1"},
        }
    ]
    attachment_candidates = [
        {
            "uid": "uid-1",
            "sender_actor_id": "actor-manager",
            "date": "2026-02-12T10:00:00",
            "snippet": "Policy section 4 requires written approval.",
            "provenance": {"evidence_handle": "attachment:uid-1:policy.pdf"},
            "follow_up": {"tool": "email_deep_context", "uid": "uid-1"},
            "attachment": {
                "filename": "policy.pdf",
                "mime_type": "application/pdf",
                "text_available": True,
                "evidence_strength": "strong_text",
                "extraction_state": "text_extracted",
            },
        }
    ]
    full_map = {
        "uid-1": {
            "uid": "uid-1",
            "subject": "Re: Process",
            "date": "2026-02-12T10:00:00",
            "meeting_data": {
                "OPFMeetingLocation": "Room A",
                "OPFMeetingStartDate": "2026-02-12T09:00:00",
            },
        }
    }

    payload = build_multi_source_case_bundle(
        case_bundle=case_bundle,
        candidates=candidates,
        attachment_candidates=attachment_candidates,
        full_map=full_map,
    )

    assert payload is not None
    assert payload["version"] == "1"
    assert payload["summary"]["source_type_counts"] == {
        "email": 1,
        "formal_document": 1,
        "meeting_note": 1,
    }
    assert payload["summary"]["missing_source_types"] == ["attachment", "chat_log"]
    assert payload["summary"]["contradiction_ready_source_count"] == 2
    source_types = {source["source_type"] for source in payload["sources"]}
    assert source_types == {"email", "formal_document", "meeting_note"}
    formal_document = next(source for source in payload["sources"] if source["source_type"] == "formal_document")
    assert formal_document["source_reliability"]["level"] == "high"
    assert formal_document["source_weighting"]["can_corroborate_or_contradict"] is True
    link_types = {link["link_type"] for link in payload["source_links"]}
    assert link_types == {"attached_to_email", "extracted_from_email"}
    assert any(
        link["relationship"] == "can_corroborate_or_contradict_message" for link in payload["source_links"]
    )
