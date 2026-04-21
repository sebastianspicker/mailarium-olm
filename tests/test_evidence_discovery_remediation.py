from __future__ import annotations

import io
import zipfile

from src.attachment_extractor import classify_text_extraction_state, extract_text
from src.conversation_segments import ConversationSegment
from src.email_db import EmailDatabase
from src.evidence_harvest import harvest_wave_payload
from src.ingest_reingest import reextract_entities_impl, reingest_analytics_impl
from src.parse_olm import Email
from src.parse_olm_postprocess import ParsedEmailParts, derive_email_enrichments


def _email(**overrides) -> Email:
    payload = {
        "message_id": "<msg-1@example.com>",
        "subject": "Test subject",
        "sender_name": "employee",
        "sender_email": "employee@example.test",
        "to": ["Bob <bob@example.com>"],
        "cc": [],
        "bcc": [],
        "date": "2025-01-15T10:00:00",
        "body_text": "Authored body text",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    payload.update(overrides)
    return Email(**payload)


def test_email_db_persists_meeting_and_exchange_metadata() -> None:
    db = EmailDatabase(":memory:")
    email = _email(
        is_calendar_message=True,
        meeting_data={"OPFMeetingStartDate": "2025-01-15T10:00:00", "OPFMeetingLocation": "Room A"},
        exchange_extracted_links=[{"url": "https://example.com/meeting"}],
        exchange_extracted_emails=["assistant@example.com"],
        exchange_extracted_contacts=["Alice Assistant"],
        exchange_extracted_meetings=[{"subject": "Coordination", "start": "2025-01-15T10:00:00"}],
    )

    assert db.insert_email(email) is True
    full = db.get_email_full(email.uid)

    assert full is not None
    assert full["meeting_data"]["OPFMeetingLocation"] == "Room A"
    assert full["exchange_extracted_links"] == [{"url": "https://example.com/meeting"}]
    assert full["exchange_extracted_emails"] == ["assistant@example.com"]
    assert full["exchange_extracted_contacts"] == ["Alice Assistant"]
    assert full["exchange_extracted_meetings"] == [{"subject": "Coordination", "start": "2025-01-15T10:00:00"}]
    db.close()


def test_reply_context_enrichment_runs_even_with_thread_headers_present() -> None:
    parts = ParsedEmailParts(
        message_id="<reply@example.com>",
        subject="Re: Thema",
        sender_name="Bob Example",
        sender_email="bob@example.com",
        to_addresses=["Alice <employee@example.test>"],
        cc_addresses=[],
        bcc_addresses=[],
        to_identities=["employee@example.test"],
        cc_identities=[],
        bcc_identities=[],
        recipient_identity_source="parsed_addresses",
        date="2025-01-15T10:00:00",
        body_text=(
            "Aktuelle Antwort.\n\n"
            "Von: Alice <employee@example.test>\n"
            "Gesendet: Montag, 15. Januar 2025 09:00\n"
            "An: Bob <bob@example.com>\n"
            "Betreff: Urspruengliches Thema\n\n"
            "Vorherige Nachricht."
        ),
        body_html="",
        folder="Inbox",
        preview="",
        raw_body_text="",
        raw_body_html="",
        raw_source="",
        raw_source_headers={},
        attachment_names=[],
        attachments=[],
        conversation_id="conv-1",
        in_reply_to="<parent@example.com>",
        references=["<parent@example.com>"],
        priority=0,
        is_read=True,
        categories=[],
        thread_topic="Thema",
        thread_index="",
        inference_classification="",
        is_calendar_message=False,
        meeting_data={},
        exchange_extracted_links=[],
        exchange_extracted_emails=[],
        exchange_extracted_contacts=[],
        exchange_extracted_meetings=[],
    )

    enrichments = derive_email_enrichments(parts, "test.xml", classify_email_type_fn=lambda *_args: "reply")

    assert enrichments.reply_context_from == "employee@example.test"
    assert enrichments.reply_context_to == ["bob@example.com"]
    assert enrichments.reply_context_subject == "Urspruengliches Thema"


def test_reingest_analytics_uses_attachment_text_for_body_poor_rows(tmp_path) -> None:
    db_path = tmp_path / "analytics.db"
    db = EmailDatabase(str(db_path))
    email = _email(
        body_text="",
        has_attachments=True,
        attachments=[
            {
                "name": "bem-notiz.txt",
                "mime_type": "text/plain",
                "size": 42,
                "is_inline": False,
                "extracted_text": "Bitte beachten Sie die Dienstvereinbarung zum mobilen Arbeiten.",
                "text_preview": "Bitte beachten Sie die Dienstvereinbarung zum mobilen Arbeiten.",
                "extraction_state": "text_extracted",
                "evidence_strength": "strong_text",
            }
        ],
    )
    db.insert_email(email)
    db.close()

    result = reingest_analytics_impl(sqlite_path=str(db_path))

    assert result["updated"] == 1
    db = EmailDatabase(str(db_path))
    row = db.conn.execute(
        "SELECT detected_language, detected_language_source FROM emails WHERE uid = ?",
        (email.uid,),
    ).fetchone()
    assert row["detected_language"] == "de"
    assert row["detected_language_source"] == "subject_plus_attachment_text"
    db.close()


def test_reextract_entities_uses_attachment_text_when_body_is_empty(tmp_path) -> None:
    from src.entity_extractor import extract_entities

    db_path = tmp_path / "entities.db"
    db = EmailDatabase(str(db_path))
    email = _email(
        body_text="",
        subject="Kontakt",
        has_attachments=True,
        attachments=[
            {
                "name": "hinweis.txt",
                "mime_type": "text/plain",
                "size": 20,
                "is_inline": False,
                "extracted_text": "Kontakt: vendor@example.com und https://example.com/pfad",
                "text_preview": "Kontakt: vendor@example.com und https://example.com/pfad",
                "extraction_state": "text_extracted",
                "evidence_strength": "strong_text",
            }
        ],
    )
    db.insert_email(email)
    db.close()

    result = reextract_entities_impl(
        sqlite_path=str(db_path),
        entity_extractor_fn=extract_entities,
        extractor_key="regex_only",
        extraction_version="1",
        force=True,
    )

    assert result["updated"] == 1
    db = EmailDatabase(str(db_path))
    rows = db.conn.execute("SELECT entity_type, normalized_form FROM entities ORDER BY entity_type, normalized_form").fetchall()
    assert ("email", "vendor@example.com") in {(row["entity_type"], row["normalized_form"]) for row in rows}
    assert ("url", "https://example.com/pfad") in {(row["entity_type"], row["normalized_form"]) for row in rows}
    db.close()


def test_search_message_segments_returns_quoted_reply_hits() -> None:
    db = EmailDatabase(":memory:")
    email = _email(
        body_text="Bitte siehe unten.",
        segments=[
            ConversationSegment(
                ordinal=1,
                segment_type="quoted_reply",
                depth=1,
                text="Can you send the updated staffing report by Friday?",
                source_surface="body_text",
                provenance={"kind": "quote"},
            )
        ],
    )
    db.insert_email(email)

    rows = db.search_message_segments("updated staffing report", limit=5)

    assert len(rows) == 1
    assert rows[0]["uid"] == email.uid
    assert rows[0]["segment_type"] == "quoted_reply"
    assert rows[0]["score"] > 0.35
    db.close()


def test_extract_text_reads_attached_email_and_zip_member_text() -> None:
    eml_bytes = (
        b"From: Alice <employee@example.test>\r\n"
        b"To: Bob <bob@example.com>\r\n"
        b"Subject: Attached thread\r\n"
        b"Date: Wed, 15 Jan 2025 10:00:00 +0100\r\n"
        b"\r\n"
        b"Please keep the mobile work arrangement."
    )
    eml_text = extract_text("note.eml", eml_bytes, mime_type="message/rfc822")
    assert eml_text is not None
    assert "Subject: Attached thread" in eml_text
    assert "Please keep the mobile work arrangement." in eml_text

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes/protokoll.txt", "BEM-Protokoll mit Hinweis auf mobiles Arbeiten")
    zip_text = extract_text("bundle.zip", buffer.getvalue(), mime_type="application/zip")
    assert zip_text is not None
    assert "[Archive extracted member text]" in zip_text
    assert "BEM-Protokoll" in zip_text
    assert classify_text_extraction_state("bundle.zip", zip_text) == "archive_contents_extracted"


def test_harvest_wave_payload_promotes_attachment_exact_quotes() -> None:
    db = EmailDatabase(":memory:")
    email = _email(
        body_text="Kurznotiz",
        has_attachments=True,
        attachments=[
            {
                "name": "protokoll.txt",
                "mime_type": "text/plain",
                "size": 40,
                "is_inline": False,
                "extracted_text": "Wir bestätigen die mobile Arbeit für medizinisch notwendige Termine.",
                "text_preview": "Wir bestätigen die mobile Arbeit für medizinisch notwendige Termine.",
                "extraction_state": "text_extracted",
                "evidence_strength": "strong_text",
            }
        ],
    )
    db.insert_email(email)

    payload = {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q34"],
            "scan_id": "scan:test:wave_1",
        },
        "archive_harvest": {
            "evidence_bank": [
                {
                    "uid": email.uid,
                    "candidate_kind": "attachment",
                    "rank": 1,
                    "score": 0.8,
                    "subject": "BEM",
                    "sender_email": "employee@example.test",
                    "sender_name": "employee",
                    "date": "2025-01-15T10:00:00",
                    "conversation_id": "conv-1",
                    "snippet": "Wir bestätigen die mobile Arbeit für medizinisch notwendige Termine.",
                    "verification_status": "attachment_reference",
                    "attachment": {"filename": "protokoll.txt", "mime_type": "text/plain"},
                    "provenance": {"evidence_handle": f"attachment:{email.uid}:protokoll.txt"},
                }
            ]
        },
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P80",
        phase_id="P80",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    assert result["candidate_count"] == 1
    assert result["attachment_candidate_count"] == 1
    assert result["promoted_count"] == 1
    assert db.evidence_stats()["total"] == 1
    db.close()
