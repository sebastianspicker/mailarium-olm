# ruff: noqa: F401
"""Tests for the SQLite EmailDatabase."""

import sqlite3

from src.db_schema import init_schema
from src.email_db import EmailDatabase, _parse_address
from src.parse_olm import Email

from .helpers.email_db_builders import _make_email


class TestSchemaV7:
    def test_migration_adds_new_columns(self):
        db = EmailDatabase(":memory:")
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
        assert "categories" in cols
        assert "thread_topic" in cols
        assert "inference_classification" in cols
        assert "is_calendar_message" in cols
        assert "references_json" in cols
        db.close()

    def test_migration_creates_new_tables(self):
        db = EmailDatabase(":memory:")
        tables = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "attachments" in tables
        assert "email_categories" in tables
        db.close()

    def test_insert_populates_categories(self):
        db = EmailDatabase(":memory:")
        email = _make_email(categories=["Meeting", "Finance"])
        db.insert_email(email)
        cats = db.category_counts()
        assert len(cats) == 2
        names = {c["category"] for c in cats}
        assert "Meeting" in names
        assert "Finance" in names
        db.close()

    def test_emails_by_category(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<m1>", categories=["Finance"])
        e2 = _make_email(message_id="<m2>", categories=["HR"])
        db.insert_email(e1)
        db.insert_email(e2)
        finance = db.emails_by_category("Finance")
        assert len(finance) == 1
        assert finance[0]["uid"] == e1.uid
        db.close()

    def test_insert_populates_attachments_table(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["doc.pdf"],
            attachments=[
                {"name": "doc.pdf", "mime_type": "application/pdf", "size": 1000, "content_id": "", "is_inline": False},
                {"name": "logo.png", "mime_type": "image/png", "size": 500, "content_id": "cid123", "is_inline": True},
            ],
        )
        db.insert_email(email)
        atts = db.attachments_for_email(email.uid)
        assert len(atts) == 2
        assert atts[0]["name"] == "doc.pdf"
        assert atts[0]["is_inline"] == 0
        assert atts[1]["content_id"] == "cid123"
        assert atts[1]["is_inline"] == 1
        db.close()

    def test_insert_populates_attachment_evidence_fields(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["scan.pdf"],
            attachments=[
                {
                    "name": "scan.pdf",
                    "mime_type": "application/pdf",
                    "size": 1000,
                    "content_id": "",
                    "is_inline": False,
                    "attachment_id": "sha256:abc123",
                    "content_sha256": "abc123",
                    "extraction_state": "ocr_text_extracted",
                    "evidence_strength": "strong_text",
                    "ocr_used": True,
                    "ocr_engine": "tesseract",
                    "ocr_lang": "deu+eng",
                    "failure_reason": None,
                    "text_preview": "Scanned invoice total: 123.45 EUR",
                    "extracted_text": "Scanned invoice total: 123.45 EUR",
                    "normalized_text": "Scanned invoice total: 123.45 EUR",
                    "text_normalization_version": 1,
                    "locator_version": 2,
                    "text_source_path": "attachment://uid/0/scan.pdf",
                    "text_locator": {"kind": "mailbox_attachment", "filename": "scan.pdf"},
                }
            ],
        )
        db.insert_email(email)
        atts = db.attachments_for_email(email.uid)
        assert len(atts) == 1
        assert atts[0]["extraction_state"] == "ocr_text_extracted"
        assert atts[0]["evidence_strength"] == "strong_text"
        assert atts[0]["ocr_used"] == 1
        assert atts[0]["attachment_id"] == "sha256:abc123"
        assert atts[0]["content_sha256"] == "abc123"
        assert atts[0]["ocr_engine"] == "tesseract"
        assert atts[0]["ocr_lang"] == "deu+eng"
        assert atts[0]["failure_reason"] in (None, "")
        assert atts[0]["text_preview"] == "Scanned invoice total: 123.45 EUR"
        assert atts[0]["extracted_text"] == "Scanned invoice total: 123.45 EUR"
        assert atts[0]["normalized_text"] == "Scanned invoice total: 123.45 EUR"
        assert atts[0]["text_normalization_version"] == 1
        assert atts[0]["locator_version"] == 2
        assert atts[0]["text_source_path"] == "attachment://uid/0/scan.pdf"
        assert atts[0]["text_locator"] == {"kind": "mailbox_attachment", "filename": "scan.pdf"}
        db.close()

    def test_attachments_for_email_derives_structured_semantics_from_durable_text(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["arbeitszeitnachweis.xlsx", "meeting.ics"],
            attachments=[
                {
                    "name": "arbeitszeitnachweis.xlsx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "size": 1200,
                    "content_id": "",
                    "is_inline": False,
                    "extraction_state": "text_extracted",
                    "evidence_strength": "strong_text",
                    "ocr_used": False,
                    "text_preview": "[Sheet: March] time system attendance 2026-03-01 to 2026-03-31",
                    "extracted_text": "[Sheet: March] time system attendance 2026-03-01 to 2026-03-31",
                },
                {
                    "name": "meeting.ics",
                    "mime_type": "text/calendar",
                    "size": 600,
                    "content_id": "",
                    "is_inline": False,
                    "extraction_state": "text_extracted",
                    "evidence_strength": "strong_text",
                    "ocr_used": False,
                    "text_preview": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:BEM review\nDTSTART:20260322T090000\nEND:VEVENT",
                    "extracted_text": "BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:BEM review\nDTSTART:20260322T090000\nEND:VEVENT",
                },
            ],
        )
        db.insert_email(email)
        atts = db.attachments_for_email(email.uid)
        spreadsheet = next(att for att in atts if att["name"] == "arbeitszeitnachweis.xlsx")
        calendar = next(att for att in atts if att["name"] == "meeting.ics")
        assert spreadsheet["source_type_hint"] == "time_record"
        assert spreadsheet["documentary_support"]["format_profile"]["format_family"] == "spreadsheet"
        assert spreadsheet["spreadsheet_semantics"]["record_type"] == "time system_export"
        assert spreadsheet["spreadsheet_semantics"]["date_range"] == {"start": "2026-03-01", "end": "2026-03-31"}
        assert calendar["documentary_support"]["format_profile"]["format_family"] == "calendar"
        assert calendar["calendar_semantics"]["calendar_summary"] == "BEM review"
        assert calendar["calendar_semantics"]["dtstart"] == "2026-03-22T09:00:00"
        assert calendar["calendar_semantics"]["schedule_signal"] == "invite"
        db.close()

    def test_calendar_emails(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<cal1>", is_calendar_message=True, date="2025-01-10T10:00:00")
        e2 = _make_email(message_id="<cal2>", is_calendar_message=False, date="2025-01-11T10:00:00")
        db.insert_email(e1)
        db.insert_email(e2)
        cals = db.calendar_emails()
        assert len(cals) == 1
        assert cals[0]["uid"] == e1.uid
        db.close()

    def test_references_json_stored(self):
        db = EmailDatabase(":memory:")
        email = _make_email(references=["ref1@example.com", "ref2@example.com"])
        db.insert_email(email)
        full = db.get_email_full(email.uid)
        assert full["references"] == ["ref1@example.com", "ref2@example.com"]
        db.close()

    def test_thread_by_references(self):
        db = EmailDatabase(":memory:")
        email = _make_email(references=["root@example.com", "parent@example.com"])
        db.insert_email(email)
        found = db.thread_by_references("root@example.com")
        assert len(found) == 1
        assert found[0]["uid"] == email.uid
        db.close()

    def test_thread_by_topic(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(message_id="<t1>", thread_topic="Budget Q4")
        e2 = _make_email(message_id="<t2>", thread_topic="Budget Q4")
        e3 = _make_email(message_id="<t3>", thread_topic="Other")
        db.insert_email(e1)
        db.insert_email(e2)
        db.insert_email(e3)
        found = db.thread_by_topic("Budget Q4")
        assert len(found) == 2
        db.close()

    def test_batch_insert_populates_v7_fields(self):
        db = EmailDatabase(":memory:")
        e1 = _make_email(
            message_id="<b1>",
            categories=["Important"],
            is_calendar_message=True,
            references=["r1@example.com"],
            attachments=[{"name": "a.txt", "mime_type": "text/plain", "size": 100, "content_id": "", "is_inline": False}],
        )
        inserted = db.insert_emails_batch([e1])
        assert len(inserted) == 1
        cats = db.category_counts()
        assert len(cats) == 1
        atts = db.attachments_for_email(e1.uid)
        assert len(atts) == 1
        full = db.get_email_full(e1.uid)
        assert full["is_calendar_message"] == 1
        assert full["references"] == ["r1@example.com"]
        db.close()

    def test_get_email_full_includes_attachments(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["report.pdf"],
            attachments=[
                {"name": "report.pdf", "mime_type": "application/pdf", "size": 2000, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        full = db.get_email_full(email.uid)
        assert "attachments" in full
        assert len(full["attachments"]) == 1
        assert full["attachments"][0]["name"] == "report.pdf"
        db.close()

    def test_get_email_for_reembed_populates_attachments(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["report.pdf"],
            attachments=[
                {"name": "report.pdf", "mime_type": "application/pdf", "size": 2000, "content_id": "", "is_inline": False},
            ],
        )
        db.insert_email(email)
        result = db.get_email_for_reembed(email.uid)
        assert result is not None
        assert result["attachment_names"] == ["report.pdf"]
        assert len(result["attachments"]) == 1
        assert result["attachments"][0]["name"] == "report.pdf"
        db.close()


class TestSchemaV8:
    def test_migration_adds_analytics_columns(self):
        db = EmailDatabase(":memory:")
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
        assert "detected_language" in cols
        assert "detected_language_confidence" in cols
        assert "detected_language_reason" in cols
        assert "detected_language_source" in cols
        assert "detected_language_token_count" in cols
        assert "sentiment_label" in cols
        assert "sentiment_score" in cols
        db.close()

    def test_update_analytics_batch(self):
        db = EmailDatabase(":memory:")
        db.insert_email(_make_email(message_id="<a1@example.test>"))
        db.insert_email(_make_email(message_id="<a2@example.test>", sender_email="bob@example.com"))
        e1_uid = _make_email(message_id="<a1@example.test>").uid
        e2_uid = _make_email(message_id="<a2@example.test>", sender_email="bob@example.com").uid
        updated = db.update_analytics_batch(
            [
                ("en", "positive", 0.8, e1_uid),
                ("de", "neutral", 0.0, e2_uid),
            ]
        )
        assert updated == 2
        row = db.conn.execute(
            "SELECT detected_language, sentiment_label, sentiment_score FROM emails WHERE uid=?",
            (e1_uid,),
        ).fetchone()
        assert row["detected_language"] == "en"
        assert row["sentiment_label"] == "positive"
        assert abs(row["sentiment_score"] - 0.8) < 0.01
        db.close()

    def test_update_analytics_batch_supports_language_metadata(self):
        db = EmailDatabase(":memory:")
        email = _make_email(message_id="<a3@example.test>")
        db.insert_email(email)
        updated = db.update_analytics_batch(
            [
                ("de", "low", "short_text_stopword_vote", "raw_body_text", 2, "neutral", 0.0, email.uid),
            ]
        )
        assert updated == 1
        row = db.conn.execute(
            """
            SELECT detected_language, detected_language_confidence, detected_language_reason,
                   detected_language_source, detected_language_token_count, sentiment_label
            FROM emails WHERE uid=?
            """,
            (email.uid,),
        ).fetchone()
        assert row["detected_language"] == "de"
        assert row["detected_language_confidence"] == "low"
        assert row["detected_language_reason"] == "short_text_stopword_vote"
        assert row["detected_language_source"] == "raw_body_text"
        assert row["detected_language_token_count"] == 2
        assert row["sentiment_label"] == "neutral"
        db.close()


class TestSchemaV9:
    def test_migration_adds_ingestion_run_id_column(self):
        db = EmailDatabase(":memory:")
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()}
        assert "ingestion_run_id" in cols
        db.close()

    def test_batch_insert_stores_ingestion_run_id(self):
        db = EmailDatabase(":memory:")
        run_id = db.record_ingestion_start("test.olm")
        db.record_ingestion_complete(run_id, {"emails_parsed": 1, "emails_inserted": 1})
        emails = [_make_email(message_id="<run1@example.test>")]
        db.insert_emails_batch(emails, ingestion_run_id=run_id)
        row = db.conn.execute(
            "SELECT ingestion_run_id FROM emails WHERE uid = ?",
            (emails[0].uid,),
        ).fetchone()
        assert row["ingestion_run_id"] == run_id
        db.close()

    def test_batch_insert_without_run_id(self):
        db = EmailDatabase(":memory:")
        emails = [_make_email(message_id="<norun@example.test>")]
        db.insert_emails_batch(emails)
        row = db.conn.execute(
            "SELECT ingestion_run_id FROM emails WHERE uid = ?",
            (emails[0].uid,),
        ).fetchone()
        assert row["ingestion_run_id"] is None
        db.close()


class TestSchemaV23:
    def test_migration_adds_entity_provenance_columns_to_existing_archive(self, tmp_path):
        db_path = tmp_path / "old.db"
        db = EmailDatabase(str(db_path))
        db.insert_email(_make_email(message_id="<legacy@example.test>"))
        conn = db.conn
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version(version) VALUES(22)")
        conn.execute("DROP TABLE entity_mentions")
        conn.execute(
            """CREATE TABLE entity_mentions (
                entity_id INTEGER NOT NULL,
                email_uid TEXT NOT NULL,
                mention_count INTEGER DEFAULT 1,
                PRIMARY KEY (entity_id, email_uid)
            )"""
        )
        conn.execute("DELETE FROM entities")
        conn.execute("INSERT INTO entities(id, entity_text, entity_type, normalized_form) VALUES(1, 'Alice', 'person', 'alice')")
        email_uid = conn.execute("SELECT uid FROM emails LIMIT 1").fetchone()[0]
        conn.execute("INSERT INTO entity_mentions(entity_id, email_uid, mention_count) VALUES(1, ?, 1)", (email_uid,))
        conn.commit()

        init_schema(conn)

        cols = {row[1] for row in conn.execute("PRAGMA table_info(entity_mentions)").fetchall()}
        assert "extractor_key" in cols
        assert "extraction_version" in cols
        assert "extracted_at" in cols
        row = conn.execute(
            "SELECT extractor_key, extraction_version, extracted_at FROM entity_mentions WHERE email_uid = ?",
            (email_uid,),
        ).fetchone()
        assert row[0] == ""
        assert row[1] == ""
        assert row[2]
        db.close()


class TestUpdateV7IsInline:
    def test_is_inline_uses_field_not_content_id(self):
        """is_inline should come from the attachment's is_inline field,
        not from bool(content_id)."""
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachments=[
                {
                    "name": "logo.png",
                    "mime_type": "image/png",
                    "size": 100,
                    "content_id": "cid:logo@example.com",
                    "is_inline": False,
                },
            ],
        )
        db.insert_email(email)
        # Now simulate update_v7_metadata with the same attachment
        db.update_v7_metadata(email)
        row = db.conn.execute("SELECT is_inline FROM attachments WHERE email_uid = ?", (email.uid,)).fetchone()
        # Despite having content_id, is_inline should be 0 because is_inline=False
        assert row["is_inline"] == 0
        db.close()

    def test_update_v7_metadata_replaces_removed_categories(self):
        db = EmailDatabase(":memory:")
        email = _make_email(categories=["Red", "Blue"])
        db.insert_email(email)

        email.categories = ["Blue"]
        db.update_v7_metadata(email)

        rows = db.conn.execute(
            "SELECT category FROM email_categories WHERE email_uid = ? ORDER BY category",
            (email.uid,),
        ).fetchall()
        assert [row["category"] for row in rows] == ["Blue"]
        db.close()

    def test_update_v7_metadata_persists_meeting_and_exchange_json(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            is_calendar_message=True,
            meeting_data={"OPFMeetingLocation": "Room A"},
            exchange_extracted_links=[{"url": "https://example.com"}],
            exchange_extracted_emails=["assistant@example.com"],
            exchange_extracted_contacts=["Alice Assistant"],
            exchange_extracted_meetings=[{"subject": "Coordination"}],
        )
        db.insert_email(email)
        db.update_v7_metadata(email)

        row = db.conn.execute(
            """
            SELECT meeting_data_json, exchange_extracted_links_json, exchange_extracted_emails_json,
                   exchange_extracted_contacts_json, exchange_extracted_meetings_json
            FROM emails WHERE uid = ?
            """,
            (email.uid,),
        ).fetchone()
        assert row is not None
        assert "Room A" in row["meeting_data_json"]
        assert "assistant@example.com" in row["exchange_extracted_emails_json"]
        assert "Alice Assistant" in row["exchange_extracted_contacts_json"]
        db.close()

    def test_update_v7_metadata_preserves_attachment_evidence_fields_when_reparse_lacks_replacements(self):
        db = EmailDatabase(":memory:")
        email = _make_email(
            has_attachments=True,
            attachment_names=["scan.pdf"],
            attachments=[
                {
                    "name": "scan.pdf",
                    "mime_type": "application/pdf",
                    "size": 1000,
                    "content_id": "",
                    "is_inline": False,
                    "extraction_state": "ocr_text_extracted",
                    "evidence_strength": "strong_text",
                    "ocr_used": True,
                    "failure_reason": "ocr_recovered",
                    "text_preview": "Recovered text preview",
                    "extracted_text": "Recovered full text",
                    "text_source_path": "attachment://uid/0/scan.pdf",
                    "text_locator": {"kind": "mailbox_attachment", "filename": "scan.pdf"},
                }
            ],
        )
        db.insert_email(email)

        email.attachments = [
            {
                "name": "scan.pdf",
                "mime_type": "application/pdf",
                "size": 1000,
                "content_id": "",
                "is_inline": False,
            }
        ]
        db.update_v7_metadata(email)

        row = db.attachments_for_email(email.uid)[0]
        assert row["extraction_state"] == "ocr_text_extracted"
        assert row["evidence_strength"] == "strong_text"
        assert row["ocr_used"] == 1
        assert row["failure_reason"] == "ocr_recovered"
        assert row["text_preview"] == "Recovered text preview"
        assert row["extracted_text"] == "Recovered full text"
        assert row["text_source_path"] == "attachment://uid/0/scan.pdf"
        assert row["text_locator"] == {"kind": "mailbox_attachment", "filename": "scan.pdf"}
        db.close()


class TestSchemaV29:
    def test_language_surface_analytics_table_exists(self):
        db = EmailDatabase(":memory:")
        tables = {row["name"] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "language_surface_analytics" in tables
        db.close()

    def test_upsert_language_surface_analytics_replaces_existing_surface_row(self):
        db = EmailDatabase(":memory:")
        email = _make_email(message_id="<surface@example.test>")
        db.insert_email(email)

        inserted = db.upsert_language_surface_analytics(
            [
                (
                    email.uid,
                    "authored_body",
                    "body_text",
                    0,
                    "hash-1",
                    42,
                    "de",
                    "high",
                    "stopword_overlap_with_markers",
                    8,
                )
            ]
        )
        assert inserted == 1

        db.upsert_language_surface_analytics(
            [
                (
                    email.uid,
                    "authored_body",
                    "body_text",
                    0,
                    "hash-2",
                    51,
                    "en",
                    "medium",
                    "stopword_overlap",
                    9,
                )
            ]
        )

        row = db.conn.execute(
            "SELECT text_hash, text_char_count, detected_language FROM language_surface_analytics "
            "WHERE email_uid = ? AND surface_scope = ?",
            (email.uid, "authored_body"),
        ).fetchone()
        assert row is not None
        assert row["text_hash"] == "hash-2"
        assert row["text_char_count"] == 51
        assert row["detected_language"] == "en"
        db.close()


class TestSchemaV30ToV33:
    def test_event_records_table_exists_and_upserts(self):
        db = EmailDatabase(":memory:")
        email = _make_email(message_id="<event-schema@example.test>")
        db.insert_email(email)

        inserted = db.upsert_event_records(
            [
                (
                    "event-key-1",
                    email.uid,
                    "request",
                    "authored_body",
                    "message_segments",
                    0,
                    10,
                    18,
                    "Bitte",
                    "2026-03-01",
                    "surface-hash-1",
                    "de",
                    "medium",
                    "de_event_rule_v1",
                    "{}",
                )
            ]
        )
        assert inserted == 1

        db.upsert_event_records(
            [
                (
                    "event-key-1",
                    email.uid,
                    "deadline_pressure",
                    "authored_body",
                    "message_segments",
                    0,
                    20,
                    31,
                    "spätestens",
                    "2026-03-01",
                    "surface-hash-1",
                    "de",
                    "high",
                    "de_event_rule_v1",
                    "{}",
                )
            ]
        )
        row = db.conn.execute("SELECT event_kind FROM event_records WHERE event_key = ?", ("event-key-1",)).fetchone()
        assert row is not None
        assert row["event_kind"] == "deadline_pressure"
        db.close()

    def test_entity_occurrences_table_exists_and_upserts(self):
        db = EmailDatabase(":memory:")
        email = _make_email(message_id="<occurrence-schema@example.test>")
        db.insert_email(email)
        inserted = db.insert_entity_occurrences(
            email.uid,
            [
                (
                    "SBV",
                    "organization",
                    "sbv",
                    "authored_body",
                    "message_segments",
                    0,
                    5,
                    8,
                    "SBV",
                )
            ],
            extractor_key="regex_only",
            extraction_version="1",
        )
        assert inserted == 1
        rows = db.entity_occurrences_for_email(email.uid)
        assert rows
        assert rows[0]["normalized_form"] == "sbv"
        assert rows[0]["source_scope"] == "authored_body"
        grouped = db.entity_occurrences_for_uids([email.uid])
        assert email.uid in grouped
        assert grouped[email.uid]
        assert grouped[email.uid][0]["normalized_form"] == "sbv"
        db.close()

    def test_ingest_checkpoints_table_exists_and_roundtrips(self):
        db = EmailDatabase(":memory:")
        run_id = db.record_ingestion_start("archive.olm")
        db.update_ingest_checkpoint(
            run_id=run_id,
            olm_path="archive.olm",
            last_batch_ordinal=2,
            emails_parsed=42,
            emails_inserted=40,
            last_email_uid="uid-42",
            status="running",
            commit=True,
        )
        checkpoint = db.latest_ingest_checkpoint(olm_path="archive.olm")
        assert checkpoint is not None
        assert checkpoint["emails_parsed"] == 42
        assert checkpoint["last_email_uid"] == "uid-42"
        db.clear_ingest_checkpoint(run_id)
        checkpoint_after = db.latest_ingest_checkpoint(olm_path="archive.olm")
        assert checkpoint_after is None
        db.close()
