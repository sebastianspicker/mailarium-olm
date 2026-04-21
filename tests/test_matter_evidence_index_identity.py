from __future__ import annotations

from src.matter_evidence_index import build_matter_evidence_index


def test_build_matter_evidence_index_uses_email_metadata_for_sender_and_recipients() -> None:
    payload = build_matter_evidence_index(
        case_bundle={
            "scope": {
                "target_person": {"name": "employee"},
                "analysis_goal": "lawyer_briefing",
                "date_from": "2025-01-01",
                "date_to": "2025-02-01",
                "employment_issue_tracks": ["retaliation_after_protected_event"],
            }
        },
        multi_source_case_bundle={
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "uid": "uid-1",
                    "date": "2025-01-15T09:00:00",
                    "title": "Meeting follow-up",
                    "snippet": "Please send future accommodation requests only through management.",
                    "sender_name": "manager",
                    "sender_email": "manager@example.test",
                    "to": ["employee <employee@example.test>"],
                    "cc": ["SBV <sbv@example.org>"],
                    "bcc": ["Legal <legal@example.org>"],
                    "source_reliability": {"level": "high", "basis": "authored_email_body"},
                    "provenance": {"evidence_handle": "email:uid-1"},
                },
                {
                    "source_id": "formal_document:uid-2:note.pdf",
                    "source_type": "formal_document",
                    "document_kind": "attached_document",
                    "uid": "uid-2",
                    "date": "2025-01-16",
                    "title": "Gedächtnisprotokoll",
                    "snippet": "Summary prepared after the meeting.",
                    "actor_id": "HR",
                    "source_reliability": {"level": "medium", "basis": "operator_supplied_document"},
                    "provenance": {"evidence_handle": "attachment:uid-2:note.pdf"},
                },
            ],
            "source_links": [],
        },
        finding_evidence_index={"findings": []},
        master_chronology={"summary": {}},
    )

    assert payload is not None
    rows = {row["source_id"]: row for row in payload["rows"]}

    email_row = rows["email:uid-1"]
    assert email_row["sender_or_author"] == "manager"
    assert email_row["sender_identity"] == {
        "name": "manager",
        "email": "manager@example.test",
        "display": "manager",
        "role": "sender",
        "identity_source": "email_metadata",
    }
    assert email_row["recipients"] == ["employee", "SBV", "Legal"]
    assert email_row["recipient_identities"]["to"][0]["email"] == "employee@example.test"
    assert email_row["recipient_identities"]["cc"][0]["display"] == "SBV"
    assert email_row["recipient_identities"]["bcc"][0]["display"] == "Legal"

    note_row = rows["formal_document:uid-2:note.pdf"]
    assert note_row["sender_or_author"] == "HR"
    assert note_row["recipient_identities"] == {"to": [], "cc": [], "bcc": []}
    assert note_row["recipients"] == []
